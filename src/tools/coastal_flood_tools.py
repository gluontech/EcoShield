# src/tools/coastal_flood_tools.py
"""
Coastal flood hazard assessment using bathtub model + SLR projections.

v3.2 Changes:
  - Gap K: ipcc_slr.get_slr_projection() with per-city regional SLR
  - Gap H: climate_forcing_resolution_m=25000
  - Gap R: @validate_no_nan decorator
"""

from typing import Optional
import math

from src.core.models import (
    Location, HazardIntensity, HazardEventContext,
    HazardAssessmentResult, AdjustedSurface, ConfidenceLevel, RiskTier,
    HazardType, DataSource,
)
from src.tools._exposure_helpers import build_point_exposure
from src.data.elevation import get_elevation
from src.data.ipcc_slr import get_slr_projection
from src.data.validation import validate_no_nan

NATIVE_RESOLUTION_M = 30
EFFECTIVE_RESOLUTION_M = 30


@validate_no_nan
async def assess_coastal_flood(
    lat: float, lon: float,
    time_horizon: int = 2050,
    scenario: str = "ssp245",
    surface: Optional[AdjustedSurface] = None,
    tidal_range_m: float = 2.0,
    city: str = "ho_chi_minh_city",
    return_period: int = 100,
) -> HazardAssessmentResult:
    """
    Assess coastal flood risk using bathtub SLR model.

    Args:
        lat, lon: Location coordinates (must be within ~10km of coast)
        time_horizon: Target year (2030, 2050, or 2100)
        scenario: SSP scenario string
        surface: AdjustedSurface with subsidence
        tidal_range_m: Local mean tidal range (meters)
        city: City identifier for per-city IPCC SLR lookup (v3.2)
    """
    elevation_m = await get_elevation(lat, lon)

    # Get regional SLR (Gap K)
    try:
        slr = get_slr_projection(city=city, scenario=scenario, target_year=time_horizon)
        slr_median = slr.slr_median_m
        slr_p5 = slr.slr_p5_m
        slr_p95 = slr.slr_p95_m
        slr_source = f"IPCC AR6 regional ({city})"
    except (ValueError, KeyError):
        # Fallback to global median if city not in regional table
        _GLOBAL_FALLBACK = {
            "ssp126": {2050: 0.18, 2100: 0.44},
            "ssp245": {2050: 0.23, 2100: 0.56},
            "ssp370": {2050: 0.25, 2100: 0.68},
            "ssp585": {2050: 0.27, 2100: 0.77},
        }
        table = _GLOBAL_FALLBACK.get(scenario, _GLOBAL_FALLBACK["ssp245"])
        horizon_key = min(table.keys(), key=lambda k: abs(k - time_horizon))
        slr_median = table[horizon_key]
        slr_p5 = slr_median * 0.7
        slr_p95 = slr_median * 1.6
        slr_source = "IPCC AR6 global median (fallback)"

    # Subsidence correction
    subsidence_effect = 0.0
    adjustments = []
    if surface and surface.subsidence_applied:
        subsidence_effect = surface.subsidence_adjustment_m
        adjustments.append("subsidence")

    effective_elevation = elevation_m - subsidence_effect
    total_water_level = slr_median + (tidal_range_m / 2)
    total_water_level_p95 = slr_p95 + (tidal_range_m / 2)

    inundation_depth = max(0, total_water_level - effective_elevation)
    inundation_p5 = max(0, slr_p5 + tidal_range_m / 2 - effective_elevation)
    inundation_p95 = max(0, total_water_level_p95 - effective_elevation)

    # Global distance-to-coast using Natural Earth land polygon boundaries
    from src.data.coastline import get_distance_to_coast_km

    dist_km = get_distance_to_coast_km(lat, lon)
    is_coastal = effective_elevation < 5 and dist_km < 5.0

    if not is_coastal:
        confidence = ConfidenceLevel.HIGH
        inundation_depth = 0.0
    elif effective_elevation < 2:
        confidence = ConfidenceLevel.LOW
    else:
        confidence = ConfidenceLevel.LOW

    limitations = [
        "Bathtub model (no wave runup, no coastal morphology)",
        "Tidal range is a fixed input, not location-specific tide model",
        f"SLR: {slr_source} {scenario.upper()} @ {time_horizon}",
        "No storm surge interaction (see storm_surge_tools.py)",
    ]
    if subsidence_effect > 0:
        limitations.append(f"Subsidence correction: -{subsidence_effect:.3f}m")

    risk_score = _calculate_coastal_risk_score(inundation_depth, time_horizon)

    return HazardAssessmentResult(
        hazard=HazardIntensity(
            hazard_type=HazardType.COASTAL_FLOOD,
            event_context=HazardEventContext(
                event_type="acute", time_horizon=time_horizon
            ),
            intensity_value=round(inundation_depth, 2),
            intensity_unit="m",
            intensity_p5=round(inundation_p5, 2),
            intensity_p95=round(inundation_p95, 2),
            uncertainty_type="ipcc_ar6_scenario_range",
            native_resolution_m=NATIVE_RESOLUTION_M,
            effective_resolution_m=EFFECTIVE_RESOLUTION_M,
            climate_forcing_resolution_m=25000,  # Gap H
            data_sources=[
                f"IPCC AR6 SLR projections ({DataSource.IPCC_AR6.value}) — {slr_source}",
                f"Copernicus GLO-30 DEM ({DataSource.COPERNICUS_GLO30.value})",
            ],
            limitations=limitations,
            confidence=confidence,
        ),
        exposure=build_point_exposure(
            lat=lat, lon=lon, elevation_m=elevation_m,
            adjustments_applied=adjustments,
        ),
        intermediate={
            "raw_elevation_m": elevation_m,
            "effective_elevation_m": round(effective_elevation, 2),
            "slr_median_m": slr_median,
            "slr_p5_m": round(slr_p5, 3),
            "slr_p95_m": round(slr_p95, 3),
            "slr_source": slr_source,
            "tidal_range_m": tidal_range_m,
            "total_water_level_m": round(total_water_level, 2),
            "inundation_depth_m": round(inundation_depth, 2),
            "subsidence_effect_m": round(subsidence_effect, 3),
            "scenario": scenario,
            "time_horizon": time_horizon,
            "city": city,
            "is_coastal": is_coastal,
        },
        impact_score=round(risk_score, 1),
        impact_tier=_score_to_tier(risk_score),
        can_aggregate_with=[HazardType.RIVERINE_FLOOD, HazardType.STORM_SURGE,
                            HazardType.PLUVIAL_FLOOD],
        dependency_order=5,
    )


def _calculate_coastal_risk_score(depth: float, horizon: int) -> float:
    if depth <= 0:
        return 0.0
    base = min(80, depth / 2.0 * 80)
    urgency = 1.0 + (0.2 if horizon <= 2050 else 0.0)
    return min(100, base * urgency)


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75:
        return RiskTier.CRITICAL
    elif score >= 50:
        return RiskTier.HIGH
    elif score >= 25:
        return RiskTier.MODERATE
    return RiskTier.LOW
