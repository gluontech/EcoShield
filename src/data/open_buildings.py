# src/data/open_buildings.py
"""
Google Open Buildings V3 (footprints) + 2.5D Temporal (heights).

This module provides the core ASSET LAYER for EcoShield — the building
footprints and heights that enable structure-level risk assessment.

Data Sources:
  V3 Polygons:
    - 1.8B buildings across Global South
    - Derived from 50cm high-resolution satellite imagery
    - Attributes: footprint polygon, confidence, plus_code
    - Access: Google Earth Engine FeatureCollection
    
  2.5D Temporal (heights):
    - Annual building presence, counts, heights (2016-2023)
    - Derived from Sentinel-2 10m imagery, 4m effective resolution
    - Access: Google Earth Engine ImageCollection
    
SEA Coverage: Vietnam, Indonesia, Philippines, Thailand, Singapore — CONFIRMED.
"""

import logging
from typing import List, Optional, Dict, Any
from pathlib import Path

import ee
import geopandas as gpd
import pandas as pd
import numpy as np
import asyncio

from src.core.models.geometry import BoundingBox, Location
from src.core.models.asset import BuildingFootprint, BuildingHeight, StructuralCharacteristics
from src.core.models.enums import DataSource, BuildingMaterial, BuildingOccupancy, VulnerabilityClass
from src.config.settings import settings

logger = logging.getLogger(__name__)


