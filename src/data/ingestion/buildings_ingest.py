# src/data/ingestion/buildings_ingest.py
"""
Batch ingest building footprints for all target cities.

Strategy:
  1. Google Open Buildings V3: Fetch via GEE
  2. Overture Maps: Fetch via DuckDB
  3. Merge and classify (TODO: full merge logic)
  4. Load into local cache/DB

Target cities: HCMC, Hanoi, Da Nang, Jakarta, Manila, Bangkok, Singapore.
"""

import asyncio
import logging
from typing import List
from pathlib import Path

from src.core.models.geometry import BoundingBox
from src.data.open_buildings import OpenBuildingsSource
from src.data.overture_buildings import OvertureBuildingsSource
from src.config.settings import settings

logger = logging.getLogger(__name__)

# City bounding boxes (same as in other ingest scripts)
CITY_BBOXES = {
    # Aligned with src/data/ingestion/nex_gddp_ingest.py
    "hcmc": BoundingBox(min_lat=10.3, max_lat=11.2, min_lon=106.3, max_lon=107.1),
    "hanoi": BoundingBox(min_lat=20.8, max_lat=21.2, min_lon=105.7, max_lon=106.1),
    "da_nang": BoundingBox(min_lat=15.8, max_lat=16.3, min_lon=107.9, max_lon=108.4),
    
    # "jakarta": BoundingBox(min_lat=-6.35, max_lat=-6.05, min_lon=106.65, max_lon=107.00),
    # "manila": BoundingBox(min_lat=14.45, max_lat=14.70, min_lon=120.90, max_lon=121.10),
    # "bangkok": BoundingBox(min_lat=13.60, max_lat=13.90, min_lon=100.35, max_lon=100.70),
    # "singapore": BoundingBox(min_lat=1.20, max_lat=1.47, min_lon=103.60, max_lon=104.05),
}


async def ingest_city_buildings(city: str, db_url: str = "sqlite:///:memory:") -> int:
    """
    Ingest all buildings for a city.
    """
    bbox = CITY_BBOXES.get(city)
    if not bbox:
        logger.warning(f"Unknown city: {city}")
        return 0
        
    logger.info(f"Starting building ingest for {city}: {bbox}")
    
    # Step 1: Google Open Buildings
    # For ingestion script, we might want to bypass DB URL requirement or use a real one
    # Here we mock it or pass a dummy one if class requires it
    google_src = OpenBuildingsSource(db_url=db_url)
    try:
        structures = await google_src.get_buildings_in_bbox(
            bbox=bbox,
            min_confidence=0.65,
            include_heights=True,
            height_year=2023,
        )
        logger.info(f"  Google: {len(structures)} buildings")
    except Exception as e:
        logger.error(f"  Google ingest failed: {e}")
        structures = []

    # Step 2: Overture Maps
    try:
        overture_src = OvertureBuildingsSource()
        overture_raw = overture_src.query_buildings(bbox=bbox, limit=10000) # Limit for MVP
        overture_enriched = overture_src.enrich_with_osm_tags(overture_raw)
        logger.info(f"  Overture: {len(overture_enriched)} buildings")
    except Exception as e:
        logger.error(f"  Overture ingest failed: {e}")
        overture_enriched = []
    
    # Step 3: Merge/Save
    # Save to local cache for MVP
    output_dir = settings.BUILDINGS_PATH
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save Google Buildings
    if structures:
        # Pydantic serialization
        google_file = output_dir / f"{city}_google_buildings.json"
        with open(google_file, "w") as f:
            # List of models -> json
            f.write("[" + ",".join([s.model_dump_json() for s in structures]) + "]")
            
    # Save Overture Buildings
    if overture_enriched:
        overture_file = output_dir / f"{city}_overture_buildings.json"
        import json
        with open(overture_file, "w") as f:
            # List of dicts -> json
            # Handle potential non-serializable types if any (datetime?)
            # Overture dicts are simple types mostly
            json.dump(overture_enriched, f, default=str)
            
    total = len(structures) + len(overture_enriched)
    logger.info(f"  Ingested {total} buildings for {city}. Saved to {output_dir}")
    return total


async def ingest_all_cities(db_url: str):
    """Ingest buildings for all target cities sequentially."""
    total = 0
    for city in CITY_BBOXES:
        count = await ingest_city_buildings(city, db_url)
        total += count
    logger.info(f"Total buildings ingested: {total}")

if __name__ == "__main__":
    import sys
    # Simple CLI
    if len(sys.argv) > 1:
        cities = sys.argv[1:]
    else:
        cities = list(CITY_BBOXES.keys())
        
    for city in cities:
        asyncio.run(ingest_city_buildings(city))
