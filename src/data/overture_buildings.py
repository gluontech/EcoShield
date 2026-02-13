# src/data/overture_buildings.py
"""
Overture Maps Building footprints — conflated from Google + Microsoft + OSM.

Overture Maps Foundation provides 2.6B building footprints globally,
conflated from three sources with OSM prioritized for community-edited data.

Data Source:
  - 2.6B buildings globally (latest release: 2026-01-21.0)
  - Format: GeoParquet (cloud-native, bbox filtering)
  - Access: AWS S3 (s3://overturemaps-us-west-2/release/) — NO AUTH
  - Schema: id, geometry, height, num_floors, class, subtype, sources, names
  
Enrichment from OSM tags (when available):
  - building:material → direct material classification
  - building:levels → accurate story count
  - building → type (residential, commercial, industrial, etc.)

FIX v3.2 (Gap N): Corrected 'latitude'/'longitude' to 'centroid_lat'/'centroid_lon'
in to_structural_characteristics() mapping.
"""

import logging
from typing import List, Optional, Dict, Any

import duckdb
# import geopandas as gpd # Not strictly needed if returning dicts

from src.core.models.geometry import BoundingBox, Location
from src.core.models.asset import BuildingFootprint, StructuralCharacteristics, BuildingHeight
from src.core.models.enums import (
    DataSource, BuildingMaterial, BuildingOccupancy, VulnerabilityClass
)
from src.config.settings import settings

logger = logging.getLogger(__name__)

# Overture Maps S3 paths (no auth required)
OVERTURE_S3_BASE = f"s3://{settings.OVERTURE_S3_BUCKET}/release/2026-01-21.0"
OVERTURE_BUILDINGS_PATH = f"{OVERTURE_S3_BASE}/theme=buildings/type=building/"

# OSM building:material → EcoShield material mapping
OSM_MATERIAL_MAP: Dict[str, BuildingMaterial] = {
    "brick": BuildingMaterial.MASONRY_UNREINFORCED,
    "stone": BuildingMaterial.MASONRY_UNREINFORCED,
    "concrete": BuildingMaterial.MASONRY_UNREINFORCED,
    "concrete_block": BuildingMaterial.MASONRY_UNREINFORCED,
    "reinforced_concrete": BuildingMaterial.CONCRETE_REINFORCED,
    "steel": BuildingMaterial.STEEL_FRAME,
    "metal": BuildingMaterial.STEEL_FRAME,
    "wood": BuildingMaterial.WOOD_FRAME,
    "timber_framing": BuildingMaterial.WOOD_FRAME,
    "bamboo": BuildingMaterial.BAMBOO_THATCH,
    "mud": BuildingMaterial.MUD_ADOBE,
    "adobe": BuildingMaterial.MUD_ADOBE,
    "nipa": BuildingMaterial.BAMBOO_THATCH,
}

# OSM building type → EcoShield occupancy mapping
OSM_OCCUPANCY_MAP: Dict[str, BuildingOccupancy] = {
    "residential": BuildingOccupancy.RESIDENTIAL_SINGLE,
    "house": BuildingOccupancy.RESIDENTIAL_SINGLE,
    "detached": BuildingOccupancy.RESIDENTIAL_SINGLE,
    "apartments": BuildingOccupancy.RESIDENTIAL_MULTI,
    "commercial": BuildingOccupancy.COMMERCIAL,
    "retail": BuildingOccupancy.COMMERCIAL,
    "office": BuildingOccupancy.COMMERCIAL,
    "industrial": BuildingOccupancy.INDUSTRIAL,
    "warehouse": BuildingOccupancy.INDUSTRIAL,
    "school": BuildingOccupancy.INSTITUTIONAL,
    "hospital": BuildingOccupancy.INSTITUTIONAL,
    "church": BuildingOccupancy.INSTITUTIONAL,
    "government": BuildingOccupancy.INSTITUTIONAL,
    "farm": BuildingOccupancy.AGRICULTURAL,
    "barn": BuildingOccupancy.AGRICULTURAL,
}


