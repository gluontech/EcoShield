# src/tools/storm_surge_tools.py
"""
Parametric storm surge assessment.

Physics: Simplified Jelesnianski (SLOSH-lite) parametric surge model.
  - Surge height from cyclone wind speed and pressure deficit
  - Coastal amplification from GEBCO bathymetry (Green's law)
  - Subsidence-adjusted elevation for inundation depth
  - Requires cyclone_params dict from cyclone_tools.py intermediate output

v3.2 Changes:
  - Gap R: @validate_no_nan decorator
  - Cyclone params now use Holland (2008) revised pressure estimates (Gap P)
"""

import logging
from typing import Optional

from src.core.models import (
    Location, HazardIntensity, HazardEventContext,
    HazardAssessmentResult, AdjustedSurface, ConfidenceLevel, RiskTier,
    HazardType, DataSource,
)
from src.tools._exposure_helpers import build_point_exposure
from src.data.elevation import get_elevation
from src.data.validation import validate_no_nan

logger = logging.getLogger(__name__)


@validate_no_nan
async def assess_storm_surge(
    lat: float, lon: float,
    cyclone_params: Optional[dict] = None,
    surface: Optional[AdjustedSurface] = None,
    return_period: int = 100,
) -> HazardAssessmentResult:
    """
    Assess storm surge inundation using parametric model.

    Args:
        lat, lon: Coastal location coordinates
        cyclone_params: From cyclone_tools.py intermediate output
        surface: AdjustedSurface with subsidence correction
        return_period: Return period (reporting only)
    """
    elevation_m = await get_elevation(lat, lon)

    if not cyclone_params:
        return _no_surge_result(lat, lon, elevation_m, return_period)

    wind_kts = cyclone_params.get("max_wind_kts", 0)
    if not wind_kts:
        # Convert from m/s if available
        wind_ms = cyclone_params.get("max_wind_ms", 0)
        wind_kts = wind_ms / 0.5144

    pressure_mb = cyclone_params.get("central_pressure_mb", 1010)
    forward_speed_ms = cyclone_params.get("forward_speed_ms", 5.0)

    # 1. Base surge from wind setup (simplified Jelesnianski)
    pressure_deficit_mb = 1013 - pressure_mb
    wind_surge_m = 0.005 * wind_kts
    pressure_surge_m = pressure_deficit_mb * 0.01
    base_surge = wind_surge_m + pressure_surge_m

    # 2. Forward speed effect
    speed_factor = 1.0 + 0.05 * (forward_speed_ms - 5.0)
    base_surge *= max(0.5, min(1.5, speed_factor))

    # 3. Bathymetry amplification (Green's law) - graceful degradation
    shelf_factor = 1.0
    try:
        from src.data.gebco import get_bathymetry
        bathy = await get_bathymetry(lat, lon)
        shelf_depth = abs(bathy.depth_m)
        shelf_factor = max(0.5, min(2.0, 50 / max(1, shelf_depth)))
    except (ImportError, Exception):
        logger.debug("GEBCO bathymetry unavailable, using default shelf_factor=1.0")

    total_surge = base_surge * shelf_factor

    # 4. Subsidence correction
    subsidence_effect = 0.0
    adjustments = []
    if surface and surface.subsidence_applied:
        subsidence_effect = surface.subsidence_adjustment_m
        adjustments.append("subsidence")

    effective_elevation = elevation_m - subsidence_effect
    inundation_depth = max(0, total_surge - effective_elevation)

    data_sources = [
        f"IBTrACS cyclone params ({DataSource.IBTRACS_V04.value})",
        f"Copernicus GLO-30 DEM ({DataSource.COPERNICUS_GLO30.value})",
    ]
    if shelf_factor != 1.0:
        data_sources.append(f"GEBCO 2024 bathymetry ({DataSource.GEBCO_2024.value})")

    risk_score = _calculate_surge_risk_score(inundation_depth)

    return HazardAssessmentResult(
        hazard=HazardIntensity(
            hazard_type=HazardType.STORM_SURGE,
            event_context=HazardEventContext(
                event_type="acute", return_period_years=return_period
            ),
            intensity_value=round(inundation_depth, 2),
            intensity_unit="m",
            intensity_p5=round(inundation_depth * 0.7, 2),
            intensity_p95=round(inundation_depth * 1.4, 2),
            uncertainty_type="parametric_model_uncertainty",
            native_resolution_m=30,
            effective_resolution_m=100,
            data_sources=data_sources,
            limitations=[
                "Parametric surge model (not full ADCIRC/SLOSH simulation)",
                "No wave setup or rainfall contribution",
                f"Shelf amplification factor: {shelf_factor:.2f}",
                "Assumes shore-normal approach angle",
            ],
            confidence=ConfidenceLevel.LOW,
        ),
        exposure=build_point_exposure(
            lat=lat, lon=lon, elevation_m=elevation_m,
            adjustments_applied=adjustments,
        ),
        intermediate={
            "cyclone_wind_kts": round(wind_kts, 0),
            "pressure_deficit_mb": round(pressure_deficit_mb, 0),
            "base_surge_m": round(base_surge, 2),
            "shelf_factor": round(shelf_factor, 2),
            "total_surge_m": round(total_surge, 2),
            "effective_elevation_m": round(effective_elevation, 2),
            "inundation_depth_m": round(inundation_depth, 2),
            "subsidence_effect_m": round(subsidence_effect, 3),
        },
        impact_score=round(risk_score, 1),
        impact_tier=_score_to_tier(risk_score),
        can_aggregate_with=[HazardType.COASTAL_FLOOD, HazardType.RIVERINE_FLOOD,
                            HazardType.TROPICAL_CYCLONE],
        dependency_order=3,
    )


def _no_surge_result(lat: float, lon: float, elevation_m: float, rp: int) -> HazardAssessmentResult:
    return HazardAssessmentResult(
        hazard=HazardIntensity(
            hazard_type=HazardType.STORM_SURGE,
            event_context=HazardEventContext(event_type="acute", return_period_years=rp),
            intensity_value=0.0, intensity_unit="m",
            intensity_p5=0.0, intensity_p95=0.0,
            uncertainty_type="no_cyclone_exposure",
            native_resolution_m=30, effective_resolution_m=100,
            data_sources=[f"IBTrACS v04r01 ({DataSource.IBTRACS_V04.value})"],
            limitations=["No significant cyclone exposure at this location"],
            confidence=ConfidenceLevel.HIGH,
        ),
        exposure=build_point_exposure(
            lat=lat, lon=lon, elevation_m=elevation_m,
        ),
        intermediate={"cyclone_params": None, "total_surge_m": 0},
        impact_score=0.0,
        impact_tier=RiskTier.LOW,
        can_aggregate_with=[HazardType.COASTAL_FLOOD],
        dependency_order=3,
    )


def _calculate_surge_risk_score(depth: float) -> float:
    if depth <= 0:
        return 0.0
    elif depth < 0.5:
        return depth / 0.5 * 25
    elif depth < 1.5:
        return 25 + (depth - 0.5) * 25
    elif depth < 3.0:
        return 50 + (depth - 1.5) / 1.5 * 25
    else:
        return min(100, 75 + (depth - 3.0) / 3.0 * 25)


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75:
        return RiskTier.CRITICAL
    elif score >= 50:
        return RiskTier.HIGH
    elif score >= 25:
        return RiskTier.MODERATE
    return RiskTier.LOW
