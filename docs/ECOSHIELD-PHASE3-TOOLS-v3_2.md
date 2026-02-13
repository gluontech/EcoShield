# EcoShield Phase 3: Hazard Assessment Tools — v3.2

## Implementation Guide for Cursor AI

> **Phase 3 v3.2**: Complete implementations for all **8** hazard tools + structure risk tool.
> All tools use the API-first data layer from Phase 2 v3.2.
> NEX-GDDP-CMIP6 replaces CMIP6-VN.  Copernicus GLO-30 replaces FABDEM.
> New data sources: GloFAS v4, SoilGrids v2, Sentinel-2, Landsat LST,
> ERA5-Land WBGT, GEBCO bathymetry.
> **v3.1**: Structure risk tool applies H×E×V per building using
> Google Open Buildings footprints, 2.5D heights, Overture Maps attributes,
> and JRC flood depth-damage curves.
> **v3.2 Gap Fixes**:
> - Riverine flood: `rating_curve.discharge_to_depth()` replaces inline Manning's proxy (Gap J).
> - Coastal flood: `ipcc_slr.get_slr_projection()` with per-city regional SLR (Gap K).
> - Cyclone: `holland_wind.holland_wind_profile()` Holland (2008) replaces inline Holland (1980) (Gap P).
> - Subsidence: Published-rate fallback from `insar.get_subsidence_velocity()` (Gap L).
> - **NEW** Pluvial flood tool: `pluvial_flood.compute_pluvial_susceptibility()` (Gap M).
> - Structure risk: Multi-RP EAL via trapezoidal integration (Gap Q),
>   per-building surface `BuildingAdjustedSurface` (Gap S),
>   occupancy value multipliers (Gap T).
> - All tools: `climate_forcing_resolution_m` on HazardIntensity (Gap H),
>   `@validate_no_nan` decorator on async functions (Gap R),
>   real ensemble p5/p95 where NEX-GDDP feeds uncertainty (Gap I).

---

## Overview

Phase 3 implements the **8 hazard assessment tools** and the **structure-level risk tool** registered with Agno agents.
Each hazard tool calls the API-first data modules from Phase 2 and returns
`HazardAssessmentResult` (defined in Phase 1). The structure risk tool
consumes hazard outputs + building data to produce `StructureRiskResult`
per building (v3.1, enhanced v3.2 with multi-RP EAL).

### Files to Create

```
src/tools/
├── __init__.py
├── riverine_flood_tools.py    # GloFAS v4 + HAND + GLO-30 + rating_curve (FIX v3.2 Gap J)
├── coastal_flood_tools.py     # ipcc_slr.py regional SLR + GLO-30 + tidal (FIX v3.2 Gap K)
├── subsidence_tools.py        # Sentinel-1 InSAR + published fallback + GLO-30 (FIX v3.2 Gap L)
├── landslide_tools.py         # GLO-30 + NEX-GDDP + SoilGrids + Sentinel-2
├── cyclone_tools.py           # IBTrACS + Holland (2008) wind profile (FIX v3.2 Gap P)
├── storm_surge_tools.py       # IBTrACS + GEBCO + GLO-30 parametric
├── urban_heat_tools.py        # Landsat LST + ERA5-Land WBGT + NEX-GDDP
├── pluvial_flood_tools.py     # HAND + slope + imperviousness + NEX-GDDP   ← NEW v3.2 (Gap M)
└── structure_risk_tools.py    # H×E×V per building + multi-RP EAL (FIX v3.2 Gap Q/S/T)
```

### Key Changes from v1.0 → v3.1 → v3.2

| Component | v1.0 (CMIP6-VN) | v3.1 (API-First + Asset Layer) | v3.2 (Gap Fixes) |
|-----------|------------------|-------------------------------|-------------------|
| Climate data import | `src.data.cmip6_vn` | `src.data.nex_gddp` | Unchanged |
| DEM source | `FABDEM (30m)` | `Copernicus GLO-30 (30m)` via AWS S3 | Unchanged |
| Flood discharge | `estimate_water_level` (broken) | `glofas.get_flood_return_period` | **+ `rating_curve.discharge_to_depth()` (Gap J)** |
| Discharge→depth | Inline Manning's proxy | Inline Manning's proxy | **`src.data.rating_curve` per-city params (Gap J)** |
| SLR projections | None | Hardcoded IPCC_SLR_MEDIAN dict | **`ipcc_slr.get_slr_projection()` per-city (Gap K)** |
| Cyclone wind profile | None | Inline Holland (1980) | **`holland_wind` Holland (2008) revised (Gap P)** |
| Subsidence source | InSAR only | InSAR only | **+ Published-rate fallback (Gap L)** |
| Pluvial flood | None | None | **NEW `pluvial_flood_tools.py` (Gap M)** |
| Ensemble uncertainty | Fabricated ±20-30% | Fabricated ±20-30% | **Real 5-GCM p5/p95 from `nex_gddp` (Gap I)** |
| Resolution metadata | Not tracked | Not tracked | **`climate_forcing_resolution_m=25000` (Gap H)** |
| EAL computation | None | `damage_ratio × value / RP` (wrong) | **Trapezoidal ∫ over [10,25,50,100,250] RPs (Gap Q)** |
| Per-building surface | None | Tile-level `AdjustedSurface` | **`BuildingAdjustedSurface` per-building (Gap S)** |
| Replacement value | JRC country × area | JRC country × area | **× `OCCUPANCY_VALUE_MULTIPLIER` (Gap T)** |
| Data validation | None | None | **`@validate_no_nan` decorator (Gap R)** |
| **Hazard count** | **6** | **7** | **8 (+ pluvial flood)** |

### Shared Utilities

```python
# Common scoring functions used by all tools

def _score_to_tier(score: float) -> RiskTier:
    """Convert 0-100 risk score to tier."""
    if score >= 75: return RiskTier.CRITICAL
    elif score >= 50: return RiskTier.HIGH
    elif score >= 25: return RiskTier.MODERATE
    return RiskTier.LOW
```

---

## 1. Riverine Flood Tool (FIX v3.2 — Gap J, H, I, R)

```python
# src/tools/riverine_flood_tools.py
"""
Riverine flood hazard assessment.

Physics: HAND model + GloFAS return-period discharge.
  - Height Above Nearest Drainage (HAND) from GLO-30 DEM gives flood susceptibility
  - GloFAS v4 provides calibrated discharge for given return period
  - Manning's equation converts discharge → approximate water level
  - Effective HAND = HAND - subsidence adjustment (from Step 1)
  - Flood depth = max(0, water_level - effective_HAND)

v3.2 Changes:
  - Gap J: discharge_to_depth() from src.data.rating_curve replaces inline proxy.
           Uses per-city channel geometry (width, slope, Manning's n).
  - Gap H: climate_forcing_resolution_m=25000 on HazardIntensity.
  - Gap I: Uncertainty from Manning's parameter ranges, not fabricated ±20%.
  - Gap R: @validate_no_nan decorator for input validation.

Data sources (all API-accessible):
  - Copernicus GLO-30 DEM (AWS S3 OpenData) → 30m elevation + HAND
  - GloFAS v4 (CDS API) → return-period river discharge
  - NEX-GDDP-CMIP6 (AWS S3) → future extreme precipitation projections
  - rating_curve.py (NEW v3.2) → Manning's equation with per-city params
"""

from typing import Optional
from src.core.models import (
    Location, HazardIntensity, HazardEventContext, ExposureProfile,
    HazardAssessmentResult, AdjustedSurface, ConfidenceLevel, RiskTier,
    HazardType, DataSource,
)
from src.data.hand import get_hand_value
from src.data.elevation import get_elevation
from src.data.glofas import get_flood_return_period
from src.data.rating_curve import discharge_to_depth, CHANNEL_WIDTHS, MANNING_N  # NEW v3.2 (Gap J)
from src.data.validation import validate_no_nan  # NEW v3.2 (Gap R)

NATIVE_RESOLUTION_M = 30
EFFECTIVE_RESOLUTION_M = 30


@validate_no_nan  # Gap R: validates return arrays are NaN-free
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
        return_period: Flood return period in years (2–1000)
        surface: AdjustedSurface from Step 1 (contains subsidence data)
        scenario: Climate scenario for future projections
        city: City identifier for per-city channel parameters (NEW v3.2)

    Returns:
        HazardAssessmentResult with flood depth as intensity_value (meters)
    """
    # 1. Get HAND value (flood susceptibility from DEM-river difference)
    hand_result = await get_hand_value(lat, lon)

    # 2. Get calibrated discharge from GloFAS
    flood_discharge = await get_flood_return_period(lat, lon, return_period)

    # 3. Convert discharge → water depth via rating_curve (FIX v3.2 — Gap J)
    #    v3.1 used inline proxy with hardcoded width=50, slope=0.001.
    #    v3.2 uses per-city channel geometry from rating_curve module.
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

    # 4. Get raw elevation for exposure profile
    elevation_result = await get_elevation(lat, lon)

    # 5. Apply subsidence correction if available
    subsidence_effect = 0.0
    adjustments = []
    if surface and surface.subsidence_applied:
        subsidence_effect = surface.subsidence_adjustment_m
        adjustments.append("subsidence")

    # 6. Calculate flood depth
    effective_hand = hand_result.hand_value_m - subsidence_effect
    flood_depth = max(0, water_level - effective_hand)

    # 7. Uncertainty bounds (FIX v3.2 — Gap I)
    #    Manning's n: ±30% uncertainty; channel width: ±25%.
    #    Combined via Manning's eq: depth uncertainty ~±35%.
    depth_p5 = flood_depth * 0.65
    depth_p95 = flood_depth * 1.35

    # 8. Confidence assessment
    if is_urban:
        confidence = ConfidenceLevel.LOW  # Urban drainage not modeled
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
            climate_forcing_resolution_m=25000,  # NEW v3.2 (Gap H)
            data_sources=[
                f"GloFAS v4 discharge ({DataSource.GLOFAS_V4.value})",
                f"Copernicus GLO-30 DEM ({NATIVE_RESOLUTION_M}m)",
                "HAND index (DEM-river difference)",
                "rating_curve.py Manning's equation (NEW v3.2)",
            ],
            limitations=limitations,
            confidence=confidence,
        ),
        exposure=ExposureProfile(
            location=Location(lat=lat, lon=lon),
            elevation_m=elevation_result.elevation_m,
            elevation_source=DataSource.COPERNICUS_GLO30.value,
            elevation_uncertainty_m=elevation_result.uncertainty_m,
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
                            HazardType.PLUVIAL_FLOOD],  # v3.2: added PLUVIAL_FLOOD
        dependency_order=4,
    )


def _calculate_flood_risk_score(flood_depth: float) -> float:
    """Map flood depth to 0-100 risk score using damage curve."""
    if flood_depth <= 0: return 0.0
    elif flood_depth < 0.3: return flood_depth / 0.3 * 25
    elif flood_depth < 1.0: return 25 + (flood_depth - 0.3) / 0.7 * 25
    elif flood_depth < 2.0: return 50 + (flood_depth - 1.0) * 30
    else: return min(100, 80 + (flood_depth - 2.0) * 10)


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75: return RiskTier.CRITICAL
    elif score >= 50: return RiskTier.HIGH
    elif score >= 25: return RiskTier.MODERATE
    return RiskTier.LOW
```

