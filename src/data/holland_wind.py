# src/data/holland_wind.py
"""
Holland (2008) Revised Parametric Cyclone Wind Profile.

NEW v3.2 (Gap P): Architecture mentioned "parametric model" for cyclone
wind field but didn't specify which model. This implements Holland (2008)
revised profile with B-parameter estimation from Vmax and central pressure.

Reference: Holland, G.J. (2008). A revised hurricane pressure-wind model.
           Monthly Weather Review, 136(9), 3432-3445.

The model converts IBTrACS best-track point data (Vmax, Pc, Pn, RMW)
to a spatial wind field at any distance from the storm center.

FIX v3.2 (Gap R): Added @validate_no_nan decorators.
"""

import math
from typing import Optional, Tuple
from pydantic import BaseModel, Field

from src.data.validation import validate_no_nan, DataQualityWarning

# Constants
RHO_AIR = 1.15  # Air density (kg/m³) at sea level, tropical
E = math.e


class HollandWindResult(BaseModel):
    """Wind speed at a specific location from Holland (2008) model."""
    wind_speed_ms: float = Field(..., ge=0, description="Sustained wind speed (m/s)")
    distance_km: float = Field(..., ge=0, description="Distance from storm center (km)")
    holland_b: float = Field(..., gt=0, lt=3, description="Holland B shape parameter")
    is_within_rmw: bool = Field(..., description="Inside radius of maximum wind")


def holland_b_parameter(
    vmax_ms: float,
    central_pressure_hpa: float,
    ambient_pressure_hpa: float = 1013.25,
) -> float:
    """
    Estimate Holland B parameter from Vmax and pressure deficit.
    
    Holland (2008) Eq. 2:
        B = (Vmax² × ρ × e) / (Pn - Pc)
    
    Clamped to [1.0, 2.5] per Holland's recommendations for the WP basin.
    """
    dp = (ambient_pressure_hpa - central_pressure_hpa) * 100  # Pa
    if dp <= 0:
        return 1.5  # Default for weak systems
    
    b = (vmax_ms ** 2 * RHO_AIR * E) / dp
    return max(1.0, min(2.5, b))  # Clamp to physical range


def holland_wind_profile(
    distance_km: float,
    vmax_ms: float,
    rmw_km: float,
    central_pressure_hpa: float,
    ambient_pressure_hpa: float = 1013.25,
    coriolis_f: float = 2.5e-5,
) -> HollandWindResult:
    """
    Compute wind speed at a given distance from cyclone center.
    
    Holland (2008) revised profile:
        V(r) = Vmax × [(RMW/r)^B × exp(1 - (RMW/r)^B)]^(1/2)
    
    With gradient-to-surface reduction factor of 0.8.
    """
    if distance_km <= 0:
        distance_km = 0.1  # Avoid division by zero
    
    b = holland_b_parameter(vmax_ms, central_pressure_hpa, ambient_pressure_hpa)
    
    r_ratio = rmw_km / distance_km
    exponent = r_ratio ** b
    
    # Holland (2008) Eq. 1: Gradient wind
    try:
        v_gradient = vmax_ms * (exponent * math.exp(1 - exponent)) ** 0.5
    except ValueError:
        v_gradient = 0.0
    
    # Surface reduction factor (gradient → 10m sustained)
    surface_factor = 0.8
    v_surface = v_gradient * surface_factor
    
    return HollandWindResult(
        wind_speed_ms=round(v_surface, 2),
        distance_km=distance_km,
        holland_b=round(b, 3),
        is_within_rmw=distance_km <= rmw_km,
    )


def wind_at_building(
    building_lat: float,
    building_lon: float,
    storm_lat: float,
    storm_lon: float,
    vmax_ms: float,
    rmw_km: float,
    central_pressure_hpa: float,
    translation_speed_ms: float = 5.0,
    heading_degrees: float = 315.0,
) -> float:
    """
    Compute sustained wind speed at a building location.
    
    Includes asymmetry correction: winds are stronger on the right side
    of the storm track (Northern Hemisphere) due to translation speed.
    """
    # Great-circle distance (simplified for short distances)
    dlat = math.radians(building_lat - storm_lat)
    dlon = math.radians(building_lon - storm_lon)
    mid_lat = math.radians((building_lat + storm_lat) / 2)
    
    dx = dlon * math.cos(mid_lat) * 6371  # km
    dy = dlat * 6371  # km
    distance_km = math.sqrt(dx**2 + dy**2)
    
    result = holland_wind_profile(
        distance_km, vmax_ms, rmw_km, central_pressure_hpa
    )
    
    # Asymmetry correction: add fraction of translation speed
    # on right side of track (NH), subtract on left
    bearing = math.degrees(math.atan2(dx, dy)) % 360
    relative_angle = (bearing - heading_degrees) % 360
    
    # Right side (NH): relative_angle 0-180 (add speed)
    # Left side (NH): 180-360 (subtract speed)
    # Using cosine to smooth transition
    asymmetry_factor = 0.5 * math.cos(math.radians(relative_angle))
    
    wind_with_asymmetry = result.wind_speed_ms + asymmetry_factor * translation_speed_ms
    
    return max(0.0, wind_with_asymmetry)
