# src/tools/landslide_tools.py
"""
Landslide susceptibility assessment with multi-factor scoring.

v3.2: Gap H (climate_forcing_resolution_m), Gap I (ensemble tracking),
      Gap R (@validate_no_nan). Core physics unchanged from v3.1.

Data sources: GLO-30 DEM, NEX-GDDP-CMIP6, SoilGrids v2, Sentinel-2 L2A.
"""

import logging
from typing import Optional

from src.core.models import (
    Location, HazardIntensity, HazardEventContext,
    HazardAssessmentResult, ConfidenceLevel, RiskTier,
    HazardType, DataSource,
)
from src.tools._exposure_helpers import build_point_exposure
from src.data.elevation import get_slope, get_elevation
from src.data.nex_gddp import get_extreme_precipitation
from src.data.validation import validate_no_nan

logger = logging.getLogger(__name__)


@validate_no_nan
async def assess_landslide(
    lat: float, lon: float,
    return_period: int = 100,
    scenario: str = "historical",
) -> HazardAssessmentResult:
    """
    Assess landslide susceptibility using multi-factor weighted model.
    Weights: 40% slope + 25% soil + 20% vegetation + 15% rainfall.
    """
    # 1. Slope from DEM
    slope_result = await get_slope(lat, lon)
    elevation_m = await get_elevation(lat, lon)
    slope = slope_result.slope_degrees
    base_susceptibility = _slope_to_susceptibility(slope)

    # 2. Rainfall trigger (Gap I: returns real ensemble_size)
    precip_result = await get_extreme_precipitation(
        lat=lat, lon=lon, scenario=scenario, return_period=return_period
    )
    threshold_precip = await get_extreme_precipitation(
        lat=lat, lon=lon, scenario="historical", return_period=10
    )
    trigger_ratio = precip_result.precip_mm_per_day / max(0.1, threshold_precip.precip_mm_per_day)
    triggered = trigger_ratio >= 1.0

    # 3. Soil susceptibility (graceful degradation)
    soil_factor = 0.5
    try:
        from src.data.soilgrids import get_soil_properties
        soil = await get_soil_properties(lat, lon)
        clay_factor = min(1.0, (getattr(soil, "clay_pct", 30) or 30) / 60)
        sand_factor = 1.0 - min(1.0, (getattr(soil, "sand_pct", 40) or 40) / 80)
        soil_factor = (clay_factor + sand_factor) / 2
    except (ImportError, Exception):
        logger.debug("SoilGrids unavailable, using default soil_factor=0.5")

    # 4. Vegetation stability (graceful degradation)
    veg_factor = 0.5
    try:
        from src.data.sentinel2 import get_ndvi_statistics
        ndvi = await get_ndvi_statistics(lat, lon, date_range="2022-01-01/2023-12-31")
        if ndvi and ndvi.ndvi_median is not None:
            veg_factor = 1.0 - min(1.0, ndvi.ndvi_median / 0.7)
    except (ImportError, Exception):
        logger.debug("Sentinel-2 NDVI unavailable, using default veg_factor=0.5")

    # 5. Multi-factor weighted score
    combined_score = (
        0.40 * base_susceptibility
        + 0.25 * (soil_factor * 100)
        + 0.20 * (veg_factor * 100)
        + 0.15 * (min(100, trigger_ratio * 30))
    )
    if triggered:
        combined_score = min(100, combined_score * 1.2)

    data_sources = [
        f"Copernicus GLO-30 DEM ({DataSource.COPERNICUS_GLO30.value})",
        f"NEX-GDDP-CMIP6 precipitation ({DataSource.NEX_GDDP_CMIP6.value})",
    ]
    confidence = ConfidenceLevel.MODERATE
    if soil_factor != 0.5:
        data_sources.append(f"SoilGrids v2 clay/sand ({DataSource.SOILGRIDS_V2.value})")
    if veg_factor != 0.5:
        data_sources.append(f"Sentinel-2 NDVI ({DataSource.SENTINEL2_L2A.value})")

    limitations = [
        "No geology/lithology beyond soil texture",
        "Simplified rainfall-based triggering (no antecedent moisture)",
        "Weighted factor model, not physics-based slope stability",
    ]
    ensemble_size = getattr(precip_result, "ensemble_size", None)
    if ensemble_size:
        limitations.append(f"Ensemble: {ensemble_size} GCMs")

    return HazardAssessmentResult(
        hazard=HazardIntensity(
            hazard_type=HazardType.LANDSLIDE,
            event_context=HazardEventContext(
                event_type="acute", return_period_years=return_period
            ),
            intensity_value=round(combined_score, 1),
            intensity_unit="susceptibility_score",
            intensity_p5=round(combined_score * 0.7, 1),
            intensity_p95=round(min(100, combined_score * 1.3), 1),
            uncertainty_type="multi_factor_weighting",
            native_resolution_m=30,
            effective_resolution_m=30,
            climate_forcing_resolution_m=25000,  # Gap H
            data_sources=data_sources,
            limitations=limitations,
            confidence=confidence,
        ),
        exposure=build_point_exposure(
            lat=lat, lon=lon, elevation_m=elevation_m,
            slope_degrees=slope,
        ),
        intermediate={
            "slope_degrees": slope,
            "base_susceptibility": round(base_susceptibility, 1),
            "soil_factor": round(soil_factor, 3),
            "vegetation_factor": round(veg_factor, 3),
            "trigger_ratio": round(trigger_ratio, 2),
            "triggered": triggered,
            "combined_score": round(combined_score, 1),
            "precip_mm_day": round(precip_result.precip_mm_per_day, 1),
        },
        impact_score=round(combined_score, 1),
        impact_tier=_score_to_tier(combined_score),
        can_aggregate_with=[HazardType.RIVERINE_FLOOD, HazardType.TROPICAL_CYCLONE],
        dependency_order=6,
    )


def _slope_to_susceptibility(slope: float) -> float:
    if slope < 5:
        return slope / 5 * 10
    elif slope < 15:
        return 10 + (slope - 5) / 10 * 20
    elif slope < 25:
        return 30 + (slope - 15) / 10 * 25
    elif slope < 35:
        return 55 + (slope - 25) / 10 * 25
    else:
        return min(100, 80 + (slope - 35) / 20 * 20)


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75:
        return RiskTier.CRITICAL
    elif score >= 50:
        return RiskTier.HIGH
    elif score >= 25:
        return RiskTier.MODERATE
    return RiskTier.LOW
