
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
    
    # 2. Fetch buildings from source
    logger.info(f"Fetching buildings in bbox {bbox}...")
    structures = await asset_source.get_buildings_in_bbox(bbox)
    logger.info(f"Fetched {len(structures)} buildings")
    
    cluster = BuildingCluster(buildings=structures)
    
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
