# src/tools/cyclone_tools.py
"""
Tropical cyclone hazard assessment using IBTrACS historical analysis.

v3.2 Changes:
  - Gap P: holland_wind.holland_wind_profile() with Holland (2008) revised profile
  - Gap R: @validate_no_nan decorator

Data sources: IBTrACS v04r01, holland_wind.py (v3.2).
"""

import math
import logging
from typing import Optional

from src.core.models import (
    Location, HazardIntensity, HazardEventContext,
    HazardAssessmentResult, CycloneEventParams, ConfidenceLevel, RiskTier,
    HazardType, DataSource,
)
from src.tools._exposure_helpers import build_point_exposure
from src.data.ibtracs import get_regional_cyclone_statistics
from src.data.elevation import get_elevation
from src.data.holland_wind import holland_wind_profile
from src.data.validation import validate_no_nan

logger = logging.getLogger(__name__)

NATIVE_RESOLUTION_M = 5000
EFFECTIVE_RESOLUTION_M = 5000


@validate_no_nan
async def assess_cyclone(
    lat: float, lon: float,
    return_period: int = 100,
    search_radius_km: float = 250,
    region: str = "southeast_asia",
) -> HazardAssessmentResult:
    """
    Assess tropical cyclone wind hazard from IBTrACS historical analysis.

    Args:
        lat, lon: Location coordinates
        return_period: Return period in years
        search_radius_km: Search radius for historical storms
        region: IBTrACS region identifier

    Returns:
        HazardAssessmentResult with wind speed as intensity_value (m/s)
    """
    elevation_m = await get_elevation(lat, lon)

    # Get cyclone statistics from IBTrACS
    cyclone_params = await get_regional_cyclone_statistics(
        lat, lon, region=region, return_period=return_period
    )

    site_wind_ms = cyclone_params.max_wind_ms
    central_pressure_mb = cyclone_params.central_pressure_hpa
    rmw_km = cyclone_params.radius_max_wind_km

    # Apply Holland (2008) distance decay if site is not at eyewall (Gap P)
    holland_b = None
    try:
        # Approximate distance — assume nearest approach is ~50km for non-zero result
        nearest_dist_km = max(10, rmw_km * 1.5)
        wind_result = holland_wind_profile(
            distance_km=nearest_dist_km,
            vmax_ms=site_wind_ms,
            rmw_km=rmw_km,
            central_pressure_hpa=central_pressure_mb,
        )
        site_wind_ms = wind_result.wind_speed_ms
        holland_b = getattr(wind_result, "b_parameter", None)
    except Exception as exc:
        logger.warning("Holland wind profile failed, using raw Vmax: %s", exc)

    # Confidence based on data quality
    ss_cat = cyclone_params.saffir_simpson_category
    if ss_cat >= 3:
        confidence = ConfidenceLevel.LOW
    elif ss_cat >= 1:
        confidence = ConfidenceLevel.MODERATE
    else:
        confidence = ConfidenceLevel.HIGH

    cyclone_params_dict = {
        "max_wind_ms": round(site_wind_ms, 1),
        "central_pressure_mb": round(central_pressure_mb, 0),
        "rmw_km": round(rmw_km, 1),
        "heading_deg": cyclone_params.heading_degrees,
        "forward_speed_ms": cyclone_params.translation_speed_ms,
        "saffir_simpson_category": ss_cat,
    }

    risk_score = _calculate_cyclone_risk_score(site_wind_ms)

    return HazardAssessmentResult(
        hazard=HazardIntensity(
            hazard_type=HazardType.TROPICAL_CYCLONE,
            event_context=HazardEventContext(
                event_type="acute", return_period_years=return_period
            ),
            intensity_value=round(site_wind_ms, 1),
            intensity_unit="m/s",
            intensity_p5=round(site_wind_ms * 0.8, 1),
            intensity_p95=round(site_wind_ms * 1.2, 1),
            uncertainty_type="gumbel_fit_uncertainty",
            native_resolution_m=NATIVE_RESOLUTION_M,
            effective_resolution_m=EFFECTIVE_RESOLUTION_M,
            data_sources=[
                f"IBTrACS v04r01 ({DataSource.IBTRACS_V04.value})",
                "Holland (2008) parametric wind profile (v3.2)",
            ],
            limitations=[
                "Gumbel extreme value distribution fit",
                "Holland (2008) revised parametric wind profile",
                "No climate change signal in future cyclone intensity",
            ],
            confidence=confidence,
        ),
        exposure=build_point_exposure(
            lat=lat, lon=lon, elevation_m=elevation_m,
        ),
        intermediate={
            "return_period_wind_ms": round(site_wind_ms, 1),
            "site_wind_ms": round(site_wind_ms, 1),
            "central_pressure_mb": round(central_pressure_mb, 0),
            "rmw_km": round(rmw_km, 1),
            "holland_b_parameter": holland_b,
            "saffir_simpson_category": ss_cat,
            "cyclone_params": cyclone_params_dict,
            "max_wind_kts": round(site_wind_ms / 0.5144, 0),
        },
        impact_score=round(risk_score, 1),
        impact_tier=_score_to_tier(risk_score),
        can_aggregate_with=[HazardType.STORM_SURGE, HazardType.RIVERINE_FLOOD,
                            HazardType.LANDSLIDE],
        dependency_order=2,
    )


def _calculate_cyclone_risk_score(wind_ms: float) -> float:
    if wind_ms < 17:
        return wind_ms / 17 * 15
    elif wind_ms < 33:
        return 15 + (wind_ms - 17) / 16 * 25
    elif wind_ms < 50:
        return 40 + (wind_ms - 33) / 17 * 25
    elif wind_ms < 70:
        return 65 + (wind_ms - 50) / 20 * 20
    else:
        return min(100, 85 + (wind_ms - 70) / 30 * 15)


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75:
        return RiskTier.CRITICAL
    elif score >= 50:
        return RiskTier.HIGH
    elif score >= 25:
        return RiskTier.MODERATE
    return RiskTier.LOW
