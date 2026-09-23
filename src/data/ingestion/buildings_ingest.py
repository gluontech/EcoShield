# src/data/ingestion/buildings_ingest.py
"""
Batch ingest building footprints using OpenBuildingMap (OBM) dataset.

Target cities: HCMC, Hanoi, Da Nang, Jakarta, Manila, Bangkok, Singapore.
"""

import asyncio
import json
import logging

from src.config.settings import settings
from src.core.models.geometry import BoundingBox
from src.data.open_building_map import OpenBuildingMapSource

logger = logging.getLogger(__name__)

CITY_BBOXES = {
    "hcmc": BoundingBox(min_lat=10.3, max_lat=11.2, min_lon=106.3, max_lon=107.1),
    "hanoi": BoundingBox(min_lat=20.8, max_lat=21.2, min_lon=105.7, max_lon=106.1),
    "da_nang": BoundingBox(min_lat=15.8, max_lat=16.3, min_lon=107.9, max_lon=108.4),
    "jakarta": BoundingBox(min_lat=-6.35, max_lat=-6.05, min_lon=106.65, max_lon=107.00),
    "manila": BoundingBox(min_lat=14.45, max_lat=14.70, min_lon=120.90, max_lon=121.10),
    "bangkok": BoundingBox(min_lat=13.60, max_lat=13.90, min_lon=100.35, max_lon=100.70),
    "singapore": BoundingBox(min_lat=1.20, max_lat=1.47, min_lon=103.60, max_lon=104.05),
}


async def ingest_city_buildings(city: str, db_url: str = settings.DATABASE_URL) -> int:
    """Ingest all OpenBuildingMap buildings for a city."""
    bbox = CITY_BBOXES.get(city.lower())
    if not bbox:
        logger.warning(f"Unknown city: {city}")
        return 0

    logger.info(f"Starting OpenBuildingMap building ingest for {city}: {bbox}")
    obm_source = OpenBuildingMapSource(db_url=db_url)

    try:
        structures = await obm_source.get_buildings_in_bbox(bbox=bbox)
        logger.info(f"  OpenBuildingMap: {len(structures)} buildings retrieved for {city}")

        # Save to local cache directory
        output_dir = settings.BUILDINGS_PATH
        output_dir.mkdir(parents=True, exist_ok=True)

        if structures:
            combined_file = output_dir / f"{city}_combined_buildings.json"
            with open(combined_file, "w") as f:
                json.dump([s.model_dump() for s in structures], f, default=str)
            logger.info(f"  Saved {len(structures)} buildings for {city} to {combined_file}")

        return len(structures)
    except Exception as e:
        logger.error(f"OpenBuildingMap ingest failed for {city}: {e}")
        return 0


async def ingest_all_cities(db_url: str = settings.DATABASE_URL):
    """Ingest buildings for all target cities sequentially."""
    total = 0
    for city in CITY_BBOXES:
        count = await ingest_city_buildings(city, db_url)
        total += count
    logger.info(f"Total buildings ingested: {total}")


if __name__ == "__main__":
    import sys
    cities = sys.argv[1:] if len(sys.argv) > 1 else list(CITY_BBOXES.keys())
    for city in cities:
        asyncio.run(ingest_city_buildings(city))