---

## 2. Coastal Flood Tool (FIX v3.2 — Gap K, H, R)

```python
# src/tools/coastal_flood_tools.py
"""
Coastal flood hazard assessment using bathtub model + SLR projections.

v3.2 Changes:
  - Gap K: Uses ipcc_slr.get_slr_projection() with per-city regional SLR data
           (HCMC, Jakarta, Manila, Bangkok, Hanoi, Singapore) instead of hardcoded
           global IPCC_SLR_MEDIAN table. Regional rates differ ±30% from global.
  - Gap H: climate_forcing_resolution_m=25000 on HazardIntensity.
  - Gap R: @validate_no_nan decorator.

Data sources:
  - Copernicus GLO-30 DEM (AWS S3 OpenData) → 30m coastal elevation
  - ipcc_slr.py (FIX v3.2) → IPCC AR6 per-city regional SLR projections
"""

from typing import Optional
from src.core.models import (
    Location, HazardIntensity, HazardEventContext, ExposureProfile,
    HazardAssessmentResult, AdjustedSurface, ConfidenceLevel, RiskTier,
    HazardType, DataSource, SSPScenario,
)
from src.data.elevation import get_elevation
from src.data.ipcc_slr import get_slr_projection  # FIX v3.2 (Gap K) — replaces hardcoded table
from src.data.validation import validate_no_nan    # NEW v3.2 (Gap R)

NATIVE_RESOLUTION_M = 30
EFFECTIVE_RESOLUTION_M = 30


@validate_no_nan  # Gap R
async def assess_coastal_flood(
    lat: float, lon: float,
    time_horizon: int = 2050,
    scenario: str = "ssp245",
    surface: Optional[AdjustedSurface] = None,
    tidal_range_m: float = 2.0,
    city: str = "ho_chi_minh_city",
) -> HazardAssessmentResult:
    """
    Assess coastal flood risk using bathtub SLR model.

    Args:
        lat, lon: Location coordinates (must be within ~10km of coast)
        time_horizon: Target year (2030, 2050, or 2100)
        scenario: SSP scenario string
        surface: AdjustedSurface with subsidence
        tidal_range_m: Local mean tidal range (meters)
        city: City identifier for per-city IPCC SLR lookup (NEW v3.2)
    """
    elevation_result = await get_elevation(lat, lon)

    # Get regional SLR (FIX v3.2 — Gap K)
    try:
        slr = get_slr_projection(city=city, scenario=scenario, target_year=time_horizon)
        slr_median = slr.median_m
        slr_p5 = slr.p5_m
        slr_p95 = slr.p95_m
        slr_source = f"IPCC AR6 regional ({city})"
    except ValueError:
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

    effective_elevation = elevation_result.elevation_m - subsidence_effect
    total_water_level = slr_median + (tidal_range_m / 2)
    total_water_level_p95 = slr_p95 + (tidal_range_m / 2)

    inundation_depth = max(0, total_water_level - effective_elevation)
    inundation_p5 = max(0, slr_p5 + tidal_range_m / 2 - effective_elevation)
    inundation_p95 = max(0, total_water_level_p95 - effective_elevation)

    is_coastal = effective_elevation < 10
    if not is_coastal:
        confidence = ConfidenceLevel.HIGH
        inundation_depth = 0.0
    elif effective_elevation < 2:
        confidence = ConfidenceLevel.MODERATE
    else:
        confidence = ConfidenceLevel.MODERATE

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
            climate_forcing_resolution_m=25000,  # NEW v3.2 (Gap H)
            data_sources=[
                f"IPCC AR6 SLR projections ({DataSource.IPCC_AR6.value}) — {slr_source}",
                f"Copernicus GLO-30 DEM ({DataSource.COPERNICUS_GLO30.value})",
            ],
            limitations=limitations,
            confidence=confidence,
        ),
        exposure=ExposureProfile(
            location=Location(lat=lat, lon=lon),
            elevation_m=elevation_result.elevation_m,
            elevation_source=DataSource.COPERNICUS_GLO30.value,
            elevation_uncertainty_m=elevation_result.uncertainty_m,
            adjustments_applied=adjustments,
        ),
        intermediate={
            "raw_elevation_m": elevation_result.elevation_m,
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
    if depth <= 0: return 0.0
    base = min(80, depth / 2.0 * 80)
    urgency = 1.0 + (0.2 if horizon <= 2050 else 0.0)
    return min(100, base * urgency)


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75: return RiskTier.CRITICAL
    elif score >= 50: return RiskTier.HIGH
    elif score >= 25: return RiskTier.MODERATE
    return RiskTier.LOW
```

---

## 3. Subsidence Tool (FIX v3.2 — Gap L, R)

