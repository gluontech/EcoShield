# src/data/elevation.py
"""
Copernicus GLO-30 Digital Elevation Model (DEM) Access.

Provides 30m resolution elevation data for terrain analysis.
Data is pre-ingested from AWS S3 to local COG files by `ingestion/dem_ingest.py`.

FIX v3.2 (Gap O): Added slope and aspect calculation for landslide/flood modeling.
FIX v3.2 (Gap R): Added @validate_no_nan decorators and fill-value handling.
"""

import asyncio
import logging
import math
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Optional, Tuple, Dict

import numpy as np
import rasterio
from rasterio.windows import Window

from src.config.settings import settings
from src.core.models import (
    SlopeResult,
    DataSource,
    ConfidenceLevel,
)
from src.data.validation import validate_no_nan, DataQualityWarning

logger = logging.getLogger(__name__)

DEM_PATH = Path(settings.COPERNICUS_DEM_LOCAL_CACHE)

# Per-thread LRU cache for rasterio dataset handles.
# Each thread gets its own set of readers so concurrent asyncio.to_thread()
# calls never share a GDAL handle (rasterio handles are not thread-safe).
# The cache is bounded to avoid leaking file descriptors in long-running workers.
_MAX_CACHED_DATASETS = 12
_thread_local = threading.local()


def _get_cached_dataset(dem_path: Path) -> rasterio.DatasetReader:
    """Return a per-thread cached rasterio dataset, opening it on first access.

    Uses an LRU eviction policy bounded to ``_MAX_CACHED_DATASETS`` entries per
    thread.  Evicted handles are closed immediately so file descriptors don't
    leak over the lifetime of the process.
    """
    cache: OrderedDict[str, rasterio.DatasetReader] = getattr(
        _thread_local, "dem_cache", None
    )
    if cache is None:
        cache = OrderedDict()
        _thread_local.dem_cache = cache

    path_str = str(dem_path)
    if path_str in cache:
        cache.move_to_end(path_str)
        return cache[path_str]

    ds = rasterio.open(dem_path)
    cache[path_str] = ds

    # Evict oldest entry when the cache exceeds the limit
    while len(cache) > _MAX_CACHED_DATASETS:
        _, evicted = cache.popitem(last=False)
        try:
            evicted.close()
        except Exception:
            pass

    return ds


def close_dem_cache() -> None:
    """Close all cached DEM handles across all threads that registered one.

    Call this during application shutdown to release file descriptors eagerly.
    For the *current* thread this always works; other threads' ``local()``
    storage is only reachable if they are still alive and joinable.
    """
    cache: Optional[OrderedDict] = getattr(_thread_local, "dem_cache", None)
    if cache is not None:
        for ds in cache.values():
            try:
                ds.close()
            except Exception:
                pass
        cache.clear()


def _get_dem_path(lat: float, lon: float) -> Optional[Path]:
    """Resolve local path for the 1x1 degree DEM tile."""
    # N10E106 -> Copernicus_DSM_COG_10_N10_00_E106_00_DEM.tif
    lat_int = math.floor(lat)
    lon_int = math.floor(lon)
    
    lat_pfx = "N" if lat_int >= 0 else "S"
    lon_pfx = "E" if lon_int >= 0 else "W"
    
    # 3-digit longitude padding
    name = f"Copernicus_DSM_COG_10_{lat_pfx}{abs(lat_int):02d}_00_{lon_pfx}{abs(lon_int):03d}_00_DEM"
    
    path = DEM_PATH / f"{name}.tif"
    if not path.exists():
        # Try checking nested folder structure if simple path fails
        nested_path = DEM_PATH / name / f"{name}.tif"
        if nested_path.exists():
            return nested_path
        return None
        
    return path


def _read_elevation_sync(lat: float, lon: float) -> float:
    """Synchronous elevation read using cached DEM dataset."""
    dem_path = _get_dem_path(lat, lon)
    if not dem_path:
        logger.warning(f"DEM tile not found for {lat}, {lon}")
        return 0.0

    try:
        src = _get_cached_dataset(dem_path)
        row, col = src.index(lon, lat)

        window = Window(col, row, 1, 1)
        val = src.read(1, window=window)

        elevation = float(val[0][0])

        if elevation == src.nodata or elevation < -1000:
            logger.warning(f"Nodata value {elevation} at {lat}, {lon}")
            return 0.0

        return elevation

    except Exception as e:
        logger.error(f"Error reading DEM {dem_path}: {e}")
        return 0.0


@validate_no_nan
async def get_elevation(lat: float, lon: float) -> float:
    """
    Get elevation at a specific point.

    Uses cached DEM file handles and runs blocking I/O in a thread pool
    so concurrent calls from asyncio.gather() execute in parallel.
    """
    return await asyncio.to_thread(_read_elevation_sync, lat, lon)


