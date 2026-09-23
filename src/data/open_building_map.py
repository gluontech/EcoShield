# src/data/open_building_map.py
"""
OpenBuildingMap (OBM) dataset reader and asset layer provider.

Data publication:
  Oostwegel et al. (2025): Scientific Data / GFZ Potsdam.
  doi: 10.5880.GFZ.LKUT.2025.002
  License: ODbL v1.0

Features:
  - Conflates OpenStreetMap + Google Open Buildings + Microsoft ML Footprints.
  - Pre-classified GEM Building Taxonomy v2.0 occupancy and height/stories.
  - Quadkey Level-6 tile organization with Level-18 building Quadkeys.
  - Sub-50ms local spatial retrieval via PostGIS or GeoPackage SQLite.
"""

import asyncio
import logging
import math
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from src.config.settings import settings
from src.core.models.asset import (
    BuildingFootprint, BuildingHeight, StructuralCharacteristics,
)
from src.core.models.enums import (
    DataSource, BuildingMaterial, BuildingOccupancy, VulnerabilityClass,
)
from src.core.models.geometry import BoundingBox, Location
from src.data.quadkey_utils import get_quadkeys_for_bbox

logger = logging.getLogger(__name__)

# GEM Taxonomy Occupancy -> EcoShield BuildingOccupancy mapping
GEM_OCCUPANCY_MAP: Dict[str, BuildingOccupancy] = {
    "RES1": BuildingOccupancy.RESIDENTIAL_SINGLE,
    "RES2": BuildingOccupancy.RESIDENTIAL_MULTI,
    "RES3": BuildingOccupancy.RESIDENTIAL_INFORMAL,
    "RES": BuildingOccupancy.RESIDENTIAL_SINGLE,
    "INFORMAL": BuildingOccupancy.RESIDENTIAL_INFORMAL,
    "SHACK": BuildingOccupancy.RESIDENTIAL_INFORMAL,
    "COM": BuildingOccupancy.COMMERCIAL,
    "COM1": BuildingOccupancy.COMMERCIAL,
    "COM2": BuildingOccupancy.COMMERCIAL,
    "COM3": BuildingOccupancy.COMMERCIAL,
    "IND": BuildingOccupancy.INDUSTRIAL,
    "IND1": BuildingOccupancy.INDUSTRIAL,
    "IND2": BuildingOccupancy.INDUSTRIAL,
    "GOV": BuildingOccupancy.INSTITUTIONAL,
    "EDU": BuildingOccupancy.INSTITUTIONAL,
    "HEALTH": BuildingOccupancy.INSTITUTIONAL,
    "REL": BuildingOccupancy.INSTITUTIONAL,
    "ASS": BuildingOccupancy.INSTITUTIONAL,
    "AGR": BuildingOccupancy.AGRICULTURAL,
    "MIX": BuildingOccupancy.MIXED_USE,
    "UNK": BuildingOccupancy.UNKNOWN,
}

# GEM Taxonomy Material -> EcoShield BuildingMaterial & VulnerabilityClass
GEM_MATERIAL_MAP: Dict[str, Tuple[BuildingMaterial, VulnerabilityClass]] = {
    "CR": (BuildingMaterial.CONCRETE_REINFORCED, VulnerabilityClass.CLASS_IV_REINFORCED),
    "SRC": (BuildingMaterial.CONCRETE_REINFORCED, VulnerabilityClass.CLASS_IV_REINFORCED),
    "S": (BuildingMaterial.STEEL_FRAME, VulnerabilityClass.CLASS_IV_REINFORCED),
    "MUR": (BuildingMaterial.MASONRY_UNREINFORCED, VulnerabilityClass.CLASS_III_MASONRY),
    "MR": (BuildingMaterial.MASONRY_UNREINFORCED, VulnerabilityClass.CLASS_III_MASONRY),
    "W": (BuildingMaterial.WOOD_FRAME, VulnerabilityClass.CLASS_II_WOOD),
    "WWOOD": (BuildingMaterial.WOOD_FRAME, VulnerabilityClass.CLASS_II_WOOD),
    "BAM": (BuildingMaterial.BAMBOO_THATCH, VulnerabilityClass.CLASS_II_WOOD),
    "MUD": (BuildingMaterial.MUD_ADOBE, VulnerabilityClass.CLASS_I_INFORMAL),
    "ADOBE": (BuildingMaterial.MUD_ADOBE, VulnerabilityClass.CLASS_I_INFORMAL),
}

