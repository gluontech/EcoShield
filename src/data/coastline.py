# src/data/coastline.py
"""
Global distance-to-coast calculation — zero heavy dependencies.

Computes the Haversine distance from any (lat, lon) to the nearest
point in a pre-sampled set of global coastline coordinates stored in
``data/coastline_points.json``.

The coastline points are densely sampled (every ~50 km) from simplified
continental boundaries.  Accuracy is ± 25 km, which is well within the
5 km threshold used for coastal classification.

Dependencies: ``math``, ``json`` only (no shapely, no geopandas).
"""

import json
import logging
import math
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

_EARTH_RADIUS_KM = 6371.0
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_COASTLINE_FILE = _DATA_DIR / "coastline_points.json"

# Module-level cache
_coast_points: List[Tuple[float, float]] | None = None


def _haversine_km(
    lat1: float, lon1: float, lat2: float, lon2: float,
) -> float:
    """Great-circle distance in kilometres."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return _EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _load_coast_points() -> List[Tuple[float, float]]:
    """Load coastline sample points from the bundled JSON file."""
    global _coast_points
    if _coast_points is not None:
        return _coast_points

    if not _COASTLINE_FILE.exists():
        logger.error(
            "Coastline file not found: %s. "
            "Run `python -m scripts.gen_coastline_points` to generate it.",
            _COASTLINE_FILE,
        )
        return []

    with open(_COASTLINE_FILE) as f:
        _coast_points = [tuple(p) for p in json.load(f)]

    logger.info(
        "Loaded %d coastline sample points from %s",
        len(_coast_points), _COASTLINE_FILE,
    )
    return _coast_points


def get_distance_to_coast_km(lat: float, lon: float) -> float:
    """Calculate distance from *(lat, lon)* to the nearest coastline.

    Args:
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.

    Returns:
        Distance in kilometres.  Returns ``999.0`` when coastline data
        is unavailable.
    """
    points = _load_coast_points()
    if not points:
        logger.warning("No coastline data — returning fallback 999 km")
        return 999.0

    min_dist = float("inf")
    for clat, clon in points:
        d = _haversine_km(lat, lon, clat, clon)
        if d < min_dist:
            min_dist = d

    return min_dist
