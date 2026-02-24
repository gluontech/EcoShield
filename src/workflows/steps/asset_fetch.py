
import logging
from typing import Dict, Any, List

from src.core.models.geometry import BoundingBox
from src.core.models.surface import BuildingAdjustedSurface
from src.core.models.asset import BuildingCluster
from src.data.open_buildings import OpenBuildingsSource
from src.data.elevation import get_elevation
from src.config.settings import settings

logger = logging.getLogger(__name__)


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
            import asyncio
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
        matched_bonus = 0.0
        b_name = (getattr(s.footprint, 'name', '') or "").lower()
        b_addr = (getattr(s.footprint, 'address', '') or "").lower()
        
        # Exact/Substring match for Name
        if req_name and b_name and (req_name in b_name or b_name in req_name):
            matched_bonus += 200.0  # Massive bonus for matching name
            
        # Exact/Substring match for Address
        if req_address and b_addr and (req_address in b_addr or b_addr in req_address):
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
    
    surfaces = {}
    for b in structures:
        # Use simple centroid lookup. For optimization, we could batch this
        # or use a raster sampling method if get_elevation supported it.
        # For now, per-building await is slow but correct for MVP.
        # Ideally get_elevation should be cached or local.
        centroid = b.footprint.centroid
        
        # Note: In a high-concurrency event loop, calling get_elevation in a loop 
        # is okay if it's fast (local COG). 
        # Only fetch if we have buildings
        ground_elev = await get_elevation(centroid.lat, centroid.lon)
        
        bid = b.footprint.building_id
        surfaces[bid] = BuildingAdjustedSurface(
            building_id=bid,
            original_elevation_m=ground_elev,
            # Subsidence will be populated in Step 1
        )
        
    data["building_cluster"] = cluster
    data["building_surfaces"] = surfaces
    
    return data