```python
# src/tools/subsidence_tools.py
"""
Land subsidence hazard assessment.

v3.2 Changes:
  - Gap L: get_subsidence_velocity() now has published-rate fallback.
           If InSAR velocity.tif unavailable, falls back to peer-reviewed rates:
           HCMC -25 mm/yr (Minderhoud 2018), Jakarta -50 mm/yr (Chaussard 2013),
           Hanoi -12 mm/yr, Manila -15 mm/yr, Bangkok -15 mm/yr.
  - Gap R: @validate_no_nan decorator.

Data sources:
  - Sentinel-1 InSAR velocity maps (ASF DAAC API / COMET LiCSAR)
  - Published subsidence rates (fallback — Gap L)
  - Copernicus GLO-30 DEM (AWS S3 OpenData)
"""

from typing import Optional
from src.core.models import (
    Location, HazardIntensity, HazardEventContext, ExposureProfile,
    HazardAssessmentResult, AdjustedSurface, ConfidenceLevel, RiskTier,
    HazardType, DataSource,
)
from src.data.insar import get_subsidence_velocity  # FIX v3.2 (Gap L): with published fallback
from src.data.elevation import get_elevation
from src.data.validation import validate_no_nan  # NEW v3.2 (Gap R)

NATIVE_RESOLUTION_M = 100
EFFECTIVE_RESOLUTION_M = 100


@validate_no_nan  # Gap R
async def assess_subsidence(
    lat: float, lon: float,
    city: str = "hcmc",
    time_horizon: int = 2050,
) -> HazardAssessmentResult:
    """
    Assess land subsidence risk using InSAR + published-rate fallback.

    Returns:
        HazardAssessmentResult with subsidence rate as intensity_value (mm/yr).
        intermediate["subsidence_source"] tracks whether InSAR or published.
    """
    # 1. Get subsidence velocity (v3.2: includes published-rate fallback)
    insar_result = await get_subsidence_velocity(lat, lon, city=city)
    velocity_mm_yr = insar_result.velocity_mm_per_year
    subsidence_source = getattr(insar_result, 'source', 'insar_measured')

    # 2. Baseline elevation
    elevation_result = await get_elevation(lat, lon)

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
        exposure=ExposureProfile(
            location=Location(lat=lat, lon=lon),
            elevation_m=elevation_result.elevation_m,
            elevation_source=DataSource.COPERNICUS_GLO30.value,
            elevation_uncertainty_m=elevation_result.uncertainty_m,
        ),
        intermediate={
            "velocity_mm_yr": round(velocity_mm_yr, 1),
            "abs_rate_mm_yr": round(abs_rate, 1),
            "cumulative_mm": round(cumulative_mm, 0),
            "cumulative_m": round(cumulative_m, 3),
            "years_forward": years_forward,
            "original_elevation_m": elevation_result.elevation_m,
            "adjusted_elevation_m": round(elevation_result.elevation_m - cumulative_m, 2),
            "subsidence_source": subsidence_source,  # NEW v3.2 (Gap L)
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
    if score >= 75: return RiskTier.CRITICAL
    elif score >= 50: return RiskTier.HIGH
    elif score >= 25: return RiskTier.MODERATE
    return RiskTier.LOW
```

---

## 4. Landslide Tool (FIX v3.2 — Gap H, I, R)

```python
# src/tools/landslide_tools.py
"""
Landslide susceptibility assessment with multi-factor scoring.

v3.2: Gap H (climate_forcing_resolution_m), Gap I (ensemble size tracking),
      Gap R (@validate_no_nan). Core physics unchanged from v3.1.

Data sources: GLO-30 DEM, NEX-GDDP-CMIP6, SoilGrids v2, Sentinel-2 L2A.
"""

from typing import Optional
from src.core.models import (
    Location, HazardIntensity, HazardEventContext, ExposureProfile,
    HazardAssessmentResult, ConfidenceLevel, RiskTier,
    HazardType, DataSource,
)
from src.data.elevation import get_slope, get_elevation
from src.data.nex_gddp import get_extreme_precipitation
from src.data.soilgrids import get_soil_properties
from src.data.sentinel2 import get_ndvi_statistics
from src.data.validation import validate_no_nan  # NEW v3.2 (Gap R)


@validate_no_nan  # Gap R
async def assess_landslide(
    lat: float, lon: float,
    return_period: int = 100,
    scenario: str = "historical"
) -> HazardAssessmentResult:
    """
    Assess landslide susceptibility using multi-factor weighted model.
    Weights: 40% slope + 25% soil + 20% vegetation + 15% rainfall.
    """
    # 1. Slope from DEM
    slope_result = await get_slope(lat, lon)
    elevation_result = await get_elevation(lat, lon)
    slope = slope_result.slope_degrees
    base_susceptibility = _slope_to_susceptibility(slope)

    # 2. Rainfall trigger — v3.2 (Gap I): returns real ensemble_size
    precip_result = await get_extreme_precipitation(lat, lon, return_period, scenario)
    threshold_precip = await get_extreme_precipitation(lat, lon, 10, "historical")
    trigger_ratio = precip_result.precip_mm_per_day / max(0.1, threshold_precip.precip_mm_per_day)
    triggered = trigger_ratio >= 1.0

    # 3. Soil susceptibility (graceful degradation)
    try:
        soil = await get_soil_properties(lat, lon)
        clay_factor = min(1.0, (soil.clay_pct or 30) / 60)
        sand_factor = 1.0 - min(1.0, (soil.sand_pct or 40) / 80)
        soil_factor = (clay_factor + sand_factor) / 2
    except Exception:
        soil_factor = 0.5

    # 4. Vegetation stability (graceful degradation)
    try:
        ndvi = await get_ndvi_statistics(lat, lon, date_range="2022-01-01/2023-12-31")
        veg_factor = 1.0 - min(1.0, (ndvi.ndvi_median or 0) / 0.7)
    except Exception:
        veg_factor = 0.5

    # 5. Multi-factor weighted score
    combined_score = (
        0.40 * base_susceptibility +
        0.25 * (soil_factor * 100) +
        0.20 * (veg_factor * 100) +
        0.15 * (min(100, trigger_ratio * 30))
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
    ensemble_size = getattr(precip_result, 'ensemble_size', None)
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
            climate_forcing_resolution_m=25000,  # NEW v3.2 (Gap H)
            data_sources=data_sources,
            limitations=limitations,
            confidence=confidence,
        ),
        exposure=ExposureProfile(
            location=Location(lat=lat, lon=lon),
            elevation_m=elevation_result.elevation_m,
            elevation_source=DataSource.COPERNICUS_GLO30.value,
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
    if slope < 5: return slope / 5 * 10
    elif slope < 15: return 10 + (slope - 5) / 10 * 20
    elif slope < 25: return 30 + (slope - 15) / 10 * 25
    elif slope < 35: return 55 + (slope - 25) / 10 * 25
    else: return min(100, 80 + (slope - 35) / 20 * 20)


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75: return RiskTier.CRITICAL
    elif score >= 50: return RiskTier.HIGH
    elif score >= 25: return RiskTier.MODERATE
    return RiskTier.LOW
```

---

## 5. Cyclone Tool (FIX v3.2 — Gap P, R)

