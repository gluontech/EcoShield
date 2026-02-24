
import asyncio
import logging
from typing import Dict, Any, List

from unidecode import unidecode

from src.core.models.geometry import BoundingBox
from src.core.models.surface import BuildingAdjustedSurface
from src.core.models.asset import BuildingCluster
from src.data.open_buildings import OpenBuildingsSource
from src.data.elevation import get_elevation
from src.config.settings import settings

logger = logging.getLogger(__name__)


def _transliterate(text: str) -> str:
    """Transliterate any Unicode script to lowercase ASCII for matching.

    Handles Vietnamese diacritics, Thai, Chinese, Arabic, etc. via unidecode.
    """
    return unidecode(text).lower().strip()


def _token_overlap_score(a: str, b: str) -> float:
    """Fraction of the shorter string's tokens found in the longer string.

    Returns 0.0–1.0.  A score >= 0.5 indicates a likely match.
    """
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    return len(intersection) / min(len(tokens_a), len(tokens_b))


async def fetch_buildings_step(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 0: Fetch buildings + create BuildingAdjustedSurface per building.
    
    Inputs:
        data["lat"]: float
        data["lon"]: float
        data["building_radius_m"]: int
        data["include_buildings"]: bool (optional)
        
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
    
    # Initialize connection to asset source
    # In a real app, this might be injected or cached
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
    
    async def fetch_overture(search_bbox):
        try:
            from src.data.overture_buildings import OvertureBuildingsSource
            overture_source = OvertureBuildingsSource()
            raw_buildings = await asyncio.to_thread(overture_source.query_buildings, bbox=search_bbox)
            if raw_buildings:
                enriched = overture_source.enrich_with_osm_tags(raw_buildings)
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
        structures = await fetch_overture(bbox)
        overture_tried = True

    # 2. Fetch from default source (Google) if we haven't found anything yet
    if not structures:
        logger.info(f"Fetching buildings in bbox {bbox} from default source...")
        structures = await asset_source.get_buildings_in_bbox(bbox)
        
    # Fallback to Overture Maps if Google Open Buildings returns empty (and we haven't tried yet)
    if not structures and not overture_tried:
        logger.info("Google Open Buildings returned no results. Attempting Overture Maps fallback...")
        structures = await fetch_overture(bbox)

    logger.info(f"Fetched {len(structures)} buildings total")

    # Filter and sort structures by distance to requested point
    def haversine(lat1, lon1, lat2, lon2):
        import math
        R = 6371000
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    try:
        from shapely.wkt import loads as load_wkt
        from shapely.geometry import Point
        query_point = Point(lon, lat)
        shapely_available = True
    except ImportError:
        logger.warning("shapely not installed. Falling back to simple distance.")
        shapely_available = False

    filtered_structures = []
    for s in structures:
        # Reject low confidence ML detections
        conf = getattr(s.footprint, 'confidence', 1.0)
        if 0 < conf < 0.65:
            continue
            
        dist = haversine(lat, lon, s.footprint.centroid.lat, s.footprint.centroid.lon)
        # Default to centroid distance
        s._distance = dist
        
        # --- Metadata Matching Bonus ---
        # Use unidecode transliteration so Thai/Chinese/Arabic/Vietnamese
        # names are converted to ASCII before comparison.
        matched_bonus = 0.0
        b_name_raw = (getattr(s.footprint, 'name', '') or "")
        b_addr_raw = (getattr(s.footprint, 'address', '') or "")
        b_aliases_raw = [a for a in getattr(s.footprint, 'name_aliases', []) if a]

        # Transliterate everything to ASCII for cross-script matching
        req_name_t = _transliterate(req_name) if req_name else ""
        req_addr_t = _transliterate(req_address) if req_address else ""
        b_name_t = _transliterate(b_name_raw) if b_name_raw else ""
        b_addr_t = _transliterate(b_addr_raw) if b_addr_raw else ""
        b_alias_ts = [_transliterate(a) for a in b_aliases_raw]

        # Name matching: substring check + token overlap on transliterated text
        name_matched = False
        if req_name_t and b_name_t:
            if (req_name_t in b_name_t or b_name_t in req_name_t
                    or _token_overlap_score(req_name_t, b_name_t) >= 0.5):
                name_matched = True
        if not name_matched and req_name_t:
            for alias_t in b_alias_ts:
                if (req_name_t in alias_t or alias_t in req_name_t
                        or _token_overlap_score(req_name_t, alias_t) >= 0.5):
                    name_matched = True
                    break
        if name_matched:
            matched_bonus += 200.0  # Massive bonus for matching name

        # Address matching: substring check + token overlap on transliterated text
        if req_addr_t and b_addr_t:
            if (req_addr_t in b_addr_t or b_addr_t in req_addr_t
                    or _token_overlap_score(req_addr_t, b_addr_t) >= 0.5):
                matched_bonus += 100.0
            
        if shapely_available:
            try:
                wkt_data = s.footprint.footprint_wkt
                if wkt_data and wkt_data.startswith("{"):
                    import ast
                    from shapely.geometry import shape
                    poly = shape(ast.literal_eval(wkt_data))
                else:
                    poly = load_wkt(wkt_data)

                if poly.contains(query_point):
                    # Point is exactly inside this building footprint
                    base_dist = 0.0
                else:
                    # Point is not inside, but we can measure distance to the polygon edge
                    poly_dist_m = poly.distance(query_point) * 111320.0
                    
                    # Gravity model for un-contained points: give large buildings a larger "capture radius"
                    import math
                    equiv_radius = math.sqrt(s.footprint.area_m2 / math.pi)
                    base_dist = max(0.0, poly_dist_m - equiv_radius)
                    base_dist = min(dist, base_dist)
                    
                s._distance = base_dist - matched_bonus
                    
            except Exception as e:
                logger.warning(f"Could not parse WKT or check containment: {e}")
                s._distance = dist - matched_bonus
        else:
            s._distance = dist - matched_bonus
                
        # Fallback distance check if point is not inside any polygon
        # But if it matched metadata, NEVER reject it via distance.
        if radius_m <= 100 and s._distance > 100 and matched_bonus == 0:
            continue
            
        filtered_structures.append(s)

    filtered_structures.sort(key=lambda x: getattr(x, '_distance', 9999))
    structures = filtered_structures
    logger.info(f"Kept {len(structures)} buildings after confidence and spatial filtering")
    
    # Generate a dummy tile_id based on centroid
    tile_id = f"tile_{lat:.4f}_{lon:.4f}"
    
    cluster = BuildingCluster(
        tile_id=tile_id,
        bounds=bbox,
        buildings=structures
    )
    
    # 3. Create BuildingAdjustedSurface for each building (Gap S)
    # We need ground elevation for each building centroid.
    # OpenBuildingsSource provides height_m (building height), not ground elevation.
    # So we fetch ground elevation from DEM.

    async def _fetch_elev(building):
        centroid = building.footprint.centroid
        elev = await get_elevation(centroid.lat, centroid.lon)
        return building.footprint.building_id, elev

    # Parallel elevation fetches — all buildings in same area share the same DEM tile
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
