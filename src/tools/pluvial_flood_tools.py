# src/tools/pluvial_flood_tools.py
"""
Pluvial (surface water) flood hazard assessment -- NEW v3.2 (Gap M).

Physics: Proxy model combining terrain susceptibility + extreme rainfall.
  - HAND from GLO-30 DEM -> drainage potential
  - Slope from GLO-30 -> ponding susceptibility
  - Impervious fraction from NDVI proxy -> runoff coefficient
  - Extreme precipitation from NEX-GDDP-CMIP6 -> rainfall trigger

Limitations:
  This is a first-order proxy. True pluvial flood modeling requires:
  - Urban drainage network, 2D shallow-water equations, LiDAR DEM
"""

import logging
from typing import Optional

from src.core.models import (
    Location, HazardIntensity, HazardEventContext,
    HazardAssessmentResult, ConfidenceLevel, RiskTier,
    HazardType, DataSource,
)
from src.tools._exposure_helpers import build_point_exposure
from src.data.hand import get_hand_value
from src.data.elevation import get_slope, get_elevation
from src.data.nex_gddp import get_extreme_precipitation
from src.data.pluvial_flood import compute_pluvial_susceptibility
from src.data.validation import validate_no_nan

logger = logging.getLogger(__name__)

NATIVE_RESOLUTION_M = 30
EFFECTIVE_RESOLUTION_M = 30


@validate_no_nan
async def assess_pluvial_flood(
    lat: float, lon: float,
    return_period: int = 10,
    scenario: str = "historical",
) -> HazardAssessmentResult:
    """
    Assess pluvial (surface water) flood susceptibility.

    Args:
        lat, lon: Location coordinates
        return_period: Rainfall return period (typically 10-50 for pluvial)
        scenario: Climate scenario for precipitation projections

    Returns:
        HazardAssessmentResult with estimated surface water depth (meters).
    """
    # 1. Terrain data
    hand_result = await get_hand_value(lat, lon)
    slope_result = await get_slope(lat, lon)
    elevation_m = await get_elevation(lat, lon)

    # 2. Extreme precipitation for design storm
    precip_result = await get_extreme_precipitation(
        lat=lat, lon=lon, scenario=scenario, return_period=return_period
    )
    rainfall_mm = precip_result.precip_mm_per_day

    # 3. Impervious fraction proxy from NDVI (graceful degradation)
    impervious_fraction = 0.5  # Default for tropical urban
    try:
        from src.data.sentinel2 import get_ndvi_statistics
        ndvi = await get_ndvi_statistics(lat, lon, date_range="2022-01-01/2023-12-31")
        if ndvi and ndvi.ndvi_median is not None:
            impervious_fraction = max(0.1, min(0.95, 1.0 - ndvi.ndvi_median / 0.7))
    except (ImportError, Exception):
        logger.debug("Sentinel-2 NDVI unavailable, using default impervious_fraction=0.5")

    # 4. Compute pluvial susceptibility + depth proxy
    pluvial_result = compute_pluvial_susceptibility(
        hand_m=hand_result.hand_value_m,
        slope_degrees=slope_result.slope_degrees,
        impervious_fraction=impervious_fraction,
        design_rainfall_mm=rainfall_mm,
    )

    susceptibility = pluvial_result.susceptibility_index
    estimated_depth = pluvial_result.estimated_depth_m

    # 5. Confidence
    confidence = ConfidenceLevel.LOW
    if (hand_result.hand_value_m < 3
            and slope_result.slope_degrees < 2
            and impervious_fraction > 0.6):
        confidence = ConfidenceLevel.MODERATE

    data_sources = [
        f"Copernicus GLO-30 DEM ({DataSource.COPERNICUS_GLO30.value})",
        "HAND index (flood susceptibility)",
        f"NEX-GDDP-CMIP6 ({DataSource.NEX_GDDP_CMIP6.value})",
    ]
    if impervious_fraction != 0.5:
        data_sources.append(f"Sentinel-2 NDVI ({DataSource.SENTINEL2_L2A.value})")

    limitations = [
        "Proxy model: no urban drainage network representation",
        "No 2D shallow-water simulation (needs LISFLOOD-FP/TUFLOW + LiDAR)",
        "Impervious fraction from NDVI proxy (not land-use classification)",
        f"Depth estimate is indicative only (susceptibility={susceptibility:.2f})",
        "Does not account for pump stations, detention basins, or drainage upgrades",
        "GLO-30 at 30m cannot resolve street-level ponding patterns",
    ]

    risk_score = _calculate_pluvial_risk_score(estimated_depth, susceptibility)

    return HazardAssessmentResult(
        hazard=HazardIntensity(
            hazard_type=HazardType.PLUVIAL_FLOOD,
            event_context=HazardEventContext(
                event_type="acute", return_period_years=return_period
            ),
            intensity_value=round(estimated_depth, 2),
            intensity_unit="m",
            intensity_p5=round(estimated_depth * 0.5, 2),
            intensity_p95=round(estimated_depth * 2.0, 2),
            uncertainty_type="proxy_model_high_uncertainty",
            native_resolution_m=NATIVE_RESOLUTION_M,
            effective_resolution_m=EFFECTIVE_RESOLUTION_M,
            climate_forcing_resolution_m=25000,  # Gap H
            data_sources=data_sources,
            limitations=limitations,
            confidence=confidence,
        ),
        exposure=build_point_exposure(
            lat=lat, lon=lon, elevation_m=elevation_m,
            slope_degrees=slope_result.slope_degrees,
        ),
        intermediate={
            "hand_value_m": round(hand_result.hand_value_m, 2),
            "slope_degrees": round(slope_result.slope_degrees, 2),
            "impervious_fraction": round(impervious_fraction, 3),
            "design_rainfall_mm": round(rainfall_mm, 1),
            "susceptibility_index": round(susceptibility, 3),
            "estimated_depth_m": round(estimated_depth, 2),
            "runoff_coefficient": round(pluvial_result.runoff_coefficient, 3),
            "scenario": scenario,
        },
        impact_score=round(risk_score, 1),
        impact_tier=_score_to_tier(risk_score),
        can_aggregate_with=[HazardType.RIVERINE_FLOOD, HazardType.COASTAL_FLOOD,
                            HazardType.STORM_SURGE],
        dependency_order=4,
    )


def _calculate_pluvial_risk_score(depth: float, susceptibility: float) -> float:
    """Map pluvial depth + susceptibility to 0-100 risk score."""
    if depth <= 0:
        return 0.0
    elif depth < 0.1:
        depth_score = depth / 0.1 * 15
    elif depth < 0.3:
        depth_score = 15 + (depth - 0.1) / 0.2 * 20
    elif depth < 0.5:
        depth_score = 35 + (depth - 0.3) / 0.2 * 20
    elif depth < 1.0:
        depth_score = 55 + (depth - 0.5) / 0.5 * 25
    else:
        depth_score = min(100, 80 + (depth - 1.0) * 20)
    return 0.7 * depth_score + 0.3 * (susceptibility * 100)


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75:
        return RiskTier.CRITICAL
    elif score >= 50:
        return RiskTier.HIGH
    elif score >= 25:
        return RiskTier.MODERATE
    return RiskTier.LOW
