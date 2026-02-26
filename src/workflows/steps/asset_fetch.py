
import asyncio
import logging
from typing import Dict, Any, List

from src.core.models.geometry import BoundingBox
from src.core.models.surface import BuildingAdjustedSurface
from src.core.models.asset import BuildingCluster
from src.core.models.enums import StructureCategory, StructureType
from src.data.open_buildings import OpenBuildingsSource
from src.data.elevation import get_elevation, get_elevation_footprint
from src.data.spatial_matcher import SpatialMatcher, SpatialMatchContext
from src.config.settings import settings

logger = logging.getLogger(__name__)


async def fetch_buildings_step(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 0: Fetch buildings + spatially match + create BuildingAdjustedSurface.

    Inputs:
        data["lat"]: float
        data["lon"]: float
        data["building_radius_m"]: int
        data["include_buildings"]: bool (optional)
        data["name"]: str (optional — building name for matching)
        data["address"]: str (optional — address for matching)
        data["structure_category"]: str (optional — residential/commercial/industrial)
        data["structure_type"]: str (optional — hotel, tube_house, etc.)

    Outputs:
        data["building_cluster"]: BuildingCluster
        data["building_surfaces"]: Dict[str, BuildingAdjustedSurface]
    """
    lat = data["lat"]
    lon = data["lon"]
    req_name = (data.get("name") or "").lower().strip()
    req_address = (data.get("address") or "").lower().strip()
    radius_m = data.get("building_radius_m", 500)
    include_buildings = data.get("include_buildings", True)

    # Parse structure hints
    raw_cat = data.get("structure_category")
    raw_type = data.get("structure_type")
    structure_category = StructureCategory(raw_cat) if raw_cat else None
    structure_type = StructureType(raw_type) if raw_type else None

    # Initialize connection to asset source
    asset_source = OpenBuildingsSource(db_url=settings.DATABASE_URL)

    if not include_buildings:
        logger.info("Building fetch skipped (include_buildings=False)")
        data["building_cluster"] = None
        data["building_surfaces"] = {}
        return data

    # 1. Compute BBox from radius
    delta_deg = radius_m / 111320.0
    bbox = BoundingBox(
        min_lat=lat - delta_deg,
        max_lat=lat + delta_deg,
        min_lon=lon - delta_deg,
        max_lon=lon + delta_deg
    )

    # ------------------------------------------------------------------
    # Fetch buildings from data sources
    # ------------------------------------------------------------------
    overture_source = None
    places = []
    building_parts = []

    async def fetch_overture(search_bbox, enrich_places=False):
        nonlocal overture_source, places
        try:
            from src.data.overture_buildings import OvertureBuildingsSource
            overture_source = OvertureBuildingsSource()
            raw_buildings = await asyncio.to_thread(
                overture_source.query_buildings, bbox=search_bbox,
            )
            if raw_buildings:
                enriched = overture_source.enrich_with_osm_tags(raw_buildings)
                if enrich_places:
                    try:
                        places = await asyncio.to_thread(
                            overture_source.query_places, bbox=search_bbox,
                        )
                        if places:
                            enriched = overture_source.enrich_buildings_with_places(
                                enriched, places,
                            )
                    except Exception as e:
                        logger.warning(f"Overture places enrichment failed (non-fatal): {e}")
                return overture_source.to_structural_characteristics(enriched)
        except Exception as e:
            logger.error(f"Overture Maps fetch failed: {e}")
        return []

    structures = []
    overture_tried = False

    # If the user is specifically trying to match a building by name or address,
    # we MUST use Overture Maps first because Google Open Buildings lacks metadata.
    if req_name or req_address:
        logger.info("Name/address provided. Prioritizing Overture Maps for metadata matching.")
        structures = await fetch_overture(bbox, enrich_places=True)
        overture_tried = True

    # 2. Fetch from default source (Google) if we haven't found anything yet
    if not structures:
        logger.info(f"Fetching buildings in bbox {bbox} from default source...")
        structures = await asset_source.get_buildings_in_bbox(bbox)

    # Fallback to Overture Maps if Google returns empty (and we haven't tried yet)
    if not structures and not overture_tried:
        logger.info("Google Open Buildings returned no results. Attempting Overture Maps fallback...")
        structures = await fetch_overture(bbox)

    logger.info(f"Fetched {len(structures)} buildings total")

    # 3. Fetch building parts for complex structures (when metadata hints available)
    if (req_name or req_address or structure_type) and overture_source:
        try:
            building_parts = await asyncio.to_thread(
                overture_source.query_building_parts, bbox=bbox,
            )
            if building_parts:
                logger.info(f"Fetched {len(building_parts)} building parts")
        except Exception as e:
            logger.warning(f"Building parts fetch failed (non-fatal): {e}")

    # ------------------------------------------------------------------
    # Multi-stage spatial matching
    # ------------------------------------------------------------------
    matcher = SpatialMatcher()
    context = SpatialMatchContext(
        name=req_name,
        address=req_address,
        structure_category=structure_category,
        structure_type=structure_type,
        city=data.get("city", "unknown"),
    )

    match_results = matcher.match(
        lat, lon, structures,
        building_parts=building_parts or None,
        places=places or None,
        context=context,
    )

    # Apply match results back to structures
    matched_structures = []
    for mr in match_results:
        fp = mr.structure.footprint
        fp.footprint_match_confidence = mr.confidence
        fp.match_method = mr.match_method
        mr.structure.poi_validated = mr.poi_validated
        matched_structures.append(mr.structure)

    structures = matched_structures
    logger.info(f"Kept {len(structures)} buildings after spatial matching")

    # ------------------------------------------------------------------
    # Build cluster + elevation surfaces
    # ------------------------------------------------------------------
    tile_id = f"tile_{lat:.4f}_{lon:.4f}"

    cluster = BuildingCluster(
        tile_id=tile_id,
        bounds=bbox,
        buildings=structures
    )

    # 4. Create BuildingAdjustedSurface for each building (Gap S)
    # Use footprint-based median elevation when WKT polygon available,
    # fall back to centroid single-pixel sampling.

    async def _fetch_elev(building):
        centroid = building.footprint.centroid
        wkt = building.footprint.footprint_wkt
        try:
            if wkt and not wkt.startswith("{"):
                elev = await get_elevation_footprint(wkt)
            else:
                elev = await get_elevation(centroid.lat, centroid.lon)
        except Exception:
            elev = await get_elevation(centroid.lat, centroid.lon)
        return building.footprint.building_id, elev

    elev_results = await asyncio.gather(*[_fetch_elev(b) for b in structures])
    surfaces = {
        bid: BuildingAdjustedSurface(
            building_id=bid,
            original_elevation_m=elev,
        )
        for bid, elev in elev_results
    }

    data["building_cluster"] = cluster
    data["building_surfaces"] = surfaces

    return data