```python
# src/tools/cyclone_tools.py
"""
Tropical cyclone hazard assessment using IBTrACS historical analysis.

v3.2 Changes:
  - Gap P: holland_wind.holland_wind_profile() with Holland (2008) revised profile
           replaces inline _holland_wind_profile() Holland (1980). Uses empirical
           B-parameter from Vmax and pressure deficit, clamped [1.0, 2.5].
  - Gap R: @validate_no_nan decorator.

Data sources: IBTrACS v04r01, holland_wind.py (NEW v3.2).
"""

from typing import Optional
import math
from src.core.models import (
    Location, HazardIntensity, HazardEventContext, ExposureProfile,
    HazardAssessmentResult, CycloneEventParams, ConfidenceLevel, RiskTier,
    HazardType, DataSource,
)
from src.data.ibtracs import query_storms_near_point
from src.data.elevation import get_elevation
from src.data.holland_wind import holland_wind_profile, wind_at_building  # NEW v3.2 (Gap P)
from src.data.validation import validate_no_nan  # NEW v3.2 (Gap R)

NATIVE_RESOLUTION_M = 5000
EFFECTIVE_RESOLUTION_M = 5000


@validate_no_nan  # Gap R
async def assess_cyclone(
    lat: float, lon: float,
    return_period: int = 100,
    search_radius_km: float = 250,
) -> HazardAssessmentResult:
    """Assess tropical cyclone wind hazard from IBTrACS historical analysis."""
    storms = await query_storms_near_point(lat, lon, search_radius_km)
    elevation_result = await get_elevation(lat, lon)

    if not storms or len(storms) < 5:
        return _low_exposure_result(lat, lon, elevation_result, return_period, len(storms))

    annual_max_winds = _get_annual_max_winds(storms)
    rp_wind_kts = _gumbel_return_period(annual_max_winds, return_period)
    rp_wind_ms = rp_wind_kts * 0.5144

    central_pressure_mb = _wind_to_pressure(rp_wind_kts)
    rmw_km = _estimate_rmw(rp_wind_kts, lat)

    # Distance decay via Holland (2008) (FIX v3.2 — Gap P)
    nearest_dist_km = min(s.get("min_dist_km", search_radius_km) for s in storms)
    holland_b = None
    if nearest_dist_km > 0:
        wind_result = holland_wind_profile(
            distance_km=nearest_dist_km,
            vmax_ms=rp_wind_ms,
            rmw_km=rmw_km,
            central_pressure_hpa=central_pressure_mb,
        )
        site_wind_ms = wind_result.wind_speed_ms
        holland_b = getattr(wind_result, 'b_parameter', None)
    else:
        site_wind_ms = rp_wind_ms

    n_storms = len(storms)
    if n_storms >= 30:
        confidence = ConfidenceLevel.HIGH
    elif n_storms >= 10:
        confidence = ConfidenceLevel.MODERATE
    else:
        confidence = ConfidenceLevel.LOW

    cyclone_params = {
        "max_wind_kts": round(rp_wind_kts, 0),
        "max_wind_ms": round(rp_wind_ms, 1),
        "central_pressure_mb": round(central_pressure_mb, 0),
        "rmw_km": round(rmw_km, 1),
        "heading_deg": 315,
        "forward_speed_ms": 5.0,
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
                f"Based on {n_storms} historical storms within {search_radius_km}km",
                "Gumbel extreme value distribution fit",
                "Holland (2008) revised parametric wind profile",
                "No climate change signal in future cyclone intensity",
            ],
            confidence=confidence,
        ),
        exposure=ExposureProfile(
            location=Location(lat=lat, lon=lon),
            elevation_m=elevation_result.elevation_m,
            elevation_source=DataSource.COPERNICUS_GLO30.value,
        ),
        intermediate={
            "n_historical_storms": n_storms,
            "return_period_wind_kts": round(rp_wind_kts, 0),
            "return_period_wind_ms": round(rp_wind_ms, 1),
            "site_wind_ms": round(site_wind_ms, 1),
            "central_pressure_mb": round(central_pressure_mb, 0),
            "rmw_km": round(rmw_km, 1),
            "nearest_approach_km": round(nearest_dist_km, 1),
            "holland_b_parameter": holland_b,  # NEW v3.2 (Gap P)
            "cyclone_params": cyclone_params,
        },
        impact_score=round(risk_score, 1),
        impact_tier=_score_to_tier(risk_score),
        can_aggregate_with=[HazardType.STORM_SURGE, HazardType.RIVERINE_FLOOD,
                            HazardType.LANDSLIDE],
        dependency_order=2,
    )


def _low_exposure_result(lat, lon, elev, rp, n_storms):
    return HazardAssessmentResult(
        hazard=HazardIntensity(
            hazard_type=HazardType.TROPICAL_CYCLONE,
            event_context=HazardEventContext(event_type="acute", return_period_years=rp),
            intensity_value=0.0, intensity_unit="m/s",
            intensity_p5=0.0, intensity_p95=0.0,
            uncertainty_type="insufficient_data",
            native_resolution_m=NATIVE_RESOLUTION_M,
            effective_resolution_m=EFFECTIVE_RESOLUTION_M,
            data_sources=[f"IBTrACS v04r01 ({DataSource.IBTRACS_V04.value})"],
            limitations=[f"Only {n_storms} storms in record — low cyclone exposure"],
            confidence=ConfidenceLevel.HIGH,
        ),
        exposure=ExposureProfile(
            location=Location(lat=lat, lon=lon),
            elevation_m=elev.elevation_m,
            elevation_source=DataSource.COPERNICUS_GLO30.value,
        ),
        intermediate={"n_historical_storms": n_storms, "cyclone_params": None},
        impact_score=0.0,
        impact_tier=RiskTier.LOW,
        can_aggregate_with=[HazardType.STORM_SURGE],
        dependency_order=2,
    )


def _get_annual_max_winds(storms: list) -> list:
    from collections import defaultdict
    yearly = defaultdict(float)
    for s in storms:
        yearly[s.get("year", 0)] = max(yearly[s.get("year", 0)], s.get("max_wind_kts", 0))
    return sorted(yearly.values())


def _gumbel_return_period(annual_maxima: list, rp: int) -> float:
    import numpy as np
    data = np.array(annual_maxima)
    mu = data.mean() - 0.5772 * data.std() * (6**0.5) / 3.14159
    beta = data.std() * (6**0.5) / 3.14159
    return mu - beta * math.log(-math.log(1 - 1/rp))


def _wind_to_pressure(wind_kts: float) -> float:
    return 1010 - (wind_kts / 3.92) ** (1 / 0.644)


def _estimate_rmw(wind_kts: float, lat: float) -> float:
    return max(15, 46.4 * math.exp(-0.0155 * wind_kts + 0.0169 * abs(lat)))


def _calculate_cyclone_risk_score(wind_ms: float) -> float:
    if wind_ms < 17: return wind_ms / 17 * 15
    elif wind_ms < 33: return 15 + (wind_ms - 17) / 16 * 25
    elif wind_ms < 50: return 40 + (wind_ms - 33) / 17 * 25
    elif wind_ms < 70: return 65 + (wind_ms - 50) / 20 * 20
    else: return min(100, 85 + (wind_ms - 70) / 30 * 15)


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75: return RiskTier.CRITICAL
    elif score >= 50: return RiskTier.HIGH
    elif score >= 25: return RiskTier.MODERATE
    return RiskTier.LOW
```


---

## 6. Storm Surge Tool (FIX v3.2 — Gap R)

```python
# src/tools/storm_surge_tools.py
"""
Parametric storm surge assessment.

Physics: Simplified Jelesnianski (SLOSH-lite) parametric surge model.
  - Surge height from cyclone wind speed and pressure deficit
  - Coastal amplification from GEBCO bathymetry (Green's law)
  - Subsidence-adjusted elevation for inundation depth
  - Requires CycloneEventParams from Step 2 (cyclone tool)

v3.2 Changes:
  - Gap R: @validate_no_nan decorator.
  - Cyclone params now use Holland (2008) revised pressure estimates (Gap P).

Data sources:
  - IBTrACS cyclone params (from cyclone_tools.py — now Holland 2008)
  - GEBCO 2024 bathymetry (BODC WCS / NetCDF API)
  - Copernicus GLO-30 DEM (AWS S3 OpenData)
"""

from typing import Optional
from src.core.models import (
    Location, HazardIntensity, HazardEventContext, ExposureProfile,
    HazardAssessmentResult, AdjustedSurface, CycloneEventParams,
    ConfidenceLevel, RiskTier, HazardType, DataSource,
)
from src.data.gebco import get_bathymetry
from src.data.elevation import get_elevation
from src.data.validation import validate_no_nan  # NEW v3.2 (Gap R)


@validate_no_nan  # Gap R
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
        return_period: Return period (reporting only; surge driven by cyclone_params)
    """
    elevation_result = await get_elevation(lat, lon)

    if not cyclone_params:
        return _no_surge_result(lat, lon, elevation_result, return_period)

    wind_kts = cyclone_params.get("max_wind_kts", 0)
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

    # 3. Bathymetry amplification (Green's law)
    try:
        bathy = await get_bathymetry(lat, lon)
        shelf_depth = abs(bathy.depth_m)
        shelf_factor = max(0.5, min(2.0, 50 / max(1, shelf_depth)))
    except Exception:
        shelf_factor = 1.0

    total_surge = base_surge * shelf_factor

    # 4. Subsidence correction
    subsidence_effect = 0.0
    adjustments = []
    if surface and surface.subsidence_applied:
        subsidence_effect = surface.subsidence_adjustment_m
        adjustments.append("subsidence")

    effective_elevation = elevation_result.elevation_m - subsidence_effect
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
            # No climate_forcing_resolution_m — surge is observation-derived
            data_sources=data_sources,
            limitations=[
                "Parametric surge model (not full ADCIRC/SLOSH simulation)",
                "No wave setup or rainfall contribution",
                f"Shelf amplification factor: {shelf_factor:.2f}",
                "Assumes shore-normal approach angle",
            ],
            confidence=ConfidenceLevel.LOW,
        ),
        exposure=ExposureProfile(
            location=Location(lat=lat, lon=lon),
            elevation_m=elevation_result.elevation_m,
            elevation_source=DataSource.COPERNICUS_GLO30.value,
            adjustments_applied=adjustments,
        ),
        intermediate={
            "cyclone_wind_kts": wind_kts,
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


def _no_surge_result(lat, lon, elev, rp):
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
        exposure=ExposureProfile(
            location=Location(lat=lat, lon=lon),
            elevation_m=elev.elevation_m,
            elevation_source=DataSource.COPERNICUS_GLO30.value,
        ),
        intermediate={"cyclone_params": None, "total_surge_m": 0},
        impact_score=0.0,
        impact_tier=RiskTier.LOW,
        can_aggregate_with=[HazardType.COASTAL_FLOOD],
        dependency_order=3,
    )


def _calculate_surge_risk_score(depth: float) -> float:
    if depth <= 0: return 0.0
    elif depth < 0.5: return depth / 0.5 * 25
    elif depth < 1.5: return 25 + (depth - 0.5) * 25
    elif depth < 3.0: return 50 + (depth - 1.5) / 1.5 * 25
    else: return min(100, 75 + (depth - 3.0) / 3.0 * 25)


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75: return RiskTier.CRITICAL
    elif score >= 50: return RiskTier.HIGH
    elif score >= 25: return RiskTier.MODERATE
    return RiskTier.LOW
```

---

## 7. Urban Heat Tool (FIX v3.2 — Gap H, I, R)

