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
import overturemaps
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
OVERTURE_BUILDING_PARTS_PATH = f"{OVERTURE_S3_BASE}/theme=buildings/type=building_part/"
OVERTURE_PLACES_PATH = f"{OVERTURE_S3_BASE}/theme=places/type=place/"

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
        try:
            arrow_table = overturemaps.record_batch_reader("building", (bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat)).read_all()
        except Exception as e:
            logger.error(f"Overture Maps download failed: {e}")
            return []

        if arrow_table.num_rows == 0:
            return []

        query = f"""
        SELECT
            id,
            ST_AsText(ST_GeomFromWKB(geometry)) AS geometry_wkt,
            ST_Area_Spheroid(ST_GeomFromWKB(geometry)) AS area_m2,
            ST_Y(ST_Centroid(ST_GeomFromWKB(geometry))) AS centroid_lat,
            ST_X(ST_Centroid(ST_GeomFromWKB(geometry))) AS centroid_lon,
            height,
            num_floors,
            class,
            subtype,
            sources,
            names
        FROM arrow_table
        LIMIT {limit}
        """
        
        try:
            result = self.conn.execute(query).fetchall()
            columns = ['id', 'geometry_wkt', 'area_m2', 'centroid_lat', 'centroid_lon',
                        'height', 'num_floors', 'class', 'subtype', 'sources', 'names']
            
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"DuckDB query failed: {e}")
            return []
    
    def query_building_parts(
        self,
        bbox: BoundingBox,
        limit: int = 10000,
    ) -> List[Dict[str, Any]]:
        """
        Query Overture building_part polygons for complex structures.

        Building parts represent subdivisions of a parent building (e.g.
        podium vs tower). The spatial matcher prefers parts that contain
        the query point over the parent building polygon.
        """
        try:
            arrow_table = overturemaps.record_batch_reader("building_part", (bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat)).read_all()
        except Exception as e:
            logger.warning(f"Overture Maps download failed: {e}")
            return []

        if arrow_table.num_rows == 0:
            return []

        query = f"""
        SELECT
            id,
            ST_AsText(ST_GeomFromWKB(geometry)) AS geometry_wkt,
            ST_Area_Spheroid(ST_GeomFromWKB(geometry)) AS area_m2,
            ST_Y(ST_Centroid(ST_GeomFromWKB(geometry))) AS centroid_lat,
            ST_X(ST_Centroid(ST_GeomFromWKB(geometry))) AS centroid_lon,
            height,
            num_floors,
            building_id
        FROM arrow_table
        LIMIT {limit}
        """

        try:
            result = self.conn.execute(query).fetchall()
            columns = ['id', 'geometry_wkt', 'area_m2', 'centroid_lat', 'centroid_lon',
                        'height', 'num_floors', 'building_id']
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.warning(f"DuckDB building_part query failed (may not exist): {e}")
            return []

    def query_places(
        self,
        bbox: BoundingBox,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Query Overture places (POIs) for address + name enrichment.

        The places theme (theme=places/type=place) contains addresses and
        richer name data that the buildings theme lacks.
        """
        try:
            arrow_table = overturemaps.record_batch_reader("place", (bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat)).read_all()
        except Exception as e:
            logger.warning(f"Overture Maps download failed: {e}")
            return []

        if arrow_table.num_rows == 0:
            return []

        query = f"""
        SELECT
            id,
            ST_Y(ST_Centroid(ST_GeomFromWKB(geometry))) AS centroid_lat,
            ST_X(ST_Centroid(ST_GeomFromWKB(geometry))) AS centroid_lon,
            names,
            addresses,
            categories
        FROM arrow_table
        LIMIT {limit}
        """

        try:
            result = self.conn.execute(query).fetchall()
            columns = ['id', 'centroid_lat', 'centroid_lon', 'names',
                        'addresses', 'categories']
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.warning(f"Overture places query failed: {e}")
            return []

    def enrich_buildings_with_places(
        self,
        buildings: List[Dict[str, Any]],
        places: List[Dict[str, Any]],
        max_distance_m: float = 30.0,
    ) -> List[Dict[str, Any]]:
        """
        Match nearby places to buildings to add address + name data.

        For each building, find the closest place within max_distance_m and
        copy its address and any missing name aliases.
        """
        import math

        def _haversine(lat1, lon1, lat2, lon2):
            R = 6371000
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = (math.sin(dlat / 2) ** 2
                 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
                 * math.sin(dlon / 2) ** 2)
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        # Pre-extract place data
        parsed_places = []
        for p in places:
            pdata = {
                'lat': p.get('centroid_lat', 0),
                'lon': p.get('centroid_lon', 0),
            }

            # Parse address
            addrs = p.get('addresses')
            if addrs and isinstance(addrs, list) and len(addrs) > 0:
                addr_node = addrs[0]
                parts = []
                if isinstance(addr_node, dict):
                    if addr_node.get('freeform'):
                        parts.append(addr_node['freeform'])
                    else:
                        for k in ['housenumber', 'street', 'city']:
                            if addr_node.get(k):
                                parts.append(addr_node[k])
                pdata['address'] = ", ".join(parts) if parts else None
            else:
                pdata['address'] = None

            # Parse names
            pnames = p.get('names')
            pdata['name_primary'] = None
            pdata['name_aliases'] = []
            if pnames and isinstance(pnames, dict):
                pdata['name_primary'] = pnames.get('primary', '')
                common = pnames.get('common')
                if common and isinstance(common, dict):
                    pdata['name_aliases'] = [v for v in common.values() if v]

            parsed_places.append(pdata)

        # Match each building to the closest place
        for b in buildings:
            blat = b.get('centroid_lat', 0)
            blon = b.get('centroid_lon', 0)

            best_place = None
            best_dist = max_distance_m + 1

            for pp in parsed_places:
                d = _haversine(blat, blon, pp['lat'], pp['lon'])
                if d < best_dist:
                    best_dist = d
                    best_place = pp

            if best_place and best_dist <= max_distance_m:
                # Fill address from place if building has none
                if not b.get('address_primary') and best_place['address']:
                    b['address_primary'] = best_place['address']

                # Merge name aliases from place
                existing = set(b.get('name_aliases', []))
                for alias in best_place.get('name_aliases', []):
                    if alias and alias not in existing:
                        b.setdefault('name_aliases', []).append(alias)
                        existing.add(alias)

                # Fill primary name from place if building has none
                if not b.get('name_primary') and best_place.get('name_primary'):
                    b['name_primary'] = best_place['name_primary']

        return buildings

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
                
            # Extract common name if available (Overture names schema: STRUCT(primary VARCHAR, ...))
            # In duckdb, it comes out as a dict: {'primary': 'Hotel Name', 'common': {'en': '...', ...}}
            b['name_aliases'] = []
            if b.get('names') and isinstance(b['names'], dict):
                b['name_primary'] = b['names'].get('primary', '')
                # Extract common names in all available languages for cross-language matching
                common = b['names'].get('common')
                if common and isinstance(common, dict):
                    b['name_aliases'] = [v for v in common.values() if v]
            elif b.get('names') and isinstance(b['names'], str):
                b['name_primary'] = b['names']

            # Note: addresses come from Overture places theme (via enrich_buildings_with_places),
            # NOT from the buildings theme which lacks an 'addresses' column.

        return buildings
    
    def to_structural_characteristics(
        self,
        buildings: List[Dict[str, Any]],
        city: str = "unknown"
    ) -> List[StructuralCharacteristics]:
        """Convert Overture buildings to EcoShield StructuralCharacteristics."""
        
        results = []
        import math
        for b in buildings:
            area = b.get('area_m2', 1.0)
            geometry_wkt = b.get('geometry_wkt')
            
            # Approximate area calculation if duckdb returned NaN
            if (area is None or math.isnan(area) or area <= 0.0) and geometry_wkt:
                try:
                    from shapely.wkt import loads as load_wkt
                    poly = load_wkt(geometry_wkt)
                    # Rough conversion factor from dec degrees squared to sq meters
                    # lat ~ 111320m, lon ~ 111320m * cos(lat)
                    clat = b.get('centroid_lat', 0)
                    lon_to_m = 111320.0 * math.cos(math.radians(clat))
                    area = poly.area * (111320.0 * lon_to_m)
                except Exception:
                    area = 1.0
            
            if area is None or math.isnan(area) or area <= 0:
                area = 1.0
                
            footprint = BuildingFootprint(
                building_id=b.get('id', 'unknown'),
                source=DataSource.OVERTURE_MAPS_BUILDINGS,
                centroid=Location(
                    lat=b.get('centroid_lat', 0),       # FIX v3.2 (Gap N)
                    lon=b.get('centroid_lon', 0),      # FIX v3.2 (Gap N)
                ),
                area_m2=area,
                footprint_wkt=geometry_wkt,
                confidence=0.0,
                overture_id=b.get('id'),
                name=b.get('name_primary'),
                address=b.get('address_primary'),
                name_aliases=b.get('name_aliases', []),
            )

            # Resolve height: prefer direct height_m, else estimate from num_floors
            num_floors_val = b.get('num_stories')  # set from num_floors in enrich step
            height_m_val = b.get('height_m')

            if not height_m_val and num_floors_val:
                height_m_val = num_floors_val * 3.0  # estimate 3m per floor for SEA

            height = None
            if height_m_val:
                height = BuildingHeight(
                    height_m=height_m_val,
                    height_source=DataSource.OVERTURE_MAPS_BUILDINGS,
                    num_floors=num_floors_val,
                )

            occupancy = b.get('mapped_occupancy', BuildingOccupancy.UNKNOWN)

            # Material inference — uses height and footprint area.
            # Priority: height > 15m OR large footprint (> 1000 m²) → reinforced
            # concrete, since SEA commercial/industrial structures of that scale
            # almost always use RC framing.  Tiny footprints (< 30 m²) are
            # informal bamboo/thatch.  Everything else defaults to masonry.
            material = BuildingMaterial.MASONRY_UNREINFORCED  # SEA default
            vuln_class = VulnerabilityClass.CLASS_III_MASONRY

            effective_area = b.get('area_m2', 0) or 0

            if height_m_val and height_m_val > 15:
                material = BuildingMaterial.CONCRETE_REINFORCED
                vuln_class = VulnerabilityClass.CLASS_IV_REINFORCED
            elif effective_area > 1000:
                # Large-footprint structures (malls, warehouses, factories)
                material = BuildingMaterial.CONCRETE_REINFORCED
                vuln_class = VulnerabilityClass.CLASS_IV_REINFORCED
            elif effective_area < 30:
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
