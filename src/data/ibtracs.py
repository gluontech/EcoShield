# src/data/ibtracs.py
"""
IBTrACS (International Best Track Archive) Cyclone Database.

Data Source : NOAA NCEI
              https://www.ncei.noaa.gov/products/international-best-track-archive
API         : Direct CSV download via HTTPS (no auth)
              https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/
Format      : CSV (one file per basin ~50 MB)
Coverage    : Global, 1842–present (WP basin most relevant for SE Asia)
License     : Public domain (US Government)

Ingestion:
    Batch download the WP (Western Pacific) basin CSV at deploy time.
    Refresh quarterly via scheduler.
    
FIX v3.2 (Gap R): Added @validate_no_nan decorators.
"""

import asyncio
import requests
import logging
from pathlib import Path
from typing import List, Tuple
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from src.core.models import CycloneEventParams
from src.config.settings import settings
from src.data.validation import validate_no_nan, DataQualityWarning

logger = logging.getLogger(__name__)

IBTRACS_PATH = Path(settings.IBTRACS_PATH)

# Direct download URL (no auth)
IBTRACS_WP_URL = (
    "https://www.ncei.noaa.gov/data/"
    "international-best-track-archive-for-climate-stewardship-ibtracs/"
    "v04r01/access/csv/ibtracs.WP.list.v04r01.csv"
)

@dataclass
class CycloneTrack:
    """Individual cyclone track."""
    storm_id: str
    name: str
    season: int
    track_points: List[Tuple[float, float, float, float]]
    basin: str


# ── Region bounding boxes (expanded for all SE Asia) ────
REGION_BOUNDS = {
    "vietnam_south": (8, 12, 104, 112),
    "vietnam_central": (12, 18, 106, 116),
    "vietnam_north": (18, 24, 104, 112),
    "philippines": (4, 22, 116, 130),
    "thailand": (5, 21, 97, 106),
    "indonesia_java": (-9, -5, 105, 115),
    "singapore": (1, 2, 103, 105),
    "southeast_asia": (0, 25, 95, 135),  # full region
}


async def load_regional_cyclones(
    region: str,
    min_year: int = 1980,
) -> List[CycloneTrack]:
    """
    Load cyclone tracks for a region from local IBTrACS CSV.
    """
    if region not in REGION_BOUNDS:
        # Fallback to full region if unknown
        region = "southeast_asia"

    lat_min, lat_max, lon_min, lon_max = REGION_BOUNDS[region]
    loop = asyncio.get_event_loop()

    def _load():
        csv_path = IBTRACS_PATH / "ibtracs.WP.csv"
        if not csv_path.exists():
            logger.info(f"Downloading IBTrACS data from {IBTRACS_WP_URL}...")
            try:
                IBTRACS_PATH.mkdir(parents=True, exist_ok=True)
                response = requests.get(IBTRACS_WP_URL, timeout=60)
                response.raise_for_status()
                with open(csv_path, "wb") as f:
                    f.write(response.content)
                logger.info("Download complete.")
            except Exception as e:
                logger.error(f"Failed to download IBTrACS data: {e}")
                return []

        # Optimization: use usecols to load only needed columns
        df = pd.read_csv(
            csv_path, 
            low_memory=False,
            usecols=['SID', 'NAME', 'SEASON', 'BASIN', 'LAT', 'LON', 'WMO_WIND', 'WMO_PRES']
        )
        
        # Rename to uppercase for consistency (already uppercase, but safe to keep if needed, 
        # or just remove if redundant. The previous code had this to normalize. 
        # Since source is uppercase, this is a no-op but safe).
        df.columns = [c.upper() for c in df.columns]
        
        # Convert to numeric, coercing errors
        df['LAT'] = pd.to_numeric(df['LAT'], errors='coerce')
        df['LON'] = pd.to_numeric(df['LON'], errors='coerce')
        df['SEASON'] = pd.to_numeric(df['SEASON'], errors='coerce')
        df['WMO_WIND'] = pd.to_numeric(df['WMO_WIND'], errors='coerce')
        df['WMO_PRES'] = pd.to_numeric(df['WMO_PRES'], errors='coerce')

        df = df[
            (df["LAT"] >= lat_min) & (df["LAT"] <= lat_max)
            & (df["LON"] >= lon_min) & (df["LON"] <= lon_max)
            & (df["SEASON"] >= min_year)
        ]

        tracks = []
        for storm_id, group in df.groupby("SID"):
            track_points = [
                (
                    row["LAT"], row["LON"],
                    row.get("WMO_WIND", 0), row.get("WMO_PRES", 1013),
                )
                for _, row in group.iterrows()
            ]
            tracks.append(CycloneTrack(
                storm_id=storm_id,
                name=group["NAME"].iloc[0] if "NAME" in group else "UNNAMED",
                season=int(group["SEASON"].iloc[0]),
                track_points=track_points,
                basin=group["BASIN"].iloc[0] if "BASIN" in group else "WP",
            ))
        return tracks

    return await loop.run_in_executor(None, _load)


@validate_no_nan
async def get_regional_cyclone_statistics(
    lat: float,
    lon: float,
    region: str,
    return_period: int = 100,
) -> CycloneEventParams:
    """
    Get cyclone parameters for a given return period.
    """
    tracks = await load_regional_cyclones(region)

    radius_deg = 2.0
    nearby_winds = []
    
    for track in tracks:
        for lat_t, lon_t, wind, pressure in track.track_points:
            dist = np.sqrt((lat_t - lat) ** 2 + (lon_t - lon) ** 2)
            if dist < radius_deg and wind > 0:
                nearby_winds.append(wind)

    if not nearby_winds:
        return CycloneEventParams(
            max_wind_ms=20.0,
            central_pressure_hpa=1000.0,
            radius_max_wind_km=50.0,
            translation_speed_ms=5.0,
            heading_degrees=315.0,
            saffir_simpson_category=0,
            rainfall_proxy_mm=50.0,
        )

    # Clean data (remove NaN)
    winds = np.array([w for w in nearby_winds if not np.isnan(w)]) * 0.514  # knots → m/s
    if len(winds) < 10:
         return CycloneEventParams(
            max_wind_ms=25.0,
            central_pressure_hpa=990.0,
            radius_max_wind_km=50.0,
            translation_speed_ms=5.0,
            heading_degrees=315.0,
            saffir_simpson_category=0,
            rainfall_proxy_mm=60.0,
        )

    shape, loc, scale = stats.genextreme.fit(winds)
    p = 1 - 1 / return_period
    return_wind = stats.genextreme.ppf(p, shape, loc=loc, scale=scale)

    # Atkinson-Holliday pressure relationship
    return_pressure = 1010 - (return_wind / 3.92) ** 2
    
    # Saffir-Simpson Scale
    if return_wind < 33: cat = 0
    elif return_wind < 43: cat = 1
    elif return_wind < 50: cat = 2
    elif return_wind < 58: cat = 3
    elif return_wind < 70: cat = 4
    else: cat = 5

    rmw = max(20.0, 80.0 - return_wind * 0.5)

    return CycloneEventParams(
        max_wind_ms=float(return_wind),
        central_pressure_hpa=float(max(880.0, return_pressure)),
        radius_max_wind_km=float(rmw),
        translation_speed_ms=5.0,
        heading_degrees=315.0,
        saffir_simpson_category=cat,
        rainfall_proxy_mm=float(return_wind * 5),
    )
