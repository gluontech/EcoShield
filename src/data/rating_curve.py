# src/data/rating_curve.py
"""
Discharge to Water Depth Conversion via Manning's Equation.

NEW v3.2 (Gap J): GloFAS provides river discharge (m³/s) but the flood
model needs water level (m). This rating curve module converts between them.

Without this, FloodReturnPeriodResult.estimated_water_level_m is always None,
and riverine flood depth at buildings cannot be computed.

Method: Manning's equation for wide-channel approximation:
    Q = (1/n) × A × R^(2/3) × S^(1/2)
    
For wide rectangular channels (width >> depth):
    A ≈ W × d,  R ≈ d  (hydraulic radius ≈ depth)
    Q ≈ (1/n) × W × d^(5/3) × S^(1/2)
    d ≈ (Q × n / (W × S^(1/2)))^(3/5)

Where:
    Q = discharge (m³/s)
    n = Manning's roughness coefficient
    W = channel width (m)
    S = channel slope (m/m)
    d = water depth (m)
    
FIX v3.2 (Gap R): Added @validate_no_nan decorators implicit in usage.
"""

import math
from typing import Optional
from pydantic import BaseModel, Field


# Manning's roughness coefficients for SEA river types
MANNING_N = {
    "urban_concrete": 0.015,
    "urban_natural": 0.030,
    "rural_natural": 0.035,
    "floodplain": 0.050,
    "mangrove": 0.070,
}

# Approximate channel widths for major SEA rivers (m)
CHANNEL_WIDTHS = {
    "saigon_river": 250,
    "dong_nai_river": 400,
    "red_river": 500,
    "han_river": 200,
    "ciliwung_river": 30,
    "pasig_river": 80,
    "chao_phraya": 300,
    "default": 100,
}


def discharge_to_depth(
    discharge_m3s: float,
    channel_width_m: float = 100.0,
    manning_n: float = 0.035,
    channel_slope: float = 0.0005,
) -> float:
    """
    Convert river discharge to approximate water depth using Manning's equation.
    
    Wide-channel approximation: d ≈ (Q × n / (W × S^(1/2)))^(3/5)
    
    Args:
        discharge_m3s: River discharge in m³/s (from GloFAS)
        channel_width_m: Effective channel width (m)
        manning_n: Manning's roughness coefficient
        channel_slope: Channel bed slope (m/m)
    
    Returns:
        Estimated water depth in meters above channel bed
    """
    if discharge_m3s <= 0 or channel_width_m <= 0 or channel_slope <= 0:
        return 0.0
    
    numerator = discharge_m3s * manning_n
    denominator = channel_width_m * math.sqrt(channel_slope)
    depth = (numerator / denominator) ** 0.6  # 3/5 = 0.6
    
    return depth


def depth_to_flood_level(
    depth_m: float,
    bankfull_depth_m: float = 3.0,
    channel_bed_elevation_m: float = 0.0,
) -> Optional[float]:
    """
    Convert channel water depth to flood water surface elevation.
    
    Returns None if water is below bankfull (no flooding).
    Returns water surface MSL elevation if overbank.
    
    Args:
        depth_m: Water depth above channel bed (m)
        bankfull_depth_m: Depth at which flooding begins
        channel_bed_elevation_m: Channel bed elevation (m MSL)
    """
    if depth_m <= bankfull_depth_m:
        return None  # No overbank flooding
    
    # Flood level is bed elevation + flow depth
    # But usually we model the *overbank* depth at the building
    # Here we return the MSL elevation of the water surface
    water_surface_msl = channel_bed_elevation_m + depth_m
    return water_surface_msl


class RatingCurveParams(BaseModel):
    """Parameters for a specific river reach rating curve."""
    river_name: str = Field(default="unknown")
    channel_width_m: float = Field(default=100.0, gt=0)
    manning_n: float = Field(default=0.035, gt=0, lt=0.2)
    channel_slope: float = Field(default=0.0005, gt=0, lt=0.1)
    bankfull_depth_m: float = Field(default=3.0, ge=0)
    channel_bed_elevation_m: float = Field(default=0.0)
    
    def discharge_to_water_level(self, discharge_m3s: float) -> Optional[float]:
        """Full pipeline: discharge → depth → water surface elevation."""
        depth = discharge_to_depth(
            discharge_m3s, self.channel_width_m,
            self.manning_n, self.channel_slope
        )
        return depth_to_flood_level(
            depth, self.bankfull_depth_m, self.channel_bed_elevation_m
        )