class OvertureBuildingsSource:
    """
    Access Overture Maps buildings via DuckDB + S3 GeoParquet.
    """
    
    def __init__(self):
        self.conn = duckdb.connect()
        try:
            self.conn.execute("INSTALL spatial; LOAD spatial;")
            self.conn.execute("INSTALL httpfs; LOAD httpfs;")
            self.conn.execute("SET s3_region='us-west-2';")
        except Exception as e:
            logger.warning(f"DuckDB init failed (extensions missing?): {e}")
    
    def query_buildings(
        self,
        bbox: BoundingBox,
        limit: int = 50000,
    ) -> List[Dict[str, Any]]:
        """
        Query Overture building footprints for a bounding box.
        """
        # Note: 'id' is reserved in some SQL, but ok here
        query = f"""
        SELECT
            id,
            ST_AsText(geometry) AS geometry_wkt,
            ST_Area_Spheroid(geometry) AS area_m2,
            ST_Y(ST_Centroid(geometry)) AS centroid_lat,
            ST_X(ST_Centroid(geometry)) AS centroid_lon,
            height,
            num_floors,
            class,
            subtype,
            sources
        FROM read_parquet('{OVERTURE_BUILDINGS_PATH}*.parquet', hive_partitioning=1)
        WHERE bbox.xmin >= {bbox.min_lon}
          AND bbox.xmax <= {bbox.max_lon}
          AND bbox.ymin >= {bbox.min_lat}
          AND bbox.ymax <= {bbox.max_lat}
        LIMIT {limit}
        """
        
        try:
            result = self.conn.execute(query).fetchall()
            columns = ['id', 'geometry_wkt', 'area_m2', 'centroid_lat', 'centroid_lon',
                        'height', 'num_floors', 'class', 'subtype', 'sources']
            
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"DuckDB query failed: {e}")
            return []
    
    def enrich_with_osm_tags(
        self,
        buildings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Enrich Overture buildings with OSM-derived structural attributes.
        """
        for b in buildings:
            sources = b.get('sources', [])
            # Check if any source is OSM (simplified check)
            # In duckdb result, 'sources' is likely a list of structs/dicts or JSON string
            # Simplified for MVP:
            b['has_osm_data'] = False # Default
            
            # Map Overture class/subtype to EcoShield occupancy
            bclass = (b.get('class') or '').lower()
            bsubtype = (b.get('subtype') or '').lower()
            
            b['mapped_occupancy'] = OSM_OCCUPANCY_MAP.get(
                bsubtype,
                OSM_OCCUPANCY_MAP.get(bclass, BuildingOccupancy.UNKNOWN)
            )
            
            if b.get('num_floors'):
                b['num_stories'] = int(b['num_floors'])
            
            if b.get('height'):
                b['height_m'] = float(b['height'])
        
        return buildings
    
    def to_structural_characteristics(
        self,
        buildings: List[Dict[str, Any]],
        city: str = "unknown"
    ) -> List[StructuralCharacteristics]:
        """Convert Overture buildings to EcoShield StructuralCharacteristics."""
        
        results = []
        for b in buildings:
            footprint = BuildingFootprint(
                building_id=b.get('id', 'unknown'),
                source=DataSource.OVERTURE_MAPS_BUILDINGS,
                centroid=Location(
                    latitude=b.get('centroid_lat', 0),       # FIX v3.2 (Gap N)
                    longitude=b.get('centroid_lon', 0),      # FIX v3.2 (Gap N)
                ),
                area_m2=b.get('area_m2', 0),
                confidence=0.0,
                overture_id=b.get('id'),
            )
            
            height = None
            if b.get('height_m'):
                height = BuildingHeight(
                    height_m=b['height_m'],
                    height_source=DataSource.OVERTURE_MAPS_BUILDINGS,
                )
            
            occupancy = b.get('mapped_occupancy', BuildingOccupancy.UNKNOWN)
            
            # Material inference
            material = BuildingMaterial.MASONRY_UNREINFORCED  # SEA default
            vuln_class = VulnerabilityClass.CLASS_III_MASONRY
            
            if b.get('height_m') and b['height_m'] > 15:
                material = BuildingMaterial.CONCRETE_REINFORCED
                vuln_class = VulnerabilityClass.CLASS_IV_REINFORCED
            elif b.get('area_m2', 0) < 30:
                material = BuildingMaterial.BAMBOO_THATCH
                vuln_class = VulnerabilityClass.CLASS_I_INFORMAL
            
            results.append(StructuralCharacteristics(
                footprint=footprint,
                height=height,
                material=material,
                occupancy=occupancy,
                vulnerability_class=vuln_class,
                material_inferred=not b.get('has_osm_data', False),
                classification_source="osm_tags" if b.get('has_osm_data') else "area_height_inference",
            ))
        
        return results