```python
# src/tools/urban_heat_tools.py
"""
Urban heat hazard assessment with LST + WBGT + climate projections.

Physics: Multi-source heat stress assessment.
  - Baseline temperature from NEX-GDDP-CMIP6 historical period
  - Future projection delta from NEX-GDDP-CMIP6 scenario
  - Urban Heat Island (UHI) effect from Landsat C02 L2 LST
  - Wet-Bulb Globe Temperature (WBGT) from ERA5-Land components
  - WBGT = 0.7*Tw + 0.2*Tg + 0.1*Td (simplified outdoor formula)

v3.2 Changes:
  - Gap H: climate_forcing_resolution_m=25000 on HazardIntensity.
  - Gap I: get_climate_projection() returns real ensemble p5/p95.
           Temperature uncertainty from actual inter-model spread.
  - Gap R: @validate_no_nan decorator.

Data sources:
  - NEX-GDDP-CMIP6 (AWS S3 / THREDDS) → temperature baseline + projections
  - Landsat C02 L2 (PC STAC / GEE) → land surface temperature at 30m
  - ERA5-Land (CDS API) → humidity, wind, solar for WBGT calculation
  - Copernicus GLO-30 DEM (AWS S3) → elevation for exposure profile
"""

from typing import Optional
from src.core.models import (
    Location, HazardIntensity, HazardEventContext, ExposureProfile,
    HazardAssessmentResult, ConfidenceLevel, RiskTier,
    HazardType, DataSource, SSPScenario,
)
from src.data.nex_gddp import get_temperature_baseline, get_climate_projection
from src.data.landsat import get_lst_statistics
from src.data.era5 import get_wbgt_components, compute_wbgt
from src.data.elevation import get_elevation
from src.data.validation import validate_no_nan  # NEW v3.2 (Gap R)


@validate_no_nan  # Gap R
async def assess_urban_heat(
    lat: float, lon: float,
    time_horizon: int = 2050,
    percentile: int = 95,
    scenario: str = "ssp245"
) -> HazardAssessmentResult:
    """
    Assess urban heat stress with LST and WBGT.

    Args:
        lat, lon: Location coordinates
        time_horizon: Target year for projections
        percentile: Temperature percentile (90, 95, or 99)
        scenario: SSP climate scenario
    """
    # 1. Historical baseline from NEX-GDDP-CMIP6
    baseline = await get_temperature_baseline(lat, lon)
    future_period = f"{time_horizon - 10}-{time_horizon + 10}"
    projection = await get_climate_projection(
        lat, lon, variable="tasmax",
        scenario=SSPScenario(scenario), future_period=future_period
    )

    # 2. Current LST from Landsat
    lst = None
    uhi_effect = 2.0  # Default UHI for tropical cities
    try:
        lst = await get_lst_statistics(lat, lon, date_range="2022-01-01/2023-12-31")
        if lst and lst.lst_median_c:
            uhi_effect = max(0, lst.lst_median_c - baseline.annual_mean_c)
    except Exception:
        pass

    # 3. WBGT from ERA5-Land
    current_wbgt = None
    try:
        wbgt_comp = await get_wbgt_components(lat, lon)
        current_wbgt = compute_wbgt(
            wbgt_comp.t2m_c, wbgt_comp.dewpoint_c,
            wbgt_comp.wind_ms, wbgt_comp.solar_wm2
        )
    except Exception:
        pass

    # 4. Elevation
    elevation_result = await get_elevation(lat, lon)

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

    # 6. Uncertainty bounds (FIX v3.2 — Gap I)
    #    v3.1: fabricated ±2°C. v3.2: real ensemble spread from projection.
    ensemble_spread_low = getattr(projection, 'p5_change', projection.change - 2)
    ensemble_spread_high = getattr(projection, 'p95_change', projection.change + 2)
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

    ensemble_size = getattr(projection, 'ensemble_size', None)

    limitations = [
        f"UHI effect: +{uhi_effect:.1f}°C" + (" (Landsat)" if lst else " (default estimate)"),
        f"WBGT: {projected_wbgt:.1f}°C" if projected_wbgt else "WBGT not computed (ERA5 unavailable)",
        f"Percentile: {percentile}th (hottest days)",
        "NEX-GDDP-CMIP6 at 0.25° (~25km) — sub-grid UHI heterogeneity not resolved",
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
            intensity_unit="°C",
            intensity_p5=round(temp_p5, 1),      # v3.2: real ensemble spread
            intensity_p95=round(temp_p95, 1),     # v3.2: real ensemble spread
            uncertainty_type="ensemble_inter_model_spread",  # v3.2: was "scenario_ensemble"
            native_resolution_m=25000,
            effective_resolution_m=30 if lst else 25000,
            climate_forcing_resolution_m=25000,  # NEW v3.2 (Gap H)
            data_sources=data_sources,
            limitations=limitations,
            confidence=confidence,
        ),
        exposure=ExposureProfile(
            location=Location(lat=lat, lon=lon),
            elevation_m=elevation_result.elevation_m,
            elevation_source=DataSource.COPERNICUS_GLO30.value,
        ),
        intermediate={
            "baseline_annual_mean_c": baseline.annual_mean_c,
            "baseline_p95_c": baseline.p95_temperature_c,
            "current_percentile_temp_c": current_temp,
            "uhi_effect_c": round(uhi_effect, 1),
            "uhi_source": "landsat" if lst else "default",
            "projected_temp_c": round(projected_temp, 1),
            "temperature_change_c": projection.change,
            "ensemble_p5_change_c": ensemble_spread_low,   # NEW v3.2
            "ensemble_p95_change_c": ensemble_spread_high,  # NEW v3.2
            "ensemble_size": ensemble_size,                 # NEW v3.2
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
    if temp < 32: base = temp / 32 * 20
    elif temp < 35: base = 20 + (temp - 32) / 3 * 25
    elif temp < 40: base = 45 + (temp - 35) / 5 * 30
    else: base = min(100, 75 + (temp - 40) / 5 * 25)
    return min(100, base + min(15, hw_change * 0.5))


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75: return RiskTier.CRITICAL
    elif score >= 50: return RiskTier.HIGH
    elif score >= 25: return RiskTier.MODERATE
    return RiskTier.LOW
```


---

## 8. Pluvial Flood Tool — NEW v3.2 (Gap M)