# Default material & vulnerability by occupancy when taxonomy lacks explicit material
DEFAULT_MATERIAL_BY_OCCUPANCY: Dict[BuildingOccupancy, Tuple[BuildingMaterial, VulnerabilityClass]] = {
    BuildingOccupancy.RESIDENTIAL_SINGLE: (BuildingMaterial.MASONRY_UNREINFORCED, VulnerabilityClass.CLASS_III_MASONRY),
    BuildingOccupancy.RESIDENTIAL_MULTI: (BuildingMaterial.CONCRETE_REINFORCED, VulnerabilityClass.CLASS_IV_REINFORCED),
    BuildingOccupancy.RESIDENTIAL_INFORMAL: (BuildingMaterial.MUD_ADOBE, VulnerabilityClass.CLASS_I_INFORMAL),
    BuildingOccupancy.COMMERCIAL: (BuildingMaterial.CONCRETE_REINFORCED, VulnerabilityClass.CLASS_IV_REINFORCED),
    BuildingOccupancy.INDUSTRIAL: (BuildingMaterial.STEEL_FRAME, VulnerabilityClass.CLASS_IV_REINFORCED),
    BuildingOccupancy.INSTITUTIONAL: (BuildingMaterial.CONCRETE_REINFORCED, VulnerabilityClass.CLASS_IV_REINFORCED),
    BuildingOccupancy.INFRASTRUCTURE: (BuildingMaterial.STEEL_FRAME, VulnerabilityClass.CLASS_IV_REINFORCED),
    BuildingOccupancy.AGRICULTURAL: (BuildingMaterial.WOOD_FRAME, VulnerabilityClass.CLASS_II_WOOD),
    BuildingOccupancy.MIXED_USE: (BuildingMaterial.CONCRETE_REINFORCED, VulnerabilityClass.CLASS_IV_REINFORCED),
    BuildingOccupancy.UNKNOWN: (BuildingMaterial.MASONRY_UNREINFORCED, VulnerabilityClass.CLASS_III_MASONRY),
}

SOURCE_ID_MAP: Dict[int, DataSource] = {
    0: DataSource.OPEN_BUILDING_MAP,       # OpenStreetMap
    1: DataSource.GOOGLE_OPEN_BUILDINGS_V3, # Google
    2: DataSource.OPEN_BUILDING_MAP,       # Microsoft
}


def parse_gem_occupancy(gem_str: Optional[str]) -> BuildingOccupancy:
    """Parse GEM Building Taxonomy occupancy tag into EcoShield BuildingOccupancy."""
    if not gem_str:
        return BuildingOccupancy.UNKNOWN
    clean = gem_str.strip().upper()
    for key, occ in GEM_OCCUPANCY_MAP.items():
        if key in clean:
            return occ
    return BuildingOccupancy.UNKNOWN


