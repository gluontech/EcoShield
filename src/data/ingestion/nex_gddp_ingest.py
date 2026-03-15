# src/data/ingestion/nex_gddp_ingest.py
"""
Batch ingest NEX-GDDP-CMIP6 data from AWS S3.

Downloads annual NetCDF files for configured models, variables,
scenarios, and city bounding boxes.
"""

import argparse
from pathlib import Path
from typing import List

import boto3
import xarray as xr
from botocore import UNSIGNED
from botocore.config import Config

from src.config.settings import settings

S3_BUCKET = settings.NEX_GDDP_S3_BUCKET
CACHE = Path(settings.NEX_GDDP_LOCAL_CACHE)

# Target cities with bounding boxes (lat_min, lat_max, lon_min, lon_max)
# MVP: Vietnam Cities Only
CITY_BBOXES = {
    "hcmc": (10.3, 11.2, 106.3, 107.1),
    "hanoi": (20.8, 21.2, 105.7, 106.1),
    "da_nang": (15.8, 16.3, 107.9, 108.4),
    # "jakarta": (-6.6, -5.9, 106.4, 107.2),
    # "manila": (14.2, 14.9, 120.8, 121.2),
    # "bangkok": (13.5, 14.0, 100.3, 100.9),
    # "singapore": (1.1, 1.5, 103.6, 104.1),
}

MODELS = settings.NEX_GDDP_MODELS
VARIABLES = ["pr", "tas", "tasmax", "tasmin"]
SCENARIOS = ["historical", "ssp245", "ssp585"]
YEAR_RANGES = {
    "historical": range(2014, 2015), # MVP: Last year only
    "ssp245": range(2050, 2051),     # MVP: Mid-century snapshot
    "ssp585": range(2050, 2051),     # MVP: Mid-century snapshot
}


def _s3_key(model: str, scenario: str, variable: str, year: int) -> str:
    return (
        f"NEX-GDDP-CMIP6/{model}/{scenario}/r1i1p1f1/{variable}/"
        f"{variable}_day_{model}_{scenario}_r1i1p1f1_gn_{year}.nc"
    )


def ingest(cities: List[str], dry_run: bool = False):
    """Download NEX-GDDP files to local cache."""
    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))

    for model in MODELS:
        for scenario in SCENARIOS:
            for variable in VARIABLES:
                for year in YEAR_RANGES[scenario]:
                    key = _s3_key(model, scenario, variable, year)
                    local = CACHE / model / scenario / f"{variable}_{year}.nc"

                    if local.exists():
                        continue  # skip already cached

                    local.parent.mkdir(parents=True, exist_ok=True)

                    if dry_run:
                        print(f"[DRY RUN] s3://{S3_BUCKET}/{key} -> {local}")
                        continue

                    print(f"Downloading {key} ...")
                    try:
                        # Download full file
                        s3.download_file(S3_BUCKET, key, str(local))
                        
                        # --- Optimization: Crop to SEA Region & Delete Original ---
                        try:
                            # Define Vietnam-focused bounds
                            # Covers HCMC, Hanoi, Da Nang with buffer
                            
                            ds = xr.open_dataset(local)
                            
                            min_lon, max_lon = 100.0, 110.0
                            min_lat, max_lat = 8.0, 24.0
                            
                            # Check if 0-360 or -180-180
                            if ds.lon.max() > 180:
                                # Data is 0-360, query is 90-140 (ok)
                                pass
                            else:
                                # Data is -180-180, query is 90-140 (ok)
                                pass

                            ds_crop = ds.sel(
                                lat=slice(min_lat, max_lat), 
                                lon=slice(min_lon, max_lon)
                            )
                            
                            # Save crop to temp file then rename
                            crop_file = local.with_suffix(".crop.nc")
                            ds_crop.to_netcdf(crop_file)
                            ds.close()
                            
                            # Replace original with crop
                            local.unlink()
                            crop_file.rename(local)
                            
                            print(f"  Cropped to Vietnam region. Size: {local.stat().st_size / 1024 / 1024:.2f} MB")
                            
                        except Exception as e:
                            print(f"  WARN: Cropping failed (keeping full file): {e}")
                            
                    except Exception as e:
                        print(f"  WARN: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Updated default to reflect MVP cities
    parser.add_argument("--cities", nargs="+", default=["hcmc", "hanoi", "da_nang"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    ingest(args.cities, args.dry_run)