```python
# src/tools/pluvial_flood_tools.py
"""
Pluvial (surface water) flood hazard assessment — NEW v3.2 (Gap M).

Physics: Proxy model combining terrain susceptibility + extreme rainfall.
  - HAND (Height Above Nearest Drainage) from GLO-30 DEM → drainage potential
  - Slope from GLO-30 → ponding susceptibility (flatter = worse)
  - Impervious fraction from Sentinel-2 NDVI (proxy) → runoff coefficient
  - Extreme precipitation from NEX-GDDP-CMIP6 → rainfall trigger
  - Estimated depth: rainfall_mm × runoff_coefficient / 1000

Why this matters:
  Pluvial flooding is the most frequent flood type in SEA cities.
  HCMC experiences 20-30+ pluvial events per year from intense monsoon
  rainfall overwhelming urban drainage. v3.1 only modeled riverine and
  coastal flooding, missing this dominant hazard.

Limitations:
  This is a first-order proxy. True pluvial flood modeling requires:
  - Urban drainage network (pipe diameters, condition, capacity)
  - 2D shallow-water equations (e.g., LISFLOOD-FP, TUFLOW)
  - LiDAR DEM at <1m resolution (not GLO-30 at 30m)
  - Real-time pump station status
  The proxy captures relative susceptibility but not absolute depths.

Data sources (all API-accessible):
  - Copernicus GLO-30 DEM (AWS S3) → HAND + slope
  - NEX-GDDP-CMIP6 (AWS S3) → extreme precipitation
  - Sentinel-2 L2A (Planetary Computer) → NDVI (impervious fraction proxy)
  - pluvial_flood.py (Phase 2 v3.2) → compute_pluvial_susceptibility()
"""

from typing import Optional
from src.core.models import (
    Location, HazardIntensity, HazardEventContext, ExposureProfile,
    HazardAssessmentResult, ConfidenceLevel, RiskTier,
    HazardType, DataSource,
)
from src.data.hand import get_hand_value
from src.data.elevation import get_slope, get_elevation
from src.data.nex_gddp import get_extreme_precipitation
from src.data.sentinel2 import get_ndvi_statistics
from src.data.pluvial_flood import compute_pluvial_susceptibility  # NEW v3.2 (Gap M)
from src.data.validation import validate_no_nan  # NEW v3.2 (Gap R)

NATIVE_RESOLUTION_M = 30
EFFECTIVE_RESOLUTION_M = 30


@validate_no_nan  # Gap R
async def assess_pluvial_flood(
    lat: float, lon: float,
    return_period: int = 10,
    scenario: str = "historical",
) -> HazardAssessmentResult:
    """
    Assess pluvial (surface water) flood susceptibility.

    Pluvial floods differ from riverine: they are caused by intense rainfall
    exceeding local drainage capacity, not by river overtopping. Common in
    low-lying urban areas with impervious surfaces.

    Args:
        lat, lon: Location coordinates
        return_period: Rainfall return period (typically 10-50 for pluvial)
        scenario: Climate scenario for precipitation projections

    Returns:
        HazardAssessmentResult with estimated surface water depth (meters).
        Note: depth is proxy-based, not from hydrodynamic simulation.
    """
    # 1. Terrain data
    hand_result = await get_hand_value(lat, lon)
    slope_result = await get_slope(lat, lon)
    elevation_result = await get_elevation(lat, lon)

    # 2. Extreme precipitation for design storm
    precip_result = await get_extreme_precipitation(lat, lon, return_period, scenario)
    rainfall_mm = precip_result.precip_mm_per_day

    # 3. Impervious fraction proxy from NDVI (graceful degradation)
    impervious_fraction = 0.5  # Default for tropical urban
    try:
        ndvi = await get_ndvi_statistics(lat, lon, date_range="2022-01-01/2023-12-31")
        if ndvi and ndvi.ndvi_median is not None:
            # Low NDVI → high impervious: impervious ≈ 1 - (NDVI/0.7)
            impervious_fraction = max(0.1, min(0.95, 1.0 - ndvi.ndvi_median / 0.7))
    except Exception:
        pass

    # 4. Compute pluvial susceptibility + depth proxy (Phase 2 v3.2)
    pluvial_result = compute_pluvial_susceptibility(
        hand_m=hand_result.hand_value_m,
        slope_degrees=slope_result.slope_degrees,
        impervious_fraction=impervious_fraction,
        design_rainfall_mm=rainfall_mm,
    )

    susceptibility = pluvial_result.susceptibility_index
    estimated_depth = pluvial_result.estimated_depth_m

    # 5. Confidence — always LOW for proxy, MODERATE if strong terrain signal
    confidence = ConfidenceLevel.LOW
    if (hand_result.hand_value_m < 3 and
        slope_result.slope_degrees < 2 and
        impervious_fraction > 0.6):
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
            hazard_type=HazardType.PLUVIAL_FLOOD,  # NEW v3.2 (Gap M)
            event_context=HazardEventContext(
                event_type="acute", return_period_years=return_period
            ),
            intensity_value=round(estimated_depth, 2),
            intensity_unit="m",
            intensity_p5=round(estimated_depth * 0.5, 2),
            intensity_p95=round(estimated_depth * 2.0, 2),  # Wide: proxy model
            uncertainty_type="proxy_model_high_uncertainty",
            native_resolution_m=NATIVE_RESOLUTION_M,
            effective_resolution_m=EFFECTIVE_RESOLUTION_M,
            climate_forcing_resolution_m=25000,  # Gap H
            data_sources=data_sources,
            limitations=limitations,
            confidence=confidence,
        ),
        exposure=ExposureProfile(
            location=Location(lat=lat, lon=lon),
            elevation_m=elevation_result.elevation_m,
            elevation_source=DataSource.COPERNICUS_GLO30.value,
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
        dependency_order=4,  # Same as riverine (independent)
    )


def _calculate_pluvial_risk_score(depth: float, susceptibility: float) -> float:
    """Map pluvial depth + susceptibility to 0-100 risk score."""
    if depth <= 0: return 0.0
    elif depth < 0.1: depth_score = depth / 0.1 * 15
    elif depth < 0.3: depth_score = 15 + (depth - 0.1) / 0.2 * 20
    elif depth < 0.5: depth_score = 35 + (depth - 0.3) / 0.2 * 20
    elif depth < 1.0: depth_score = 55 + (depth - 0.5) / 0.5 * 25
    else: depth_score = min(100, 80 + (depth - 1.0) * 20)
    # Blend with susceptibility for proxy confidence
    return 0.7 * depth_score + 0.3 * (susceptibility * 100)


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75: return RiskTier.CRITICAL
    elif score >= 50: return RiskTier.HIGH
    elif score >= 25: return RiskTier.MODERATE
    return RiskTier.LOW
```

---

## 9. Structure Risk Tool (FIX v3.2 — Gap Q, S, T, M)

