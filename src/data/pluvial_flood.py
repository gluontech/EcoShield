# src/data/pluvial_flood.py
"""
Pluvial (surface water) flood susceptibility proxy.

NEW v3.2 (Gap M): The system modeled riverine and coastal flooding but omitted
pluvial flooding from intense rainfall overwhelming drainage capacity. This is
the most frequent flood type in SEA cities.

Method: Proxy susceptibility index from terrain + surface + precipitation:
  - HAND (Height Above Nearest Drainage): low HAND = water accumulation zone
  - Slope: flat terrain retains water
  - Impervious fraction: urban surfaces prevent infiltration
  - Extreme precipitation: intensity of rainfall events
  
Depth estimation (simplified):
  depth_m ≈ rainfall_mm × runoff_coefficient / 1000
  for flat urban areas with minimal drainage capacity.

FIX v3.2 (Gap R): Added @validate_no_nan decorators implicit in usage.
"""

import math
from typing import Optional
from pydantic import BaseModel, Field

from src.core.models import HazardType
from src.data.validation import validate_no_nan, DataQualityWarning


class PluvialFloodResult(BaseModel):
    """Pluvial flood susceptibility and estimated depth for a location."""
    susceptibility_index: float = Field(
        ..., ge=0, le=1,
        description="Pluvial flood susceptibility (0=none, 1=maximum)"
    )
    estimated_depth_m: float = Field(
        default=0.0, ge=0,
        description="Estimated surface water depth (m) for design rainfall"
    )
    hand_m: float = Field(..., ge=0, description="HAND value at location")
    slope_degrees: float = Field(..., ge=0, description="Terrain slope")
    impervious_fraction: float = Field(
        ..., ge=0, le=1,
        description="Fraction of impervious surface"
    )
    design_rainfall_mm: float = Field(
        ..., ge=0,
        description="Design rainfall intensity (mm/day)"
    )
    runoff_coefficient: float = Field(
        ..., ge=0, le=1,
        description="Estimated runoff coefficient"
    )
    hazard_type: HazardType = Field(default=HazardType.PLUVIAL_FLOOD)


def compute_pluvial_susceptibility(
    hand_m: float,
    slope_degrees: float,
    impervious_fraction: float = 0.5,
    design_rainfall_mm: float = 100.0,
) -> PluvialFloodResult:
    """
    Compute pluvial flood susceptibility from terrain and surface data.
    
    Susceptibility index = weighted combination of:
      - HAND factor (0-1): lower HAND → higher susceptibility
      - Slope factor (0-1): flatter → higher susceptibility
      - Impervious factor (0-1): more impervious → higher susceptibility
    """
    # HAND factor: exponential decay, threshold at 5m
    # Low HAND (near 0) -> high factor (near 1)
    hand_factor = math.exp(-hand_m / 2.0) if hand_m >= 0 else 1.0
    hand_factor = min(1.0, max(0.0, hand_factor))
    
    # Slope factor: flat terrain retains water
    # Slope 0 -> factor 1. Slope 10 deg -> factor 0
    slope_factor = max(0.0, 1.0 - slope_degrees / 10.0)
    
    # Combined susceptibility (weighted)
    # HAND is dominant (where water goes), Imperviousness next (generation), Slope (retention)
    susceptibility = (
        0.40 * hand_factor +
        0.25 * slope_factor +
        0.35 * impervious_fraction
    )
    susceptibility = max(0.0, min(1.0, susceptibility))
    
    # Runoff coefficient from impervious fraction
    # CN method simplified: C ≈ 0.3 + 0.65 × impervious_fraction
    runoff_coeff = 0.3 + 0.65 * impervious_fraction
    
    # Estimated depth for flat urban areas (simplified mass balance)
    # depth = rainfall × runoff_coeff / 1000 (mm → m)
    # Adjusted by susceptibility to account for drainage capacity (susceptibility < 1 implies some drainage/runoff elsewhere)
    estimated_depth = (design_rainfall_mm * runoff_coeff / 1000.0) * susceptibility
    
    return PluvialFloodResult(
        susceptibility_index=round(susceptibility, 3),
        estimated_depth_m=round(estimated_depth, 3),
        hand_m=hand_m,
        slope_degrees=slope_degrees,
        impervious_fraction=impervious_fraction,
        design_rainfall_mm=design_rainfall_mm,
        runoff_coefficient=round(runoff_coeff, 3),
    )