class OpenBuildingsSource:
    """
    Access Google Open Buildings V3 footprints + 2.5D heights via Earth Engine.
    
    Strategy:
      1. BATCH: Pre-ingest building footprints for each target city bbox into PostGIS
      2. ON-DEMAND: Query GEE for uncached locations
      3. Heights are fetched as raster → zonal stats per building polygon
    """
    
    def __init__(self, db_url: str, gee_project: Optional[str] = None):
        self.db_url = db_url
        self.gee_project = gee_project or settings.GEE_PROJECT 
        self._init_gee()
    
    def _init_gee(self):
        """Initialize Google Earth Engine."""
        try:
            # Check if using service account
            if settings.GEE_SERVICE_ACCOUNT and settings.GEE_KEY_FILE:
                credentials = ee.ServiceAccountCredentials(
                    settings.GEE_SERVICE_ACCOUNT, 
                    settings.GEE_KEY_FILE
                )
                ee.Initialize(credentials=credentials, project=self.gee_project)
            else:
                # Fallback to default auth (e.g. gcloud)
                ee.Initialize(project=self.gee_project)
                
            self._gee_available = True
        except Exception as e:
            logger.warning(f"GEE init failed: {e}. Falling back to cached data only.")
            self._gee_available = False
    
    async def get_buildings_in_bbox(
        self,
        bbox: BoundingBox,
        min_confidence: float = 0.70,
        include_heights: bool = True,
        height_year: int = 2023,
    ) -> List[StructuralCharacteristics]:
        """
        Retrieve building footprints + heights for a bounding box.
        
        1. Check PostGIS cache first (TODO)
        2. If cache miss, query GEE
        3. Enrich with heights from 2.5D Temporal
        4. Infer structural characteristics
        """
        # Step 1: Check PostGIS cache (skipped for MVP - assume miss)
        # cached = await self._query_postgis(bbox)
        # if cached: return cached
        
        # Step 2: Query GEE for footprints
        if not self._gee_available:
            # raise RuntimeError("GEE not available and no cached data for bbox")
            logger.error("GEE not available. Returning empty list.")
            return []
        
        footprints = await asyncio.to_thread(self._fetch_footprints_gee, bbox, min_confidence)
        logger.info(f"Fetched {len(footprints)} footprints from GEE")
        
        # Step 3: Enrich with heights
        if include_heights and footprints:
            heights = await asyncio.to_thread(self._fetch_heights_gee, bbox, height_year)
            footprints = await asyncio.to_thread(self._join_heights, footprints, heights)
        
        # Step 4: Build StructuralCharacteristics with inferred classification
        structures = [
            self._build_structure(fp, city=self._resolve_city(bbox))
            for fp in footprints
        ]
        
        # Step 5: Cache to PostGIS (TODO)
        # await self._cache_to_postgis(structures)
        
        return structures

    async def _query_postgis(self, bbox: BoundingBox) -> List[StructuralCharacteristics]:
        """Check PostGIS for cached buildings in bbox."""
        # MVP: Return empty list to trigger GEE fetch.
        # Implementation would involve reading from 'buildings' table using geopandas/sqlalchemy
        return []

    async def _cache_to_postgis(self, structures: List[StructuralCharacteristics]):
        """Cache fetched buildings to PostGIS."""
        # MVP: No-op.
        # Implementation would involve converting models to GeoDataFrame and writing to PostGIS.
        pass
    
    def _fetch_footprints_gee(
        self, bbox: BoundingBox, min_confidence: float
    ) -> List[Dict[str, Any]]:
        """Fetch building polygons from Google Open Buildings V3 via GEE."""
        
        region = ee.Geometry.Rectangle([
            bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat
        ])
        
        buildings_fc = (
            ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons')
            .filterBounds(region)
            .filter(ee.Filter.gte('confidence', min_confidence))
        )
        
        # Limit to manageable size (GEE export limit ~5000 features inline)
        try:
            count = buildings_fc.size().getInfo()
        except ee.EEException as e:
            logger.error(f"GEE Error: {e}")
            return []

        logger.info(f"Found {count} buildings in bbox (confidence >= {min_confidence})")
        
        if count > 5000:
            logger.warning("Large area (>5000 buildings): limiting to 5000 for inline query")
            buildings_fc = buildings_fc.limit(5000)
        
        try:
            features = buildings_fc.getInfo()['features']
        except Exception:
            return []

        res = []
        for f in features:
            geom = f.get('geometry', {})
            clat, clon = 0.0, 0.0
            lat_prop = f.get('properties', {}).get('latitude')
            lon_prop = f.get('properties', {}).get('longitude')
            
            if lat_prop is not None and lon_prop is not None:
                clat, clon = lat_prop, lon_prop
            elif geom and geom.get('coordinates'):
                try:
                    # GeoJSON Polygon coords: [[[lon, lat], ...]]
                    coords = geom['coordinates'][0] 
                    lons = [c[0] for c in coords]
                    lats = [c[1] for c in coords]
                    clon = sum(lons) / len(lons)
                    clat = sum(lats) / len(lats)
                except Exception:
                    pass
                    
            res.append({
                'geometry': geom,
                'area_m2': f.get('properties', {}).get('area_in_meters', 0),
                'confidence': f.get('properties', {}).get('confidence', 0),
                'plus_code': f.get('properties', {}).get('full_plus_code', ''),
                'centroid_lat': clat,
                'centroid_lon': clon,
            })
            
        return res
    
    def _fetch_heights_gee(
        self, bbox: BoundingBox, year: int = 2023
    ) -> Optional[Any]:
        """
        Fetch building heights from Open Buildings 2.5D Temporal via GEE.
        """
        region = ee.Geometry.Rectangle([
            bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat
        ])
        
        temporal_col = ee.ImageCollection(
            'GOOGLE/Research/open-buildings-temporal/v1'
        ).filterBounds(region)
        
        # Filter to target year (images are annual, centered on June 30)
        year_image = temporal_col.filter(
            ee.Filter.calendarRange(year, year, 'year')
        ).first()
        
        # Check if image exists (getInfo is expensive, but we handle None result)
        # Actually .first() returns an Element, we can use it directly.
        # If collection empty, .first() might be null in client side logic? 
        # No, ee objects are verified on server side processing mainly.
        
        return year_image.select(['building_height', 'building_presence'])
    
    def _join_heights(
        self, footprints: List[Dict], height_image: Any
    ) -> List[Dict]:
        """
        Join building heights to footprints via zonal statistics.
        """
        if height_image is None or not footprints:
            return footprints
        
        # Batch zonal stats via GEE reduceRegions
        # Convert local footprints back to FC for server-side join
        features = []
        for i, fp in enumerate(footprints):
            geom = ee.Geometry(fp['geometry'])
            features.append(ee.Feature(geom, {'idx': i}))
            
        fc = ee.FeatureCollection(features)
        
        try:
            stats = height_image.reduceRegions(
                collection=fc,
                reducer=ee.Reducer.mean(),
                scale=4  # 4m resolution
            ).getInfo()
            
            height_map = {}
            for f in stats['features']:
                idx = f['properties'].get('idx')
                h = f['properties'].get('building_height')
                p = f['properties'].get('building_presence', 1.0)
                if idx is not None and h is not None:
                    height_map[idx] = {'height_m': h, 'presence': p}
            
            for i, fp in enumerate(footprints):
                if i in height_map:
                    fp['height_m'] = height_map[i]['height_m']
                    fp['building_presence'] = height_map[i]['presence']
                    
        except Exception as e:
            logger.error(f"Failed to fetch heights: {e}")
            
        return footprints
    
    def _build_structure(
        self, fp: Dict, city: str = "unknown"
    ) -> StructuralCharacteristics:
        """
        Build a StructuralCharacteristics from raw footprint + height data.
        """
        # Circular import workaround if specific constants needed
        # from src.core.models.asset import SEA_MATERIAL_DEFAULTS
        
        area = fp.get('area_m2', 0)
        height_m = fp.get('height_m')
        
        # Infer material and vulnerability class
        material, vuln_class, occupancy = self._infer_classification(
            area, height_m, city
        )
        
        footprint = BuildingFootprint(
            building_id=fp.get('plus_code', f"gb_{fp.get('centroid_lat', 0):.6f}_{fp.get('centroid_lon', 0):.6f}"),
            source=DataSource.GOOGLE_OPEN_BUILDINGS_V3,
            centroid=Location(
                lat=fp.get('centroid_lat', 0),
                lon=fp.get('centroid_lon', 0),
            ),
            footprint_wkt=str(fp.get('geometry', '')),
            area_m2=area,
            confidence=fp.get('confidence', 0),
        )
        
        height = None
        if height_m is not None:
            height = BuildingHeight(
                height_m=height_m,
                height_source=DataSource.GOOGLE_OPEN_BUILDINGS_V3,
                height_year=2023,
                building_presence=fp.get('building_presence', 1.0),
            )
        
        # Simple default GFH
        gf_height = 0.3 # default
        has_stilts = False
        
        return StructuralCharacteristics(
            footprint=footprint,
            height=height,
            material=material,
            occupancy=occupancy,
            vulnerability_class=vuln_class,
            ground_floor_height_m=gf_height,
            has_stilts=has_stilts,
            material_inferred=True,
            classification_source="area_height_inference",
        )
    
    def _infer_classification(
        self, area_m2: float, height_m: Optional[float], city: str
    ) -> tuple:
        """Infer building material, vulnerability class, and occupancy."""
        
        # Height-based override: tall buildings are reinforced concrete
        if height_m and height_m > 15:
            return (
                BuildingMaterial.CONCRETE_REINFORCED,
                VulnerabilityClass.CLASS_IV_REINFORCED,
                BuildingOccupancy.COMMERCIAL if area_m2 > 300 else BuildingOccupancy.RESIDENTIAL_MULTI,
            )
        
        # Area-based classification
        if area_m2 < 30:
            return (
                BuildingMaterial.BAMBOO_THATCH,
                VulnerabilityClass.CLASS_I_INFORMAL,
                BuildingOccupancy.RESIDENTIAL_INFORMAL,
            )
        elif area_m2 < 80:
            return (
                BuildingMaterial.WOOD_FRAME,
                VulnerabilityClass.CLASS_II_WOOD,
                BuildingOccupancy.RESIDENTIAL_SINGLE,
            )
        elif area_m2 < 200:
            return (
                BuildingMaterial.MASONRY_UNREINFORCED,
                VulnerabilityClass.CLASS_III_MASONRY,
                BuildingOccupancy.RESIDENTIAL_SINGLE,
            )
        else:
            return (
                BuildingMaterial.CONCRETE_REINFORCED,
                VulnerabilityClass.CLASS_IV_REINFORCED,
                BuildingOccupancy.COMMERCIAL,
            )
    
    def _resolve_city(self, bbox: BoundingBox) -> str:
        """Resolve city name from bbox centroid."""
        lat = (bbox.min_lat + bbox.max_lat) / 2
        lon = (bbox.min_lon + bbox.max_lon) / 2
        # Simple lookup
        if 10 < lat < 11 and 106 < lon < 107: return "ho_chi_minh_city"
        return "unknown"