def _read_elevation_footprint_sync(wkt_polygon: str) -> float:
    """Sample median elevation across a building footprint polygon.

    Instead of single-pixel at centroid, clips the DEM to the footprint
    and returns the median of valid pixels.  Handles:
    - Height raster misalignment (±5m shift at 30m resolution)
    - Mixed pixel bleed at polygon edges
    - DEM void fill (nodata pixels excluded from median)
    """
    try:
        from shapely.wkt import loads as load_wkt
        from rasterio.mask import mask as rio_mask
    except ImportError:
        logger.warning("shapely or rasterio.mask not available; falling back to centroid")
        return 0.0

    try:
        poly = load_wkt(wkt_polygon)
        centroid = poly.centroid
    except Exception as e:
        logger.warning(f"Could not parse WKT for footprint elevation: {e}")
        return 0.0

    dem_path = _get_dem_path(centroid.y, centroid.x)
    if not dem_path:
        return _read_elevation_sync(centroid.y, centroid.x)

    try:
        src = _get_cached_dataset(dem_path)
        geojson = [poly.__geo_interface__]
        out_image, _ = rio_mask(src, geojson, crop=True, nodata=src.nodata)

        # Flatten and filter invalid values
        valid = out_image.flatten()
        if src.nodata is not None:
            valid = valid[valid != src.nodata]
        valid = valid[valid > -1000]

        if len(valid) == 0:
            # Polygon too small or falls on void — fallback to centroid
            return _read_elevation_sync(centroid.y, centroid.x)

        return float(np.median(valid))

    except Exception as e:
        logger.warning(f"Footprint elevation mask failed, falling back to centroid: {e}")
        return _read_elevation_sync(centroid.y, centroid.x)


@validate_no_nan
async def get_elevation_footprint(wkt_polygon: str) -> float:
    """Get median elevation across a building footprint polygon.

    Falls back to centroid single-pixel sampling when the polygon is too
    small or the mask returns no valid pixels.
    """
    return await asyncio.to_thread(_read_elevation_footprint_sync, wkt_polygon)


@validate_no_nan
async def get_slope(lat: float, lon: float) -> SlopeResult:
    """
    Calculate slope and aspect using 3x3 window gradient.
    
    Returns:
        SlopeResult with degrees and aspect.
    """
    dem_path = _get_dem_path(lat, lon)
    if not dem_path:
        return SlopeResult(
            slope_degrees=0.0,
            aspect_degrees=0.0,
            elevation_m=0.0,
            data_source=DataSource.COPERNICUS_GLO30,
        )

    try:
        with rasterio.open(dem_path) as src:
            row, col = src.index(lon, lat)
            
            # Read 3x3 window
            # Check bounds
            if row < 1 or col < 1 or row >= src.height - 1 or col >= src.width - 1:
                return SlopeResult(
                    slope_degrees=0.0,
                    aspect_degrees=0.0,
                    elevation_m=0.0,
                    data_source=DataSource.COPERNICUS_GLO30,
                )
                
            window = Window(col - 1, row - 1, 3, 3)
            data = src.read(1, window=window)
            
            # Horn's method for slope
            # [a, b, c]
            # [d, e, f]
            # [g, h, i]
            # data is 3x3
            
            cell_size = 30.0  # Approx meters (should adjust for lat)
            
            dz_dx = ((data[0, 2] + 2*data[1, 2] + data[2, 2]) - 
                     (data[0, 0] + 2*data[1, 0] + data[2, 0])) / (8 * cell_size)
                     
            dz_dy = ((data[2, 0] + 2*data[2, 1] + data[2, 2]) - 
                     (data[0, 0] + 2*data[0, 1] + data[0, 2])) / (8 * cell_size)
            
            rise_run = math.sqrt(dz_dx**2 + dz_dy**2)
            slope_rad = math.atan(rise_run)
            slope_deg = math.degrees(slope_rad)
            
            # Aspect (direction of steepest slope)
            aspect_rad = math.atan2(dz_dy, -dz_dx)
            aspect_deg = math.degrees(aspect_rad)
            if aspect_deg < 0:
                aspect_deg += 360
                
            return SlopeResult(
                slope_degrees=float(slope_deg),
                aspect_degrees=float(aspect_deg),
                elevation_m=float(data[1, 1]), # Center pixel
                data_source=DataSource.COPERNICUS_GLO30,
            )

    except Exception as e:
        logger.error(f"Error calculating slope {dem_path}: {e}")
        return SlopeResult(
            slope_degrees=0.0,
            aspect_degrees=0.0,
            elevation_m=0.0,
            data_source=DataSource.COPERNICUS_GLO30,
        )
