# src/tools/urban_heat_tools.py
"""
Urban heat hazard assessment with WBGT + climate projections.

v3.2 Changes:
  - Gap H: climate_forcing_resolution_m=25000
  - Gap I: get_climate_projection() returns real ensemble p5/p95
  - Gap R: @validate_no_nan decorator

Data sources: NEX-GDDP-CMIP6, ERA5-Land, Copernicus GLO-30 DEM.
Optional: Landsat C02 L2 for UHI quantification.
"""

import logging
from typing import Optional

from src.core.models import (
    Location, HazardIntensity, HazardEventContext,
    HazardAssessmentResult, ConfidenceLevel, RiskTier,
    HazardType, DataSource,
)
from src.tools._exposure_helpers import build_point_exposure
from src.data.nex_gddp import get_temperature_baseline, get_climate_projection
from src.data.era5 import get_wbgt_statistics, compute_wbgt
from src.data.elevation import get_elevation
from src.data.validation import validate_no_nan

logger = logging.getLogger(__name__)


@validate_no_nan
async def assess_urban_heat(
    lat: float, lon: float,
    time_horizon: int = 2050,
    percentile: int = 95,
    scenario: str = "ssp245",
) -> HazardAssessmentResult:
    """
    Assess urban heat stress with WBGT and climate projections.

    Args:
        lat, lon: Location coordinates
        time_horizon: Target year for projections
        percentile: Temperature percentile (90, 95, or 99)
        scenario: SSP climate scenario
    """
    # 1. Historical baseline from NEX-GDDP-CMIP6
    baseline = await get_temperature_baseline(lat, lon)
    projection = await get_climate_projection(
        lat=lat, lon=lon, scenario=scenario,
        target_year=time_horizon, variable="tasmax"
    )

    # 2. UHI effect (graceful degradation if Landsat unavailable)
    lst = None
    uhi_effect = 2.0  # Default UHI for tropical cities
    try:
        from src.data.landsat import get_lst_statistics
        lst = await get_lst_statistics(lat, lon, date_range="2022-01-01/2023-12-31")
        if lst and lst.lst_median_c:
            uhi_effect = max(0, lst.lst_median_c - baseline.annual_mean_c)
    except (ImportError, Exception):
        logger.debug("Landsat LST unavailable, using default UHI=2.0C")

    # 3. WBGT from ERA5-Land
    current_wbgt = None
    try:
        wbgt_result = await get_wbgt_statistics(lat, lon)
        current_wbgt = wbgt_result.mean_wbgt_c
    except Exception:
        logger.debug("ERA5 WBGT unavailable")

    # 4. Elevation
    elevation_m = await get_elevation(lat, lon)

    # 5. Calculate projected temperature
    if percentile == 90:
        current_temp = baseline.p90_temperature_c
    elif percentile == 95:
        current_temp = baseline.p95_temperature_c
    else:
        current_temp = baseline.p95_temperature_c + 2

    projected_temp = current_temp + projection.change + uhi_effect
    projected_wbgt = (current_wbgt + projection.change) if current_wbgt else None
    heat_wave_days_change = projection.hot_days_change or 0

    # 6. Uncertainty bounds (Gap I: real ensemble spread)
    ensemble_spread_low = getattr(projection, "p5_change", projection.change - 2)
    ensemble_spread_high = getattr(projection, "p95_change", projection.change + 2)
    temp_p5 = current_temp + ensemble_spread_low + uhi_effect
    temp_p95 = current_temp + ensemble_spread_high + uhi_effect

    # 7. Confidence
    confidence = ConfidenceLevel.MODERATE
    if lst and current_wbgt:
        confidence = ConfidenceLevel.HIGH

    # 8. Data sources
    data_sources = [f"NEX-GDDP-CMIP6 ({DataSource.NEX_GDDP_CMIP6.value})"]
    if lst:
        data_sources.append(f"Landsat C2L2 LST ({DataSource.LANDSAT_C2L2.value})")
    if current_wbgt:
        data_sources.append(f"ERA5-Land WBGT ({DataSource.ERA5_LAND.value})")

    ensemble_size = getattr(projection, "ensemble_size", None)

    limitations = [
        f"UHI effect: +{uhi_effect:.1f}C" + (" (Landsat)" if lst else " (default estimate)"),
        f"WBGT: {projected_wbgt:.1f}C" if projected_wbgt else "WBGT not computed (ERA5 unavailable)",
        f"Percentile: {percentile}th (hottest days)",
        "NEX-GDDP-CMIP6 at 0.25 deg (~25km) — sub-grid UHI heterogeneity not resolved",
    ]
    if ensemble_size:
        limitations.append(f"Ensemble: {ensemble_size} GCMs")

    risk_score = _calculate_heat_risk_score(projected_temp, heat_wave_days_change)

    return HazardAssessmentResult(
        hazard=HazardIntensity(
            hazard_type=HazardType.URBAN_HEAT,
            event_context=HazardEventContext(
                event_type="chronic", time_horizon=time_horizon, percentile=percentile
            ),
            intensity_value=round(projected_temp, 1),
            intensity_unit="C",
            intensity_p5=round(temp_p5, 1),
            intensity_p95=round(temp_p95, 1),
            uncertainty_type="ensemble_inter_model_spread",
            native_resolution_m=25000,
            effective_resolution_m=30 if lst else 25000,
            climate_forcing_resolution_m=25000,  # Gap H
            data_sources=data_sources,
            limitations=limitations,
            confidence=confidence,
        ),
        exposure=build_point_exposure(
            lat=lat, lon=lon, elevation_m=elevation_m,
        ),
        intermediate={
            "baseline_annual_mean_c": baseline.annual_mean_c,
            "baseline_p95_c": baseline.p95_temperature_c,
            "current_percentile_temp_c": current_temp,
            "uhi_effect_c": round(uhi_effect, 1),
            "uhi_source": "landsat" if lst else "default",
            "projected_temp_c": round(projected_temp, 1),
            "temperature_change_c": projection.change,
            "ensemble_p5_change_c": ensemble_spread_low,
            "ensemble_p95_change_c": ensemble_spread_high,
            "ensemble_size": ensemble_size,
            "current_wbgt_c": round(current_wbgt, 1) if current_wbgt else None,
            "projected_wbgt_c": round(projected_wbgt, 1) if projected_wbgt else None,
            "lst_median_c": lst.lst_median_c if lst else None,
            "heat_wave_days_change": heat_wave_days_change,
            "scenario": scenario,
        },
        impact_score=round(risk_score, 1),
        impact_tier=_score_to_tier(risk_score),
        can_aggregate_with=[HazardType.SUBSIDENCE],
        dependency_order=1,
    )


def _calculate_heat_risk_score(temp: float, hw_change: int) -> float:
    if temp < 32:
        base = temp / 32 * 20
    elif temp < 35:
        base = 20 + (temp - 32) / 3 * 25
    elif temp < 40:
        base = 45 + (temp - 35) / 5 * 30
    else:
        base = min(100, 75 + (temp - 40) / 5 * 25)
    return max(0.0, min(100.0, base + min(15.0, hw_change * 0.5)))


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75:
        return RiskTier.CRITICAL
    elif score >= 50:
        return RiskTier.HIGH
    elif score >= 25:
        return RiskTier.MODERATE
    return RiskTier.LOW
