# src/data/hand.py
"""
Height Above Nearest Drainage (HAND) computation.

HAND measures the vertical distance between a point and the nearest
drainage channel, derived from the GLO-30 DEM. Lower HAND values
indicate higher riverine flood susceptibility.

Data source: Copernicus GLO-30 DEM (AWS S3 OpenData)
"""

import logging
import math
from typing import Optional

from src.core.models.elevation import HANDResult, ElevationResult
from src.core.models.enums import DataSource
from src.data.elevation import get_elevation
from src.data.validation import validate_no_nan

logger = logging.getLogger(__name__)

# Simplified HAND estimation parameters
# In production, HAND would be precomputed from full hydrological analysis
DRAINAGE_THRESHOLD_ACCUM = 1000  # Flow accumulation threshold for drainage


@validate_no_nan
async def get_hand_value(lat: float, lon: float) -> HANDResult:
    """
    Get Height Above Nearest Drainage at a location.

    Uses a simplified proxy: samples a small neighborhood from the DEM
    and estimates HAND as the difference between the point elevation and
    a simulated local drainage elevation. In production, this would use
    precomputed HAND rasters from full D8 flow routing.

    Args:
        lat: Latitude (decimal degrees)
        lon: Longitude (decimal degrees)

    Returns:
        HANDResult with hand_value_m and flood_susceptibility
    """
    elevation = await get_elevation(lat, lon)

    # Simplified HAND proxy: estimate local drainage from neighborhood
    # Sample elevations at ~90m offsets (3 GLO-30 pixels)
    offset_deg = 0.001  # ~110m at equator
    neighborhood_elevations = []
    for dlat in [-offset_deg, 0, offset_deg]:
        for dlon in [-offset_deg, 0, offset_deg]:
            if dlat == 0 and dlon == 0:
                continue
            neighbor_elev = await get_elevation(lat + dlat, lon + dlon)
            neighborhood_elevations.append(neighbor_elev)

    if neighborhood_elevations:
        local_min = min(neighborhood_elevations)
        hand_value = max(0.0, elevation - local_min)
    else:
        # Fallback: use elevation directly (coastal proxy)
        hand_value = max(0.0, elevation)

    # Estimate drainage distance from HAND (empirical relationship)
    # Higher HAND => likely farther from drainage
    drainage_distance = hand_value * 50.0  # ~50m per meter of HAND

    logger.debug(
        "HAND at (%.4f, %.4f): %.2f m, drainage distance: %.0f m",
        lat, lon, hand_value, drainage_distance,
    )

    return HANDResult(
        hand_value_m=round(hand_value, 2),
        nearest_drainage_distance_m=round(drainage_distance, 1),
        drainage_area_km2=None,
        flow_accumulation=None,
        resolution_m=30,
        data_source=DataSource.COPERNICUS_GLO30,
    )