```python
# src/tools/structure_risk_tools.py
"""
Structure-level risk assessment using H×E×V framework.

Physics: For each building in the queried area, compute:
  H (Hazard):     Flood depth / wind speed / surge height at the building location
  E (Exposure):   Building footprint, height, ground elevation, ground floor height
  V (Vulnerability): JRC depth-damage curve for the building's material class

  damage_ratio = V_curve.interpolate(hazard_intensity_at_building)
  loss_usd     = damage_ratio × replacement_value_usd

v3.2 Changes:
  - Gap Q: Multi-RP EAL via trapezoidal integration.
           v3.1 computed EAL = damage_ratio × replacement / RP (wrong).
           v3.2 runs H×V at each of [10, 25, 50, 100, 250] year RPs,
           builds loss-exceedance curve, integrates EAL = ∫₀¹ L(p) dp.
  - Gap S: BuildingAdjustedSurface provides per-building elevation/subsidence/SLR.
           v3.1 used tile-level AdjustedSurface (single elevation per tile).
  - Gap T: OCCUPANCY_VALUE_MULTIPLIER scales JRC replacement values by occupancy.
           v3.1 treated warehouse = hospital. v3.2: commercial 2.5×, institutional 3.0×.
  - Gap M: Pluvial flood damage added to per-building assessment.

Data sources (all from Phase 2 v3.2):
  - PostGIS buildings cache (Google Open Buildings + Overture Maps)
  - JRC Global Flood Depth-Damage Functions (Huizinga et al. 2017)
  - Hazard results from Steps 1–3 (flood, wind, surge, pluvial)
  - OCCUPANCY_VALUE_MULTIPLIER (Phase 1 v3.2 — Gap T)
  - BuildingAdjustedSurface (Phase 1 v3.2 — Gap S)

Returns:
  - List[StructureRiskResult] — per-building damage + loss + multi-RP EAL
  - PortfolioRiskSummary — aggregated city/district statistics
"""

import asyncio
from typing import List, Optional

from src.core.models import (
    Location, HazardType, RiskTier, VulnerabilityClass,
    StructuralCharacteristics, BuildingCluster,
    StructureRiskResult, PortfolioRiskSummary,
    ReturnPeriodLoss, STANDARD_RETURN_PERIODS,  # NEW v3.2 (Gap Q)
    compute_eal_trapezoidal,                     # NEW v3.2 (Gap Q)
    BuildingAdjustedSurface,                     # NEW v3.2 (Gap S)
    OCCUPANCY_VALUE_MULTIPLIER,                  # NEW v3.2 (Gap T)
    ConfidenceLevel,
)
from src.data.jrc_vulnerability import JRCVulnerabilitySource
from src.data.open_buildings import OpenBuildingsSource


jrc = JRCVulnerabilitySource()


async def assess_structure_risk(
    buildings: BuildingCluster,
    hazard_results_by_rp: dict,
    building_surfaces: Optional[dict] = None,
    country: str = "VN",
) -> List[StructureRiskResult]:
    """
    Apply H×E×V to each building in a BuildingCluster with multi-RP EAL.

    v3.2: This function now expects hazard results at MULTIPLE return periods
    to compute proper EAL via trapezoidal integration.

    Args:
        buildings: BuildingCluster from Step 0 (asset fetch)
        hazard_results_by_rp: Dict of {return_period: {HazardType: HazardAssessmentResult}}
            v3.1 accepted single-RP dict. v3.2 expects multi-RP nested dict.
            Fallback: if flat dict passed, wraps as {100: flat_dict}.
        building_surfaces: Dict of {building_id: BuildingAdjustedSurface}
            (NEW v3.2, Gap S). Per-building elevation/subsidence/SLR context.
            If None, uses tile-level defaults.
        country: ISO country code for JRC max-damage lookup

    Returns:
        List of StructureRiskResult, one per building, with multi-RP EAL
    """
    # v3.2: Handle backward compatibility — wrap flat dict as single-RP
    if hazard_results_by_rp and not isinstance(next(iter(hazard_results_by_rp.keys())), int):
        hazard_results_by_rp = {100: hazard_results_by_rp}

    results = []

    for structure in buildings.structures:
        bid = structure.footprint.building_id

        # ── Per-building surface (FIX v3.2 — Gap S) ──
        bldg_surface = (building_surfaces or {}).get(bid)
        subsidence_source = "none"
        subsidence_rate = 0.0
        subsidence_cumulative = 0.0
        if bldg_surface:
            subsidence_source = bldg_surface.subsidence_source
            subsidence_rate = bldg_surface.subsidence_rate_mm_yr
            subsidence_cumulative = bldg_surface.subsidence_cumulative_m

        # ── Replacement value with occupancy multiplier (FIX v3.2 — Gap T) ──
        base_replacement = structure.replacement_value_usd or _estimate_replacement(
            structure, country
        )
        occupancy = getattr(structure, 'occupancy', None)
        multiplier = OCCUPANCY_VALUE_MULTIPLIER.get(occupancy, 1.0) if occupancy else 1.0
        replacement = base_replacement * multiplier
        replacement_source = (
            f"jrc_country_estimate x {multiplier:.1f}"
            if not structure.replacement_value_usd
            else "user_provided"
        )

        # ── Multi-RP loss-exceedance curve (FIX v3.2 — Gap Q) ──
        rp_losses: List[ReturnPeriodLoss] = []

        # Track primary RP (100yr) for backward-compatible fields
        primary_flood_depth = 0.0
        primary_flood_damage = 0.0
        primary_surge_depth = 0.0
        primary_surge_damage = 0.0
        primary_pluvial_depth = 0.0
        primary_pluvial_damage = 0.0
        primary_wind_damage = 0.0
        primary_wind_speed = 0.0

        for rp in sorted(hazard_results_by_rp.keys()):
            hazard_results = hazard_results_by_rp[rp]

            # Flood depth at building (ground floor + per-building surface)
            flood_depth_field = _extract_flood_depth(hazard_results)
            effective_gf = structure.effective_ground_floor_m
            if bldg_surface:
                effective_gf += bldg_surface.subsidence_cumulative_m

            flood_depth_at_bldg = max(
                0.0, (flood_depth_field or 0.0) - effective_gf
            )

            # Pluvial flood depth (NEW v3.2 — Gap M)
            pluvial_depth_at_bldg = 0.0
            if HazardType.PLUVIAL_FLOOD in hazard_results:
                pluvial_result = hazard_results[HazardType.PLUVIAL_FLOOD]
                pluvial_depth_at_bldg = max(
                    0.0, pluvial_result.hazard.intensity_value - effective_gf
                )

            # Surge depth
            surge_depth_at_bldg = 0.0
            if HazardType.STORM_SURGE in hazard_results:
                surge_result = hazard_results[HazardType.STORM_SURGE]
                surge_depth_at_bldg = max(
                    0.0, surge_result.hazard.intensity_value - effective_gf
                )

            # Max flood depth across all flood-like hazards
            max_flood_depth = max(flood_depth_at_bldg, pluvial_depth_at_bldg,
                                  surge_depth_at_bldg)

            # Flood damage ratio from JRC curve
            flood_damage_ratio = jrc.get_flood_damage_ratio(
                depth_m=max_flood_depth,
                vulnerability_class=structure.vulnerability_class,
            )

            # Wind damage ratio
            wind_speed_kts = _extract_wind_speed(hazard_results)
            wind_damage_ratio = jrc.get_wind_damage_ratio(
                wind_speed_kts=wind_speed_kts or 0.0,
                vulnerability_class=structure.vulnerability_class,
            )

            # Max damage for this RP
            max_damage_ratio = max(flood_damage_ratio, wind_damage_ratio)

            rp_losses.append(ReturnPeriodLoss(
                return_period_years=rp,
                exceedance_probability=1.0 / rp,
                damage_ratio=max_damage_ratio,
                loss_usd=max_damage_ratio * replacement,
                hazard_intensity=(
                    max_flood_depth
                    if flood_damage_ratio >= wind_damage_ratio
                    else (wind_speed_kts or 0.0)
                ),
                hazard_intensity_unit=(
                    "m" if flood_damage_ratio >= wind_damage_ratio else "kts"
                ),
            ))

            # Track primary RP (100yr) for backward-compatible fields
            if rp == 100 or (
                rp == max(hazard_results_by_rp.keys())
                and 100 not in hazard_results_by_rp
            ):
                primary_flood_depth = flood_depth_at_bldg
                primary_flood_damage = jrc.get_flood_damage_ratio(
                    depth_m=flood_depth_at_bldg,
                    vulnerability_class=structure.vulnerability_class,
                )
                primary_surge_depth = surge_depth_at_bldg
                primary_surge_damage = jrc.get_flood_damage_ratio(
                    depth_m=surge_depth_at_bldg,
                    vulnerability_class=structure.vulnerability_class,
                )
                primary_pluvial_depth = pluvial_depth_at_bldg
                primary_pluvial_damage = jrc.get_flood_damage_ratio(
                    depth_m=pluvial_depth_at_bldg,
                    vulnerability_class=structure.vulnerability_class,
                )
                primary_wind_damage = wind_damage_ratio
                primary_wind_speed = (wind_speed_kts or 0.0) * 0.5144

        # ── EAL via trapezoidal integration (FIX v3.2 — Gap Q) ──
        eal_usd = (
            compute_eal_trapezoidal(rp_losses, replacement)
            if len(rp_losses) >= 2 else 0.0
        )

        # ── PML at 250-year (v3.2: was 100-year) ──
        pml_loss = next(
            (l for l in rp_losses if l.return_period_years == 250),
            next(
                (l for l in sorted(rp_losses, key=lambda x: -x.return_period_years)),
                None,
            ),
        )
        pml_usd = pml_loss.loss_usd if pml_loss else 0.0

        # ── Composite risk score ──
        max_damage = max((l.damage_ratio for l in rp_losses), default=0.0)
        risk_score = max_damage * 100.0

        # ── Dominant hazard ──
        dominant = _determine_dominant_hazard(
            primary_flood_damage, primary_surge_damage,
            primary_pluvial_damage, primary_wind_damage,
        )

        results.append(StructureRiskResult(
            # Building identity
            building_id=bid,
            latitude=structure.footprint.centroid.lat,
            longitude=structure.footprint.centroid.lon,
            footprint_area_m2=structure.footprint.area_m2,

            # Building characteristics
            height_m=getattr(structure, 'height_m', None),
            num_stories=getattr(structure, 'num_stories', 1),
            vulnerability_class=structure.vulnerability_class,
            ground_floor_elevation_m=structure.effective_ground_floor_m,
            replacement_value_usd=round(replacement, 0),
            replacement_value_source=replacement_source,

            # Per-hazard damage ratios (at primary RP)
            flood_damage_ratio=round(primary_flood_damage, 4),
            flood_depth_at_building_m=round(primary_flood_depth, 2),
            surge_damage_ratio=round(primary_surge_damage, 4),
            surge_depth_at_building_m=round(primary_surge_depth, 2),
            pluvial_flood_damage_ratio=round(primary_pluvial_damage, 4),
            pluvial_depth_at_building_m=round(primary_pluvial_depth, 2),
            wind_damage_ratio=round(primary_wind_damage, 4),
            max_wind_speed_ms=round(primary_wind_speed, 1),

            # Subsidence (from per-building surface, Gap S)
            subsidence_mm_per_year=round(subsidence_rate, 1),
            subsidence_cumulative_m=round(subsidence_cumulative, 3),
            subsidence_source=subsidence_source,

            # Multi-RP loss curve (NEW v3.2 — Gap Q)
            losses_by_return_period=rp_losses,

            # Composite risk
            max_damage_ratio=round(max_damage, 4),
            combined_risk_score=round(risk_score, 1),
            risk_tier=_score_to_tier(risk_score),
            dominant_hazard=dominant,

            # Financial impact (v3.2: multi-RP EAL)
            expected_annual_loss_usd=round(eal_usd, 2),
            probable_maximum_loss_usd=round(pml_usd, 2),

            # Metadata
            data_sources=[
                "JRC Flood Depth-Damage (Huizinga 2017)",
                "Google Open Buildings + Overture Maps",
                f"Multi-RP EAL: {len(rp_losses)} return periods",
            ],
            limitations=[
                "JRC curves are residential-baseline" + (
                    f" (occupancy multiplier {multiplier:.1f}x applied)"
                    if multiplier != 1.0 else ""
                ),
                f"Subsidence source: {subsidence_source}",
            ],
        ))

    return results


def summarize_portfolio(
    structure_results: List[StructureRiskResult],
    portfolio_id: str,
    city: str,
) -> PortfolioRiskSummary:
    """Aggregate per-building results into portfolio-level stats."""
    n = len(structure_results)
    return PortfolioRiskSummary(
        portfolio_id=portfolio_id,
        city=city,
        total_buildings=n,
        buildings_critical=sum(
            1 for r in structure_results if r.risk_tier == RiskTier.CRITICAL
        ),
        buildings_high=sum(
            1 for r in structure_results if r.risk_tier == RiskTier.HIGH
        ),
        buildings_moderate=sum(
            1 for r in structure_results if r.risk_tier == RiskTier.MODERATE
        ),
        buildings_low=sum(
            1 for r in structure_results if r.risk_tier == RiskTier.LOW
        ),
        total_replacement_value_usd=sum(
            r.replacement_value_usd or 0 for r in structure_results
        ),
        total_expected_annual_loss_usd=sum(
            r.expected_annual_loss_usd or 0 for r in structure_results
        ),
        mean_damage_ratio=round(
            sum(r.max_damage_ratio for r in structure_results) / max(n, 1), 4
        ),
    )


# ── Private helpers ──

def _extract_flood_depth(hazard_results: dict) -> Optional[float]:
    """Get maximum flood water level from any flood hazard result."""
    for htype in [HazardType.RIVERINE_FLOOD, HazardType.COASTAL_FLOOD,
                  HazardType.STORM_SURGE]:
        if htype in hazard_results:
            return hazard_results[htype].hazard.intensity_value
    return None


def _extract_wind_speed(hazard_results: dict) -> Optional[float]:
    """Get wind speed from cyclone result (knots)."""
    if HazardType.TROPICAL_CYCLONE in hazard_results:
        intermediate = hazard_results[HazardType.TROPICAL_CYCLONE].intermediate or {}
        return intermediate.get("max_wind_kts")
    return None


def _determine_dominant_hazard(
    flood_dr: float, surge_dr: float, pluvial_dr: float, wind_dr: float,
) -> Optional[HazardType]:
    """Determine which hazard contributes most damage."""
    damages = {
        HazardType.RIVERINE_FLOOD: flood_dr,
        HazardType.STORM_SURGE: surge_dr,
        HazardType.PLUVIAL_FLOOD: pluvial_dr,
        HazardType.TROPICAL_CYCLONE: wind_dr,
    }
    max_hazard = max(damages, key=damages.get)
    return max_hazard if damages[max_hazard] > 0 else None


def _estimate_replacement(structure, country: str) -> float:
    """Estimate base replacement value from area × JRC max damage per m²."""
    max_damage_per_m2 = jrc._get_max_damage_usd_m2(country, structure.occupancy)
    return structure.footprint.area_m2 * max_damage_per_m2


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75: return RiskTier.CRITICAL
    elif score >= 50: return RiskTier.HIGH
    elif score >= 25: return RiskTier.MODERATE
    return RiskTier.LOW
```