def parse_gem_height(height_str: Optional[str], default_floors: int = 1) -> Tuple[float, int]:
    """
    Parse GEM height string into (height_meters, num_floors).

    Examples:
      'HBET:1-3' -> (6.0, 2)
      'H:12'     -> (12.0, 4)
      '3'        -> (9.0, 3)
    """
    if not height_str:
        return (default_floors * 3.0, default_floors)

    raw = str(height_str).strip()

    # Match numeric meters e.g. H:15m or 15.5
    m_match = re.search(r'H:?\s*(\d+(?:\.\d+)?)m?', raw, re.IGNORECASE)
    if m_match:
        h = float(m_match.group(1))
        floors = max(1, int(round(h / 3.0)))
        return (h, floors)

    # Match story ranges e.g. HBET:1-3 or HBET:2
    range_match = re.search(r'HBET:?\s*(\d+)(?:-(\d+))?', raw, re.IGNORECASE)
    if range_match:
        low = int(range_match.group(1))
        high = int(range_match.group(2)) if range_match.group(2) else low
        floors = int((low + high) / 2)
        return (floors * 3.0, max(1, floors))

    # Single integer floor count
    if raw.isdigit():
        floors = max(1, int(raw))
        return (floors * 3.0, floors)

    return (default_floors * 3.0, default_floors)


def parse_gem_material(gem_str: Optional[str], occ: BuildingOccupancy) -> Tuple[BuildingMaterial, VulnerabilityClass]:
    """Extract structural material & vulnerability class from GEM taxonomy tag or occupancy default."""
    if gem_str:
        clean = gem_str.strip().upper()
        for key, (mat, vul) in GEM_MATERIAL_MAP.items():
            if f"MAT:{key}" in clean or f"/{key}" in clean:
                return mat, vul

    return DEFAULT_MATERIAL_BY_OCCUPANCY.get(occ, (BuildingMaterial.MASONRY_UNREINFORCED, VulnerabilityClass.CLASS_III_MASONRY))


