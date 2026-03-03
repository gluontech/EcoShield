from pathlib import Path
from src.config.settings import settings
from src.data.ingestion.nex_gddp_ingest import CITY_BBOXES
import numpy as np

CACHE = Path(settings.COPERNICUS_DEM_LOCAL_CACHE)
print("CACHE:", CACHE)

lat_min, lat_max, lon_min, lon_max = CITY_BBOXES["hcmc"]
print("BBOX:", lat_min, lat_max, lon_min, lon_max)

for lat in range(int(np.floor(lat_min)), int(np.ceil(lat_max))):
    for lon in range(int(np.floor(lon_min)), int(np.ceil(lon_max))):
        def _tile_key(lat: int, lon: int) -> str:
            lat_pfx = "N" if lat >= 0 else "S"
            lon_pfx = "E" if lon >= 0 else "W"
            name = f"Copernicus_DSM_COG_10_{lat_pfx}{abs(lat):02d}_00_{lon_pfx}{abs(lon):03d}_00_DEM"
            return f"{name}/{name}.tif"

        key = _tile_key(lat, lon)
        local = CACHE / key.split("/")[-1]
        print("Checking local path:", local)
        if local.exists():
            print("Exists!")
            continue
        print("Does not exist, would download", key)
