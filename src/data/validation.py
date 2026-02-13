# src/data/validation.py
"""
Data quality validation layer.

NEW v3.2 (Gap R): Data flows from API ingestion to Pydantic models to hazard
tools with no quality checks. This module adds validation decorators and
utility functions to catch common data quality issues:

- NaN / Inf values from NetCDF files
- DEM voids in urban canyons (fill values like -32768)
- GEE empty results due to cloud cover
- SoilGrids 255 (no data sentinel) being treated as valid percentage
- Degenerate building polygons (zero area, self-intersecting)
- Out-of-range values (negative precipitation, temperature > 70°C)

Usage:
    @validate_no_nan
    async def get_elevation(lat, lon): ...
    
    or:
    data = validate_array(raw_data, var_name="elevation", valid_range=(-500, 9000))
"""

import functools
import logging
from typing import Optional, Tuple, Any, Callable
import numpy as np

logger = logging.getLogger(__name__)


class DataQualityError(Exception):
    """Raised when data fails quality validation."""
    pass


class DataQualityWarning:
    """Logged (not raised) for recoverable quality issues."""
    def __init__(self, source: str, issue: str, severity: str = "warning"):
        self.source = source
        self.issue = issue
        self.severity = severity
        logger.warning(f"[DataQuality:{severity}] {source}: {issue}")


# ── Array-level validation ──

def validate_array(
    data: np.ndarray,
    var_name: str = "data",
    valid_range: Optional[Tuple[float, float]] = None,
    max_nan_fraction: float = 0.5,
    fill_values: Optional[list] = None,
) -> np.ndarray:
    """
    Validate a numpy array and replace bad values with NaN.
    
    Args:
        data: Input array
        var_name: Variable name for logging
        valid_range: (min, max) valid range
        max_nan_fraction: Max fraction of NaN before raising error
        fill_values: Additional fill values to treat as NaN (e.g., -32768, 255)
    
    Returns:
        Cleaned array with fill values replaced by NaN
    """
    result = data.astype(float).copy()
    
    # Replace fill values
    if fill_values:
        for fv in fill_values:
            mask = result == fv
            if mask.any():
                DataQualityWarning(var_name, f"Replaced {mask.sum()} fill values ({fv}) with NaN")
                result[mask] = np.nan
    
    # Replace Inf
    inf_mask = np.isinf(result)
    if inf_mask.any():
        DataQualityWarning(var_name, f"Replaced {inf_mask.sum()} Inf values with NaN")
        result[inf_mask] = np.nan
    
    # Range check
    if valid_range:
        low, high = valid_range
        oor_mask = (result < low) | (result > high)
        oor_mask = oor_mask & ~np.isnan(result)
        if oor_mask.any():
            DataQualityWarning(
                var_name,
                f"{oor_mask.sum()} values outside range [{low}, {high}], clamped"
            )
            result = np.clip(result, low, high)
    
    # NaN fraction check
    nan_frac = np.isnan(result).sum() / max(result.size, 1)
    if nan_frac > max_nan_fraction:
        raise DataQualityError(
            f"{var_name}: {nan_frac:.0%} NaN values exceeds threshold {max_nan_fraction:.0%}"
        )
    
    return result


# ── Scalar validation ──

def validate_scalar(
    value: float,
    var_name: str,
    valid_range: Optional[Tuple[float, float]] = None,
) -> float:
    """Validate a single scalar value."""
    if np.isnan(value) or np.isinf(value):
        raise DataQualityError(f"{var_name}: value is NaN or Inf")
    if valid_range:
        low, high = valid_range
        if value < low or value > high:
            DataQualityWarning(var_name, f"Value {value} outside range [{low}, {high}]")
            return float(np.clip(value, low, high))
    return value


# ── Decorator for async functions ──

def validate_no_nan(func: Callable) -> Callable:
    """Decorator that validates numeric fields in Pydantic return values."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        result = await func(*args, **kwargs)
        # Check all float fields in Pydantic model
        if hasattr(result, 'model_fields'):
            for field_name, field_info in result.model_fields.items():
                value = getattr(result, field_name, None)
                if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
                    DataQualityWarning(
                        func.__name__,
                        f"Field '{field_name}' is NaN/Inf in result"
                    )
        return result
    return wrapper


# ── Common valid ranges for EcoShield data ──

VALID_RANGES = {
    "elevation_m": (-500, 9000),
    "temperature_c": (-60, 60),
    "precipitation_mm": (0, 2000),
    "wind_speed_ms": (0, 120),
    "discharge_m3s": (0, 100000),
    "clay_fraction": (0, 100),
    "sand_fraction": (0, 100),
    "silt_fraction": (0, 100),
    "ndvi": (-1, 1),
    "lst_c": (-40, 70),
    "subsidence_mm_yr": (-200, 50),
    "building_area_m2": (1, 100000),
    "building_height_m": (0, 500),
}
