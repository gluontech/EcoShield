# src/data/ingestion/dem_ingest.py
"""
Batch ingest Copernicus GLO-30 DEM tiles from AWS S3.

Downloads 1°x1° COG tiles covering configured city bounding boxes.
"""

import argparse
from pathlib import Path

import numpy as np
import boto3
from botocore import UNSIGNED
from botocore.config import Config

from src.config.settings import settings


S3_BUCKET = settings.COPERNICUS_DEM_S3_BUCKET
CACHE = Path(settings.COPERNICUS_DEM_LOCAL_CACHE)
CACHE.mkdir(parents=True, exist_ok=True)

# Reuse city bboxes from nex_gddp_ingest
from src.data.ingestion.nex_gddp_ingest import CITY_BBOXES


def _tile_key(lat: int, lon: int) -> str:
    """Build S3 key for a Copernicus GLO-30 tile."""
    lat_pfx = "N" if lat >= 0 else "S"
    lon_pfx = "E" if lon >= 0 else "W"
    name = f"Copernicus_DSM_COG_10_{lat_pfx}{abs(lat):02d}_00_{lon_pfx}{abs(lon):03d}_00_DEM"
    return f"{name}/{name}.tif"


def ingest(cities: list[str], dry_run: bool = False):
    """Download DEM tiles for target cities."""
    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))

    for city in cities:
        if city not in CITY_BBOXES:
            print(f"WARN: unknown city {city}")
            continue

        lat_min, lat_max, lon_min, lon_max = CITY_BBOXES[city]

        for lat in range(int(np.floor(lat_min)), int(np.ceil(lat_max))):
            for lon in range(int(np.floor(lon_min)), int(np.ceil(lon_max))):
                key = _tile_key(lat, lon)
                local = CACHE / key.split("/")[-1]

                if local.exists():
                    continue

                if dry_run:
                    print(f"[DRY RUN] s3://{S3_BUCKET}/{key} -> {local}")
                    continue

                print(f"Downloading {key} ...")
                try:
                    s3.download_file(S3_BUCKET, key, str(local))
                        
                except Exception as e:
                    print(f"  WARN: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cities", nargs="+", default=["hcmc"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    ingest(args.cities, args.dry_run)