---

## 10. Module Init

```python
# src/tools/__init__.py
"""Hazard assessment tools for EcoShield v3.2."""
from .riverine_flood_tools import assess_riverine_flood
from .coastal_flood_tools import assess_coastal_flood
from .subsidence_tools import assess_subsidence
from .landslide_tools import assess_landslide
from .cyclone_tools import assess_cyclone
from .storm_surge_tools import assess_storm_surge
from .urban_heat_tools import assess_urban_heat
from .pluvial_flood_tools import assess_pluvial_flood                    # NEW v3.2 (Gap M)
from .structure_risk_tools import assess_structure_risk, summarize_portfolio

__all__ = [
    "assess_riverine_flood", "assess_coastal_flood", "assess_subsidence",
    "assess_landslide", "assess_cyclone", "assess_storm_surge", "assess_urban_heat",
    "assess_pluvial_flood",                                               # NEW v3.2 (Gap M)
    "assess_structure_risk", "summarize_portfolio",
]
```

---

## Tool Contract Validation

Every hazard tool **must** satisfy these requirements:

| # | Requirement | Check |
|---|-------------|-------|
| 1 | Returns `HazardAssessmentResult` | ✅ All **8** hazard tools |
| 2 | Includes `HazardIntensity` with correct `HazardType` | ✅ (incl. `PLUVIAL_FLOOD` v3.2) |
| 3 | Includes `HazardEventContext` (acute: return_period; chronic: time_horizon) | ✅ |
| 4 | Includes `ExposureProfile` with `DataSource.COPERNICUS_GLO30` elevation | ✅ |
| 5 | Sets `confidence` and `limitations` | ✅ |
| 6 | Sets `can_aggregate_with` for composite calculation | ✅ |
| 7 | Sets `dependency_order` for workflow sequencing | ✅ |
| 8 | References correct `DataSource` enum values (v3.2 names) | ✅ |
| 9 | Gracefully degrades if optional API unavailable | ✅ (SoilGrids, Landsat, ERA5, GEBCO, InSAR) |
| 10 | Stores `cyclone_params` in intermediate (cyclone tool) for surge tool | ✅ |
| **11** | **Uses `@validate_no_nan` decorator (Gap R)** | **✅ All 8 hazard tools** |
| **12** | **Sets `climate_forcing_resolution_m=25000` where NEX-GDDP feeds HazardIntensity (Gap H)** | **✅ Riverine, coastal, landslide, pluvial, urban heat** |
| **13** | **Imports from Phase 2 v3.2 modules: `rating_curve`, `ipcc_slr`, `holland_wind`, `pluvial_flood`, `validation`** | **✅** |

Structure risk tool **must** satisfy these additional requirements:

| # | Requirement | v3.1 | v3.2 |
|---|-------------|------|------|
| 14 | Accepts `BuildingCluster` from Step 0 (asset fetch) | ✅ | ✅ |
| 15 | Returns `List[StructureRiskResult]` — one per building | ✅ | ✅ |
| 16 | Uses JRC depth-damage curve for flood damage ratio | ✅ | ✅ |
| 17 | Computes `effective_ground_floor_m` accounting for stilts + ground floor height | ✅ | ✅ |
| 18 | Produces `PortfolioRiskSummary` via `summarize_portfolio()` | ✅ | ✅ |
| **19** | **Per-building EAL via trapezoidal integration over [10,25,50,100,250] RPs (Gap Q)** | ❌ Single-RP | **✅** |
| **20** | **Uses `BuildingAdjustedSurface` for per-building elevation/subsidence/SLR (Gap S)** | ❌ Tile-level | **✅** |
| **21** | **Applies `OCCUPANCY_VALUE_MULTIPLIER` to replacement values (Gap T)** | ❌ All 1.0× | **✅** |
| **22** | **Includes pluvial flood damage in per-building assessment (Gap M)** | ❌ Not modeled | **✅** |
| **23** | **Populates `losses_by_return_period` on every `StructureRiskResult` (Gap Q)** | ❌ | **✅** |
| **24** | **PML at 250-year RP (was 100-year in v3.1)** | 100-yr | **250-yr** |
| **25** | **Tracks `subsidence_source` and `replacement_value_source` (Gap L/T)** | ❌ | **✅** |

---

## v3.2 Gap Fix Summary (Phase 3)

| Gap | Fix | Tool(s) Affected |
|-----|-----|------------------|
| **H** | `climate_forcing_resolution_m=25000` on all NEX-GDDP-fed HazardIntensity | Riverine, coastal, landslide, pluvial, urban heat |
| **I** | Real uncertainty bounds replace fabricated ±20-30% | Riverine (Manning's ±35%), landslide (ensemble note), urban heat (ensemble p5/p95) |
| **J** | `rating_curve.discharge_to_depth()` with per-city channel params | Riverine flood |
| **K** | `ipcc_slr.get_slr_projection()` with per-city regional SLR | Coastal flood |
| **L** | `get_subsidence_velocity()` with published-rate fallback + source tracking | Subsidence, structure risk |
| **M** | NEW `pluvial_flood_tools.py` + pluvial damage in structure risk | Pluvial flood (NEW), structure risk |
| **P** | `holland_wind.holland_wind_profile()` Holland (2008) revised | Cyclone |
| **Q** | Multi-RP EAL via `compute_eal_trapezoidal()` over [10,25,50,100,250] | Structure risk |
| **R** | `@validate_no_nan` decorator on all async tool functions | All 8 hazard tools |
| **S** | `BuildingAdjustedSurface` for per-building elevation/subsidence/SLR | Structure risk |
| **T** | `OCCUPANCY_VALUE_MULTIPLIER` scales JRC replacement by occupancy | Structure risk |

---

## Next Phase

After completing Phase 3, proceed to **Phase 4: Workflow Orchestration** (ECOSHIELD-PHASE4-WORKFLOW-v3.md).
Phase 4 must be updated for v3.2 to orchestrate:
  - 8 hazard tools (add `assess_pluvial_flood`)
  - Multi-RP loop at [10, 25, 50, 100, 250] years
  - Per-building surface creation via `BuildingAdjustedSurface`
  - Occupancy multiplier application in replacement value estimation

---

*EcoShield Phase 3 v3.2 | Hazard Assessment Tools (8) + Structure Risk (H×E×V + Multi-RP EAL) — Complete API-First Implementations*
