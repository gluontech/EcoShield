# src/tools/riverine_flood_tools.py
"""
Riverine flood hazard assessment.

Physics: HAND model + GloFAS return-period discharge.
  - Height Above Nearest Drainage (HAND) from GLO-30 DEM
  - GloFAS v4 provides calibrated discharge for given return period
  - rating_curve converts discharge -> water depth (v3.2 Gap J)
  - Flood depth = max(0, water_level - effective_HAND)

v3.2 Changes:
  - Gap J: discharge_to_depth() from src.data.rating_curve
  - Gap H: climate_forcing_resolution_m=25000
  - Gap I: Manning's parameter uncertainty replaces fabricated +/-20%
  - Gap R: @validate_no_nan decorator
"""

from typing import Optional

from src.core.models import (
    Location, HazardIntensity, HazardEventContext,
    HazardAssessmentResult, AdjustedSurface, ConfidenceLevel, RiskTier,
    HazardType, DataSource,
)
from src.tools._exposure_helpers import build_point_exposure
from src.data.hand import get_hand_value
from src.data.elevation import get_elevation
from src.data.glofas import get_flood_return_period
from src.data.rating_curve import discharge_to_depth, CHANNEL_WIDTHS, MANNING_N
from src.data.validation import validate_no_nan

NATIVE_RESOLUTION_M = 30
EFFECTIVE_RESOLUTION_M = 30


@validate_no_nan
async def assess_riverine_flood(
    lat: float, lon: float,
    return_period: int = 100,
    surface: Optional[AdjustedSurface] = None,
    scenario: str = "historical",
    city: str = "hcmc",
) -> HazardAssessmentResult:
    """
    Assess riverine flood risk at a point location.

    Args:
        lat, lon: Location coordinates
        return_period: Flood return period in years (2-1000)
        surface: AdjustedSurface from Step 1 (contains subsidence data)
        scenario: Climate scenario for future projections
        city: City identifier for per-city channel parameters (v3.2)

    Returns:
        HazardAssessmentResult with flood depth as intensity_value (meters)
    """
    # 1. Get HAND value
    hand_result = await get_hand_value(lat, lon)

    # 2. Get calibrated discharge from GloFAS
    flood_discharge = await get_flood_return_period(
        lat=lat, lon=lon, return_period_years=return_period
    )

    # 3. Convert discharge -> water depth via rating_curve (Gap J)
    channel_width = CHANNEL_WIDTHS.get(city, 100.0)
    manning_n = MANNING_N.get("rural_natural", 0.035)
    is_urban = hand_result.hand_value_m < 5
    if is_urban:
        manning_n = MANNING_N.get("urban_concrete", 0.015)

    water_level = discharge_to_depth(
        discharge_m3s=flood_discharge.discharge_m3s,
        channel_width_m=channel_width,
        manning_n=manning_n,
    )

    # 4. Get raw elevation
    elevation_m = await get_elevation(lat, lon)

    # 5. Apply subsidence correction if available
    subsidence_effect = 0.0
    adjustments = []
    if surface and surface.subsidence_applied:
        subsidence_effect = surface.subsidence_adjustment_m
        adjustments.append("subsidence")

    # 6. Calculate flood depth
    effective_hand = hand_result.hand_value_m - subsidence_effect
    flood_depth = max(0, water_level - effective_hand)

    # 7. Uncertainty bounds (Gap I: Manning's n +/-30%, width +/-25%)
    depth_p5 = flood_depth * 0.65
    depth_p95 = flood_depth * 1.35

    # 8. Confidence assessment
    if is_urban:
        confidence = ConfidenceLevel.LOW
    elif hand_result.hand_value_m < 10:
        confidence = ConfidenceLevel.MODERATE
    else:
        confidence = ConfidenceLevel.HIGH

    limitations = [
        "HAND model does not represent engineered drainage",
        "No levee or embankment representation",
        f"Manning's equation: n={manning_n}, W={channel_width}m (city={city})",
    ]
    if is_urban:
        limitations.append("Urban drainage not represented — see pluvial_flood_tools.py")
    if subsidence_effect > 0:
        limitations.append(f"Subsidence adjustment: {subsidence_effect:.3f}m")

    risk_score = _calculate_flood_risk_score(flood_depth)

    return HazardAssessmentResult(
        hazard=HazardIntensity(
            hazard_type=HazardType.RIVERINE_FLOOD,
            event_context=HazardEventContext(
                event_type="acute", return_period_years=return_period
            ),
            intensity_value=round(flood_depth, 2),
            intensity_unit="m",
            intensity_p5=round(depth_p5, 2),
            intensity_p95=round(depth_p95, 2),
            uncertainty_type="manning_parameter_uncertainty_35pct",
            native_resolution_m=NATIVE_RESOLUTION_M,
            effective_resolution_m=EFFECTIVE_RESOLUTION_M,
            climate_forcing_resolution_m=25000,  # Gap H
            data_sources=[
                f"GloFAS v4 discharge ({DataSource.GLOFAS_V4.value})",
                f"Copernicus GLO-30 DEM ({NATIVE_RESOLUTION_M}m)",
                "HAND index (DEM-river difference)",
                "rating_curve.py Manning's equation (v3.2)",
            ],
            limitations=limitations,
            confidence=confidence,
        ),
        exposure=build_point_exposure(
            lat=lat, lon=lon, elevation_m=elevation_m,
            adjustments_applied=adjustments,
        ),
        intermediate={
            "hand_value_m": round(hand_result.hand_value_m, 2),
            "discharge_m3s": round(flood_discharge.discharge_m3s, 1),
            "water_level_m": round(water_level, 2),
            "channel_width_m": channel_width,
            "manning_n": manning_n,
            "subsidence_effect_m": round(subsidence_effect, 3),
            "effective_hand_m": round(effective_hand, 2),
            "flood_depth_m": round(flood_depth, 2),
            "flooded": flood_depth > 0,
            "is_urban": is_urban,
            "city": city,
            "flood_susceptibility": hand_result.flood_susceptibility,
        },
        impact_score=round(risk_score, 1),
        impact_tier=_score_to_tier(risk_score),
        can_aggregate_with=[HazardType.COASTAL_FLOOD, HazardType.STORM_SURGE,
                            HazardType.TROPICAL_CYCLONE, HazardType.LANDSLIDE,
                            HazardType.PLUVIAL_FLOOD],
        dependency_order=4,
    )


def _calculate_flood_risk_score(flood_depth: float) -> float:
    """Map flood depth to 0-100 risk score using damage curve."""
    if flood_depth <= 0:
        return 0.0
    elif flood_depth < 0.3:
        return flood_depth / 0.3 * 25
    elif flood_depth < 1.0:
        return 25 + (flood_depth - 0.3) / 0.7 * 25
    elif flood_depth < 2.0:
        return 50 + (flood_depth - 1.0) * 30
    else:
        return min(100, 80 + (flood_depth - 2.0) * 10)


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75:
        return RiskTier.CRITICAL
    elif score >= 50:
        return RiskTier.HIGH
    elif score >= 25:
        return RiskTier.MODERATE
    return RiskTier.LOW
