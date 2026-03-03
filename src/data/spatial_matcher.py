# src/data/spatial_matcher.py
"""
Multi-stage spatial matching engine for building footprint lookup.

Replaces the inline centroid-distance matching in asset_fetch.py with a
6-stage pipeline:
  Stage 1: Polygon containment + POI cross-check
  Stage 2: Buffer intersection (adaptive radius)
  Stage 3: Confidence scoring & ranking
  Stage 4: Building part preference (integrated into Stage 1)
  Stage 5: Vertical stacking resolution (integrated into Stage 3)
  Stage 6: QA rejection + retry

Input:  (lat, lon) + list of StructuralCharacteristics + optional context
Output: ranked list of SpatialMatchResult with footprint_match_confidence
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from unidecode import unidecode

from src.core.models.asset import StructuralCharacteristics
from src.core.models.enums import StructureCategory, StructureType
from src.data.structure_expectations import (
    StructureExpectation,
    get_expectation,
    get_zone_leniency,
    is_converted_type,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_EARTH_RADIUS_M = 6_371_000.0
_DEG_TO_M = 111_320.0  # metres per degree latitude (approx)

# Buffer sizes by structure type for Stage 2
_LARGE_BUFFER_TYPES = {
    StructureType.SHOPPING_MALL,
    StructureType.HOTEL,
    StructureType.FACTORY,
    StructureType.WAREHOUSE,
    StructureType.APARTMENT_BUILDING,
    StructureType.OFFICE_BUILDING,
    StructureType.CONVERTED_WAREHOUSE_COMMERCIAL,
    StructureType.HOSPITAL,
    StructureType.SCHOOL,
    StructureType.MUSEUM,
    StructureType.CONVENTION_CENTER,
}
_SMALL_BUFFER_TYPES = {
    StructureType.TUBE_HOUSE,
    StructureType.INFORMAL_SETTLEMENT,
    StructureType.RETAIL_SHOP,
    StructureType.CONVERTED_TUBE_HOUSE_HOTEL,
    StructureType.CONVERTED_TUBE_HOUSE_SHOP,
    StructureType.CONVERTED_TUBE_HOUSE_RESTAURANT,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class SpatialMatchContext:
    """Caller-provided hints that inform matching and QA."""
    name: str = ""
    address: str = ""
    structure_category: Optional[StructureCategory] = None
    structure_type: Optional[StructureType] = None
    expectation: Optional[StructureExpectation] = None
    city: str = "unknown"


@dataclass
class SpatialMatchResult:
    """A scored building match."""
    structure: StructuralCharacteristics
    confidence: float = 0.0
    match_method: str = "centroid_distance"
    containment: bool = False
    overlap_ratio: float = 0.0
    centroid_distance_m: float = 0.0
    name_matched: bool = False
    address_matched: bool = False
    poi_validated: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in metres between two (lat, lon) points."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return _EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _transliterate(text: str) -> str:
    return unidecode(text).lower().strip()


def _token_overlap(a: str, b: str) -> float:
    stopwords = {"the", "a", "an", "of", "in", "and", "at", "building", "tower", "residence", "hotel", "apartments", "apartment", "complex"}
    ta = set(a.split()) - stopwords
    tb = set(b.split()) - stopwords
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _name_matches(req: str, candidate: str) -> bool:
    """Return True when *req* and *candidate* are a plausible name match."""
    if not req or not candidate:
        return False
    if req in candidate or candidate in req:
        return True
    return _token_overlap(req, candidate) >= 0.5


def _buffer_deg(metres: float, lat: float) -> float:
    """Convert a distance in metres to approximate degrees at *lat*."""
    return metres / (_DEG_TO_M * math.cos(math.radians(lat)))


def _choose_buffer_m(ctx: SpatialMatchContext) -> float:
    st = ctx.structure_type
    if st in _LARGE_BUFFER_TYPES:
        return 10.0
    if st in _SMALL_BUFFER_TYPES:
        return 3.0
    if st is not None:
        return 5.0
    return 5.0  # default


# ---------------------------------------------------------------------------
# SpatialMatcher
# ---------------------------------------------------------------------------
class SpatialMatcher:
    """Multi-stage building footprint matcher."""

    # Thresholds (can be tuned)
    CONFIDENCE_REJECT = 0.6
    QA_PLAUSIBILITY_REJECT = 0.3
    QA_RETRY_BUFFER_M = 150.0

    def match(
        self,
        lat: float,
        lon: float,
        buildings: List[StructuralCharacteristics],
        building_parts: Optional[List[Dict[str, Any]]] = None,
        places: Optional[List[Dict[str, Any]]] = None,
        context: Optional[SpatialMatchContext] = None,
    ) -> List[SpatialMatchResult]:
        """Run the full multi-stage matching pipeline.

        Returns a list of ``SpatialMatchResult`` sorted by descending
        confidence.  The caller should treat the first element as the
        best match.
        """
        if context is None:
            context = SpatialMatchContext()

        # Resolve expectation from context if not already set
        if context.expectation is None:
            context.expectation = get_expectation(
                context.structure_type, context.structure_category,
            )

        # Pre-compute: load shapely geometries, centroids, distances
        candidates = self._prepare_candidates(lat, lon, buildings)

        if not candidates:
            return []

        # Stage 1 + 4: polygon containment (prefer building parts)
        contained = self._stage1_containment(
            lat, lon, candidates, building_parts, places, context,
        )

        # Stage 2: buffer intersection
        buffer_hits = self._stage2_buffer(lat, lon, candidates, context)

        # Merge: contained + buffer hits (deduplicate by building_id)
        merged = self._merge_results(contained, buffer_hits)

        if not merged:
            # Nothing from containment or buffer — fall through to scoring
            # on ALL candidates (closest by centroid)
            merged = candidates

        # Stage 3 + 5: confidence scoring
        scored = self._stage3_scoring(merged, context, lat, lon)

        # Stage 6: QA rejection + retry
        final = self._stage6_qa(scored, lat, lon, candidates, context)

        return final

    # ------------------------------------------------------------------
    # Stage 1 + 4: Polygon containment
    # ------------------------------------------------------------------
    def _stage1_containment(
        self,
        lat: float,
        lon: float,
        candidates: List[SpatialMatchResult],
        building_parts: Optional[List[Dict[str, Any]]],
        places: Optional[List[Dict[str, Any]]],
        context: SpatialMatchContext,
    ) -> List[SpatialMatchResult]:

        try:
            from shapely.geometry import Point
            from shapely.wkt import loads as load_wkt
        except ImportError:
            return []

        query_point = Point(lon, lat)
        contained: List[SpatialMatchResult] = []

        # Stage 4: Check building parts first (more specific polygons)
        if building_parts:
            for part in building_parts:
                wkt = part.get("geometry_wkt")
                if not wkt:
                    continue
                try:
                    poly = load_wkt(wkt)
                    if poly.contains(query_point):
                        # Find parent building in candidates
                        parent_id = part.get("building_id")
                        for c in candidates:
                            bid = c.structure.footprint.building_id
                            oid = c.structure.footprint.overture_id
                            if parent_id and parent_id in (bid, oid):
                                c.containment = True
                                c.match_method = "containment_part"
                                c.confidence = 0.95
                                contained.append(c)
                                break
                except Exception:
                    continue

        # Check main building polygons
        for c in candidates:
            if c.containment:
                continue  # already matched via part
            wkt = c.structure.footprint.footprint_wkt
            if not wkt:
                continue
            try:
                if wkt.startswith("{"):
                    import ast
                    from shapely.geometry import shape
                    poly = shape(ast.literal_eval(wkt))
                else:
                    poly = load_wkt(wkt)

                if poly.contains(query_point):
                    c.containment = True
                    c.match_method = "containment"
                    c.confidence = 0.95
                    contained.append(c)
            except Exception:
                continue

        if not contained:
            return []

        # Stage 5 (vertical stacking): prefer smallest containing polygon
        if len(contained) > 1:
            contained.sort(key=lambda r: r.structure.footprint.area_m2)

        # If exactly 1 contained and it also has a POI cross-check, boost
        if len(contained) == 1:
            contained[0].poi_validated = self._poi_cross_check(
                lat, lon, contained[0], places, context,
            )
            return contained

        # Multiple containment — try POI cross-check to disambiguate
        if places and context.name:
            for c in contained:
                c.poi_validated = self._poi_cross_check(
                    lat, lon, c, places, context,
                )
            poi_matches = [c for c in contained if c.poi_validated]
            if len(poi_matches) == 1:
                return poi_matches

        return contained

    # ------------------------------------------------------------------
    # Stage 2: Buffer intersection
    # ------------------------------------------------------------------
    def _stage2_buffer(
        self,
        lat: float,
        lon: float,
        candidates: List[SpatialMatchResult],
        context: SpatialMatchContext,
        buffer_m: Optional[float] = None,
    ) -> List[SpatialMatchResult]:

        try:
            from shapely.geometry import Point
            from shapely.wkt import loads as load_wkt
        except ImportError:
            return []

        if buffer_m is None:
            buffer_m = _choose_buffer_m(context)

        buf_deg = _buffer_deg(buffer_m, lat)
        query_buf = Point(lon, lat).buffer(buf_deg)

        hits: List[SpatialMatchResult] = []
        for c in candidates:
            if c.containment:
                continue  # already handled
            wkt = c.structure.footprint.footprint_wkt
            if not wkt:
                continue
            try:
                if wkt.startswith("{"):
                    import ast
                    from shapely.geometry import shape
                    poly = shape(ast.literal_eval(wkt))
                else:
                    poly = load_wkt(wkt)

                intersection = poly.intersection(query_buf)
                if intersection.is_empty:
                    continue

                overlap = intersection.area / max(poly.area, 1e-12)
                c.overlap_ratio = min(overlap, 1.0)
                c.match_method = "buffer_overlap"
                c.confidence = 0.85 * c.overlap_ratio
                hits.append(c)
            except Exception:
                continue

        hits.sort(key=lambda r: r.overlap_ratio, reverse=True)
        return hits

    # ------------------------------------------------------------------
    # Stage 3 + 5: Confidence scoring
    # ------------------------------------------------------------------
    def _stage3_scoring(
        self,
        candidates: List[SpatialMatchResult],
        context: SpatialMatchContext,
        lat: float,
        lon: float,
    ) -> List[SpatialMatchResult]:

        req_name_t = _transliterate(context.name) if context.name else ""
        req_addr_t = _transliterate(context.address) if context.address else ""

        for c in candidates:
            fp = c.structure.footprint

            # ── Component scores ──
            containment_score = 1.0 if c.containment else 0.0
            overlap_score = c.overlap_ratio

            dist = c.centroid_distance_m
            distance_score = 1.0 / (1.0 + dist) if dist >= 0 else 0.0

            # Height similarity
            height_sim = self._height_similarity(c.structure, context)

            # Footprint plausibility
            plausibility = self._footprint_plausibility(c.structure, context, lat, lon)

            raw_score = (
                containment_score * 0.40
                + overlap_score * 0.25
                + distance_score * 0.15
                + height_sim * 0.10
                + plausibility * 0.10
            )

            # ── Name / address multiplier ──
            name_matched = False
            b_name_t = _transliterate(fp.name or "")
            b_alias_ts = [_transliterate(a) for a in (fp.name_aliases or []) if a]

            if req_name_t:
                if _name_matches(req_name_t, b_name_t):
                    name_matched = True
                if not name_matched:
                    for alias_t in b_alias_ts:
                        if _name_matches(req_name_t, alias_t):
                            name_matched = True
                            break

            addr_matched = False
            if req_addr_t:
                b_addr_t = _transliterate(fp.address or "")
                if b_addr_t and _name_matches(req_addr_t, b_addr_t):
                    addr_matched = True

            multiplier = 1.0
            if name_matched or c.poi_validated:
                multiplier *= 3.0  # Massive boost for name match, especially crucial for small footprint structures
            elif req_name_t and fp.name:
                # Explicit penalty: user requested a specific name, the building has a different distinct name
                # Avoid returning BIDV when the user explicitly asked for The Waterfront Residence
                multiplier *= 0.3

            if addr_matched:
                multiplier *= 1.5

            c.confidence = min(raw_score * multiplier, 1.0)
            c.name_matched = name_matched
            c.address_matched = addr_matched

            # Stage 5: vertical stacking bonus for smaller polygon
            if c.containment and c.structure.footprint.area_m2 < 500:
                c.confidence = min(c.confidence + 0.1, 1.0)

        # Sort descending by confidence
        candidates.sort(key=lambda r: r.confidence, reverse=True)
        return candidates

    # ------------------------------------------------------------------
    # Stage 6: QA rejection + retry
    # ------------------------------------------------------------------
    def _stage6_qa(
        self,
        scored: List[SpatialMatchResult],
        lat: float,
        lon: float,
        all_candidates: List[SpatialMatchResult],
        context: SpatialMatchContext,
    ) -> List[SpatialMatchResult]:

        if not scored:
            return []

        best = scored[0]

        # Check plausibility if expectation is available
        flagged = False
        exp = context.expectation
        if exp and best.confidence > 0:
            area = best.structure.footprint.area_m2
            height_m = best.structure.height.height_m if best.structure.height else None
            floors = best.structure.num_stories

            pscore = exp.plausibility_score(area, height_m, floors)

            # Apply zone leniency only for non-converted commercial types,
            # matching the guard in _footprint_plausibility (Stage 3).
            leniency = 1.0
            if (context.structure_type
                    and not is_converted_type(context.structure_type)
                    and context.structure_category == StructureCategory.COMMERCIAL):
                leniency = get_zone_leniency(lat, lon)
                pscore = min(pscore * leniency, 1.0)

            if pscore < self.QA_PLAUSIBILITY_REJECT:
                logger.info(
                    f"QA flag: plausibility {pscore:.2f} < {self.QA_PLAUSIBILITY_REJECT} "
                    f"for {context.structure_type} at ({lat}, {lon}), "
                    f"area={area:.0f}m², zone_leniency={leniency:.1f}. Retrying with wider buffer."
                )
                flagged = True

        # Check presence
        if best.structure.height and best.structure.height.building_presence < 0.8:
            logger.info("QA flag: building_presence < 0.8")
            flagged = True

        # Check confidence
        if best.confidence < 0.7:
            flagged = True

        # Retry with wider buffer if flagged
        if flagged:
            wider_hits = self._stage2_buffer(
                lat, lon, all_candidates, context,
                buffer_m=self.QA_RETRY_BUFFER_M,
            )
            if wider_hits:
                re_scored = self._stage3_scoring(wider_hits, context, lat, lon)
                # Pick best from retry IF it's better than original
                if re_scored and re_scored[0].confidence > best.confidence:
                    scored = re_scored
                    logger.info(
                        f"QA retry improved match: {re_scored[0].confidence:.2f} "
                        f"(was {best.confidence:.2f})"
                    )

        # Filter out below threshold
        result = [r for r in scored if r.confidence >= self.CONFIDENCE_REJECT]

        # If nothing passes threshold, return best with low-confidence flag
        if not result and scored:
            scored[0].match_method = f"{scored[0].match_method}_low_confidence"
            result = [scored[0]]

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _prepare_candidates(
        self,
        lat: float,
        lon: float,
        buildings: List[StructuralCharacteristics],
    ) -> List[SpatialMatchResult]:
        """Build initial candidate list with centroid distances."""
        results = []
        for s in buildings:
            # Reject low confidence ML detections
            conf = getattr(s.footprint, "confidence", 1.0)
            if 0 < conf < 0.65:
                continue

            dist = _haversine(lat, lon, s.footprint.centroid.lat, s.footprint.centroid.lon)
            results.append(SpatialMatchResult(
                structure=s,
                centroid_distance_m=dist,
            ))
        return results

    def _poi_cross_check(
        self,
        lat: float,
        lon: float,
        candidate: SpatialMatchResult,
        places: Optional[List[Dict[str, Any]]],
        context: SpatialMatchContext,
    ) -> bool:
        """Check if a nearby POI confirms the building type."""
        if not places or not context.name:
            return False

        req_name_t = _transliterate(context.name)
        fp = candidate.structure.footprint

        for p in places:
            plat = p.get("centroid_lat", 0)
            plon = p.get("centroid_lon", 0)

            # POI must be close to the building
            d_to_building = _haversine(
                fp.centroid.lat, fp.centroid.lon, plat, plon,
            )
            if d_to_building > 30:
                continue

            # Check name match
            pnames = p.get("names")
            if not pnames or not isinstance(pnames, dict):
                continue

            pname_t = _transliterate(pnames.get("primary", ""))
            if _name_matches(req_name_t, pname_t):
                return True

            # Check common aliases
            common = pnames.get("common")
            if common and isinstance(common, dict):
                for alias in common.values():
                    if alias and _name_matches(req_name_t, _transliterate(alias)):
                        return True

        return False

    def _height_similarity(
        self,
        structure: StructuralCharacteristics,
        context: SpatialMatchContext,
    ) -> float:
        """Return 0.0–1.0 based on how close building height is to expectation."""
        exp = context.expectation
        if exp is None:
            return 0.5  # neutral when no expectation

        height_m = structure.height.height_m if structure.height else None
        if height_m is None:
            return 0.5  # neutral when no height data

        if exp.height_plausible(height_m):
            return 1.0

        # Smooth decay outside range
        mid = (exp.min_height_m + exp.max_height_m) / 2.0
        span = exp.max_height_m - exp.min_height_m
        if span <= 0:
            return 0.5
        dist = min(abs(height_m - exp.min_height_m), abs(height_m - exp.max_height_m))
        return max(0.0, 1.0 - dist / span)

    def _footprint_plausibility(
        self,
        structure: StructuralCharacteristics,
        context: SpatialMatchContext,
        lat: float,
        lon: float,
    ) -> float:
        """Return 0.0–1.0 using the StructureExpectation plausibility_score."""
        exp = context.expectation
        if exp is None:
            return 0.5  # neutral

        area = structure.footprint.area_m2
        height_m = structure.height.height_m if structure.height else None
        floors = structure.num_stories

        score = exp.plausibility_score(area, height_m, floors)

        # Apply zone leniency for non-converted commercial types
        if (context.structure_type
                and not is_converted_type(context.structure_type)
                and context.structure_category == StructureCategory.COMMERCIAL):
            leniency = get_zone_leniency(lat, lon)
            score = min(score * leniency, 1.0)

        return score

    def _merge_results(
        self,
        *result_lists: List[SpatialMatchResult],
    ) -> List[SpatialMatchResult]:
        """Merge multiple result lists, keeping the highest-confidence entry per building."""
        seen: Dict[str, SpatialMatchResult] = {}
        for results in result_lists:
            for r in results:
                bid = r.structure.footprint.building_id
                if bid not in seen or r.confidence > seen[bid].confidence:
                    seen[bid] = r
        return list(seen.values())