class OpenBuildingMapSource:
    """
    Access OpenBuildingMap footprints & GEM metadata via local GeoPackage or PostGIS.
    """

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        db_url: Optional[str] = None,
        use_postgis: bool = True,
    ):
        self.data_dir = data_dir or settings.OBM_DATA_PATH
        self.db_url = db_url or settings.DATABASE_URL
        self.use_postgis = use_postgis and getattr(settings, "OBM_USE_POSTGIS", True)

    async def get_buildings_in_bbox(
        self,
        bbox: BoundingBox,
        limit: int = 50000,
    ) -> List[StructuralCharacteristics]:
        """
        Retrieve building footprints and structural characteristics inside bounding box.
        """
        # Step 1: Attempt PostGIS query if enabled
        if self.use_postgis and self.db_url:
            try:
                results = await self._query_postgis(bbox, limit)
                if results:
                    logger.info(f"Retrieved {len(results)} buildings from PostGIS obm_buildings")
                    return results
            except Exception as e:
                err_msg = str(e)
                if "password authentication failed" in err_msg.lower() or "invalidpassworderror" in err_msg.lower():
                    logger.error(
                        f"PostGIS authentication error: {e}. "
                        "If using Docker, ensure database credentials match .env or re-initialize volume via `docker compose down -v`."
                    )
                else:
                    logger.warning(f"PostGIS OBM query failed ({e}); falling back to local GeoPackage files.")

        # Step 2: Query local GeoPackage SQLite files
        gpkg_results = await asyncio.to_thread(self._query_geopackage_files, bbox, limit)
        if gpkg_results:
            logger.info(f"Retrieved {len(gpkg_results)} buildings from local OpenBuildingMap GeoPackage files")
            return gpkg_results

        # Step 3: Fallback check for cached city JSON files
        json_results = await asyncio.to_thread(self._query_cached_json, bbox, limit)
        if json_results:
            logger.info(f"Retrieved {len(json_results)} buildings from cached city JSON files")
            return json_results

        logger.warning(f"No OpenBuildingMap footprints found for bbox: {bbox}")
        return []

    async def ensure_schema(self, conn=None) -> None:
        """Ensure PostGIS extension and obm_buildings table exist."""
        import asyncpg
        should_close = False
        if conn is None:
            clean_url = self.db_url.replace("postgresql+asyncpg://", "postgresql://")
            conn = await asyncpg.connect(clean_url, timeout=10.0)
            should_close = True

        try:
            await conn.execute("""
                CREATE EXTENSION IF NOT EXISTS postgis;
                CREATE TABLE IF NOT EXISTS obm_buildings (
                    id BIGINT PRIMARY KEY,
                    occupancy TEXT,
                    height TEXT,
                    floorspace REAL,
                    quadkey TEXT,
                    source_id INT,
                    geom geometry(Polygon, 4326)
                );
                CREATE INDEX IF NOT EXISTS idx_obm_buildings_geom ON obm_buildings USING GIST (geom);
            """)
            logger.info("Ensured PostGIS extension and obm_buildings schema.")
        finally:
            if should_close:
                await conn.close()

    async def _query_postgis(self, bbox: BoundingBox, limit: int) -> List[StructuralCharacteristics]:
        """Query spatial features from PostGIS table obm_buildings."""
        import asyncpg

        # Parse postgres connection string from db_url
        clean_url = self.db_url.replace("postgresql+asyncpg://", "postgresql://")
        try:
            conn = await asyncpg.connect(clean_url, timeout=10.0)
        except asyncpg.InvalidPasswordError as exc:
            logger.error(f"PostgreSQL authentication failed for DSN: {clean_url.split('@')[-1] if '@' in clean_url else '***'}")
            raise RuntimeError(f"PostGIS authentication failed for user 'ecoshield': {exc}") from exc
        except Exception as exc:
            logger.warning(f"PostgreSQL connection failed: {exc}")
            raise

        try:
            query = """
                SELECT id, occupancy, height, floorspace, quadkey, source_id,
                       ST_AsText(geom) as wkt,
                       ST_Y(ST_Centroid(geom)) as lat,
                       ST_X(ST_Centroid(geom)) as lon,
                       ST_Area(geom::geography) as area_m2
                FROM obm_buildings
                WHERE geom && ST_MakeEnvelope($1, $2, $3, $4, 4326)
                LIMIT $5
            """
            try:
                rows = await conn.fetch(query, bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat, limit)
            except asyncpg.UndefinedTableError:
                logger.warning("Table 'obm_buildings' missing in PostGIS. Auto-creating schema...")
                await self.ensure_schema(conn)
                rows = await conn.fetch(query, bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat, limit)

            results = []
            for row in rows:
                sc = self._row_to_structural_characteristics(dict(row))
                if sc:
                    results.append(sc)
            return results
        finally:
            await conn.close()

    def _query_geopackage_files(self, bbox: BoundingBox, limit: int) -> List[StructuralCharacteristics]:
        """Query Level-6 Quadkey GeoPackage SQLite files in local data_dir."""
        if not self.data_dir.exists():
            return []

        quadkeys = get_quadkeys_for_bbox(
            min_lat=bbox.min_lat, max_lat=bbox.max_lat,
            min_lon=bbox.min_lon, max_lon=bbox.max_lon, zoom=6
        )

        results = []
        for qk in quadkeys:
            if len(results) >= limit:
                break

            # Find matching file e.g. building.132212.gpkg or building.132212.gpkg.bz2
            gpkg_path = self.data_dir / f"building.{qk}.gpkg"
            if not gpkg_path.exists():
                candidates = list(self.data_dir.glob(f"*{qk}*.gpkg"))
                if candidates:
                    gpkg_path = candidates[0]
                else:
                    continue

            try:
                with sqlite3.connect(str(gpkg_path)) as conn:
                    cursor = conn.cursor()
                    # Query building table
                    cursor.execute("""
                        SELECT id, occupancy, height, floorspace, quadkey, source_id,
                               minx, miny, maxx, maxy
                        FROM Building
                        WHERE minx <= ? AND maxx >= ? AND miny <= ? AND maxy >= ?
                        LIMIT ?
                    """, (bbox.max_lon, bbox.min_lon, bbox.max_lat, bbox.min_lat, limit - len(results)))

                    rows = cursor.fetchall()
                    for r in rows:
                        b_id, occ, h_str, fs, qk18, src_id, minx, miny, maxx, maxy = r
                        centroid_lat = (miny + maxy) / 2.0
                        centroid_lon = (minx + maxx) / 2.0

                        # Compute approximate area in m2 if floorspace missing
                        area_m2 = float(fs) if fs and float(fs) > 0 else 100.0

                        row_dict = {
                            "id": b_id,
                            "occupancy": occ,
                            "height": h_str,
                            "floorspace": area_m2,
                            "quadkey": qk18,
                            "source_id": src_id,
                            "wkt": f"POLYGON(({minx} {miny}, {maxx} {miny}, {maxx} {maxy}, {minx} {maxy}, {minx} {miny}))",
                            "lat": centroid_lat,
                            "lon": centroid_lon,
                            "area_m2": area_m2,
                        }
                        sc = self._row_to_structural_characteristics(row_dict)
                        if sc:
                            results.append(sc)
            except Exception as e:
                logger.warning(f"Failed to query GeoPackage {gpkg_path}: {e}")

        return results

    def _query_cached_json(self, bbox: BoundingBox, limit: int) -> List[StructuralCharacteristics]:
        """Fallback querying cached city JSON files in buildings directory."""
        import json
        cache_dir = settings.BUILDINGS_PATH
        if not cache_dir.exists():
            return []

        results = []
        for json_file in cache_dir.glob("*combined_buildings.json"):
            try:
                with open(json_file, "r") as f:
                    data = json.load(f)
                    for item in data:
                        lat = item.get("centroid", {}).get("lat") or item.get("latitude")
                        lon = item.get("centroid", {}).get("lon") or item.get("longitude")
                        if lat and lon and (bbox.min_lat <= lat <= bbox.max_lat) and (bbox.min_lon <= lon <= bbox.max_lon):
                            # Re-instantiate StructuralCharacteristics model
                            sc = StructuralCharacteristics.model_validate(item)
                            results.append(sc)
                            if len(results) >= limit:
                                return results
            except Exception as e:
                logger.debug(f"Failed reading cache json {json_file}: {e}")
        return results

    def _row_to_structural_characteristics(self, row: Dict[str, Any]) -> Optional[StructuralCharacteristics]:
        """Convert raw building database row to StructuralCharacteristics model."""
        try:
            b_id = str(row["id"])
            occ_enum = parse_gem_occupancy(row.get("occupancy"))
            height_m, num_floors = parse_gem_height(row.get("height"))
            material, vul_class = parse_gem_material(row.get("height") or row.get("occupancy"), occ_enum)

            lat = float(row["lat"])
            lon = float(row["lon"])
            area_m2 = max(10.0, float(row.get("area_m2") or 100.0))
            wkt = row.get("wkt")

            src_id = int(row.get("source_id", 0))
            data_src = SOURCE_ID_MAP.get(src_id, DataSource.OPEN_BUILDING_MAP)

            footprint = BuildingFootprint(
                building_id=f"OBM_{b_id}",
                source=data_src,
                centroid=Location(lat=lat, lon=lon),
                footprint_wkt=wkt,
                area_m2=area_m2,
                confidence=0.90,
                osm_id=b_id if src_id == 0 else None,
            )

            b_height = BuildingHeight(
                height_m=height_m,
                height_source=DataSource.OPEN_BUILDING_MAP,
                num_floors=num_floors,
                estimated_stories=num_floors,
            )

            return StructuralCharacteristics(
                footprint=footprint,
                height=b_height,
                occupancy=occ_enum,
                material=material,
                vulnerability_class=vul_class,
                replacement_value_usd=round(area_m2 * num_floors * 650.0, 2),
            )
        except Exception as e:
            logger.debug(f"Row conversion failed: {e}")
            return None
