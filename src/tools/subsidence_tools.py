# src/tools/subsidence_tools.py
"""
Land subsidence hazard assessment.

v3.2 Changes:
  - Gap L: get_subsidence_velocity() now has published-rate fallback
  - Gap R: @validate_no_nan decorator
"""

from typing import Optional

from src.core.models import (
    Location, HazardIntensity, HazardEventContext,
    HazardAssessmentResult, ConfidenceLevel, RiskTier,
    HazardType, DataSource,
)
from src.tools._exposure_helpers import build_point_exposure
from src.data.insar import get_subsidence_velocity
from src.data.elevation import get_elevation
from src.data.validation import validate_no_nan

NATIVE_RESOLUTION_M = 100
EFFECTIVE_RESOLUTION_M = 100


@validate_no_nan
async def assess_subsidence(
    lat: float, lon: float,
    city: str = "hcmc",
    time_horizon: int = 2050,
) -> HazardAssessmentResult:
    """
    Assess land subsidence risk using InSAR + published-rate fallback.

    Returns:
        HazardAssessmentResult with subsidence rate as intensity_value (mm/yr).
    """
    # 1. Get subsidence velocity (v3.2: includes published-rate fallback)
    insar_result = await get_subsidence_velocity(lat, lon, city=city)
    velocity_mm_yr = insar_result.velocity_mm_per_year
    subsidence_source = getattr(insar_result, "source", "insar_measured")

    # 2. Baseline elevation
    elevation_m = await get_elevation(lat, lon)

    # 3. Project cumulative subsidence
    years_forward = max(0, time_horizon - 2024)
    cumulative_mm = abs(velocity_mm_yr) * years_forward
    cumulative_m = cumulative_mm / 1000

    # 4. Confidence
    abs_rate = abs(velocity_mm_yr)
    if abs_rate < 5:
        confidence = ConfidenceLevel.HIGH
    elif abs_rate < 20:
        confidence = ConfidenceLevel.MODERATE
    else:
        confidence = ConfidenceLevel.LOW

    # v3.2 (Gap L): Downgrade confidence if using published rates
    if subsidence_source == "published_literature":
        confidence = min(confidence, ConfidenceLevel.MODERATE)

    limitations = [
        f"Subsidence source: {subsidence_source}",
        f"Projection: {years_forward} years at {velocity_mm_yr:.1f} mm/yr",
        "Does not account for groundwater policy changes",
    ]
    if subsidence_source == "insar_measured":
        limitations.append("InSAR velocity assumes constant deformation rate")
        limitations.append("Seasonal/tidal signals may affect velocity estimates")
    elif subsidence_source == "published_literature":
        limitations.append("Published rate is city-average; spatial variation not captured")

    regional_notes = {
        "hcmc": "HCMC: known severe subsidence (10-50 mm/yr in Binh Chanh/District 7)",
        "jakarta": "Jakarta: extreme subsidence (up to 250 mm/yr in North Jakarta)",
        "bangkok": "Bangkok: moderate subsidence (10-30 mm/yr, slowing with policy)",
        "manila": "Manila: moderate subsidence in Metro Manila low-lying areas",
    }
    if city in regional_notes:
        limitations.append(regional_notes[city])

    risk_score = _calculate_subsidence_risk_score(abs_rate, cumulative_m)

    data_sources = [f"Copernicus GLO-30 DEM ({DataSource.COPERNICUS_GLO30.value})"]
    if subsidence_source == "insar_measured":
        data_sources.insert(0, f"Sentinel-1 InSAR ({DataSource.SENTINEL1_INSAR.value})")
    else:
        data_sources.insert(0, "Published subsidence rates (peer-reviewed literature)")

    return HazardAssessmentResult(
        hazard=HazardIntensity(
            hazard_type=HazardType.SUBSIDENCE,
            event_context=HazardEventContext(
                event_type="chronic", time_horizon=time_horizon
            ),
            intensity_value=round(abs_rate, 1),
            intensity_unit="mm/yr",
            intensity_p5=round(abs_rate * 0.7, 1),
            intensity_p95=round(abs_rate * 1.3, 1),
            uncertainty_type="measurement_uncertainty_30pct",
            native_resolution_m=NATIVE_RESOLUTION_M,
            effective_resolution_m=EFFECTIVE_RESOLUTION_M,
            data_sources=data_sources,
            limitations=limitations,
            confidence=confidence,
        ),
        exposure=build_point_exposure(
            lat=lat, lon=lon, elevation_m=elevation_m,
        ),
        intermediate={
            "velocity_mm_yr": round(velocity_mm_yr, 1),
            "abs_rate_mm_yr": round(abs_rate, 1),
            "cumulative_mm": round(cumulative_mm, 0),
            "cumulative_m": round(cumulative_m, 3),
            "years_forward": years_forward,
            "original_elevation_m": elevation_m,
            "adjusted_elevation_m": round(elevation_m - cumulative_m, 2),
            "subsidence_source": subsidence_source,
            "city": city,
        },
        impact_score=round(risk_score, 1),
        impact_tier=_score_to_tier(risk_score),
        can_aggregate_with=[HazardType.URBAN_HEAT],
        dependency_order=1,
    )


def _calculate_subsidence_risk_score(rate_mm_yr: float, cumulative_m: float) -> float:
    rate_score = min(60, rate_mm_yr / 30 * 60)
    cum_score = min(40, cumulative_m / 0.5 * 40)
    return min(100, rate_score + cum_score)


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75:
        return RiskTier.CRITICAL
    elif score >= 50:
        return RiskTier.HIGH
    elif score >= 25:
        return RiskTier.MODERATE
    return RiskTier.LOW
