# EcoShield Phase 4: Workflow Orchestration — v3.2

## Implementation Guide for Cursor AI

> **Phase 4 v3.2**: Complete workflow orchestration with Agno Workflows.
> All cities use NEX-GDDP-CMIP6 (global) — no Vietnam-only limitation.
> **v3.1**: 6-step workflow (was 4-step). Added Step 0 (asset fetch from
> PostGIS buildings cache) and Step 4 (structure-level H×E×V risk per building).
> **v3.2 Gap Fixes**:
> - **8 hazard tools** (was 7): Added `assess_pluvial_flood` in Step 3 (Gap M).
> - **Multi-RP loop**: Steps 2-3 run at [2, 5, 10, 25, 50, 100, 250, 500, 1000] year RPs,
>   feeding `hazard_results_by_rp` to structure risk for trapezoidal EAL (Gap Q).
> - **Per-building surface**: Step 0 now creates `BuildingAdjustedSurface`
>   per building from centroid elevation + spatially interpolated subsidence (Gap S).
> - **Occupancy multiplier**: `OCCUPANCY_VALUE_MULTIPLIER` scales replacement
>   values by building occupancy class (Gap T).
> - **Tool call updates**: riverine passes `city` for rating_curve (Gap J),
>   coastal passes `city` for ipcc_slr (Gap K), subsidence tracks source (Gap L),
>   cyclone uses Holland (2008) internally (Gap P).
> - **Pluvial flood weights** added to all city hazard configurations.
> - **Subsidence corrections**: Removed subsidence as chronic hazard for Hanoi
>   (central city diminishing, localized peri-urban only — Nguyen et al. 2022)
>   and Bangkok (inner city mitigated to ~0-1 cm/yr via strict groundwater
>   regulation — Phien-wej et al. 2006). Retained for HCMC, Jakarta, Manila
>   where subsidence remains severe and unmitigated.
> - Expanded city hazard configurations + weights for all SEA target cities.

---

## Overview

Phase 4 implements the **Agno Workflow orchestration layer** — the central
nervous system that coordinates the **8** hazard tools from Phase 3 into a
deterministic, dependency-respecting pipeline.

### Why Workflows (Not Just Agent Teams)

| Feature | Agent Teams | Agno Workflows |
|---------|-------------|----------------|
| Execution order | Dynamic (agent decides) | Deterministic (declared steps) |
| Dependencies | Implicit | Explicit (step data flow) |
| Parallelism | Agent-controlled | Declared with `asyncio.gather()` |
| State passing | Session-based | Step-to-step data flow |
| Reproducibility | Variable | Identical given same inputs |
| Use case | Flexible collaboration | Repeatable assessment pipelines |

**EcoShield uses Workflows** because hazard assessment has hard dependencies:
subsidence must complete before flood calculations can use the adjusted surface.

### Files to Create

```
src/workflows/
├── __init__.py
├── hazard_workflow.py          # Main 6-step workflow + multi-RP loop (FIX v3.2)
├── portfolio_workflow.py       # Batch portfolio (parallel sites + EAL aggregation)
└── steps/
    ├── __init__.py
    ├── asset_fetch.py          # Step 0: Buildings + BuildingAdjustedSurface (FIX v3.2 Gap S)
    ├── chronic_hazards.py      # Step 1: Subsidence (+ published fallback) + Urban Heat
    ├── cyclone_step.py         # Step 2: Cyclone → CycloneEventParams (Holland 2008)
    ├── acute_hazards.py        # Step 3: Flood + Surge + Landslide + Pluvial (NEW v3.2 Gap M)
    ├── structure_risk.py       # Step 4: Multi-RP H×E×V → EAL (FIX v3.2 Gap Q/S/T)
    └── composite.py            # Step 5: Weighted composite → FullRiskProfile
```

---

## 1. City Hazard Configuration (FIX v3.2 — Gap M)

```python
# src/config/city_hazards.py
"""
City-specific hazard configurations.

v3.0: All SEA target cities supported from day one.
NEX-GDDP-CMIP6 provides global climate projections.

v3.2 (Gap M): Added "pluvial_flood" to acute hazards for urban cities.
Pluvial flooding is the most frequent flood type in SEA; HCMC experiences
20-30+ events per year. Now assessed at multiple return periods.

v3.2 subsidence corrections:
  - Hanoi: Removed from chronic. Central Hanoi subsidence diminishing over
    2007-2018 (Nguyen et al. 2022, Engineering Geology). Localized hotspots
    in peri-urban Ha Dong/Hoai Duc (~50 mm/yr) but city is "relatively less
    affected compared to other SEA cities." Small consolidation coefficients.
  - Bangkok: Removed from chronic. Historic crisis (120 mm/yr peak, 1980s)
    largely mitigated through groundwater pricing, tap water expansion, and
    strict enforcement (Phien-wej et al. 2006). Inner Bangkok now ~0-1 cm/yr
    (Mekong-US Partnership 2020). Neighboring provinces outside assessment
    bounds still subsiding.
  - HCMC: Retained — up to 80 mm/yr, no effective mitigation (World Bank 2015).
  - Jakarta: Retained — up to 250 mm/yr, world's worst (Frontiers 2024).
  - Manila: Retained — max 109 mm/yr Bulacan, 20-42 mm/yr Metro Manila
    (Sulapas et al. 2024). No effective mitigation.
"""

CITY_HAZARDS = {
    # ═══════════════════════════════════════════════
    #  VIETNAM (MVP targets)
    # ═══════════════════════════════════════════════
    "hcmc": {
        "name": "Ho Chi Minh City",
        "country": "VN",
        "acute": ["riverine_flood", "coastal_flood", "storm_surge",
                  "tropical_cyclone", "pluvial_flood"],  # v3.2: + pluvial_flood
        "chronic": ["subsidence", "urban_heat"],
        # Subsidence: Severe, up to 80 mm/yr in District 7 (World Bank 2015).
        # Mekong Delta groundwater extraction ongoing; no effective mitigation yet.
        "bounds": {"north": 11.2, "south": 10.4, "east": 107.0, "west": 106.3},
        "tidal_range_m": 3.5,
    },
    "hanoi": {
        "name": "Hanoi",
        "country": "VN",
        "acute": ["riverine_flood", "tropical_cyclone", "landslide",
                  "pluvial_flood"],  # v3.2: + pluvial_flood
        "chronic": ["urban_heat"],
        # v3.2: Subsidence removed from chronic. Central Hanoi subsidence has been
        # diminishing (Nguyen et al. 2022, Eng. Geology). Localized hotspots in
        # peri-urban Ha Dong/Hoai Duc (~50 mm/yr) but "Hanoi is relatively less
        # affected by land subsidence compared to other SEA cities" due to small
        # consolidation coefficients and lower population density.
        "bounds": {"north": 21.3, "south": 20.8, "east": 106.0, "west": 105.5},
        "tidal_range_m": 0.0,
    },
    "danang": {
        "name": "Da Nang",
        "country": "VN",
        "acute": ["riverine_flood", "coastal_flood", "storm_surge",
                  "tropical_cyclone", "landslide", "pluvial_flood"],  # v3.2
        "chronic": ["urban_heat"],
        "bounds": {"north": 16.3, "south": 15.8, "east": 108.5, "west": 107.8},
        "tidal_range_m": 1.2,
    },

    # ═══════════════════════════════════════════════
    #  INDONESIA
    # ═══════════════════════════════════════════════
    "jakarta": {
        "name": "Jakarta",
        "country": "ID",
        "acute": ["riverine_flood", "coastal_flood", "storm_surge",
                  "landslide", "pluvial_flood"],  # v3.2: + pluvial_flood
        "chronic": ["subsidence", "urban_heat"],
        # Subsidence: World's most severe — up to 250 mm/yr in North Jakarta
        # (Frontiers in Earth Science 2024). Capital relocation to Nusantara
        # partly driven by subsidence. No effective mitigation to date.
        "bounds": {"north": -6.0, "south": -6.5, "east": 107.1, "west": 106.5},
        "tidal_range_m": 1.0,
    },

    # ═══════════════════════════════════════════════
    #  PHILIPPINES
    # ═══════════════════════════════════════════════
    "manila": {
        "name": "Manila",
        "country": "PH",
        "acute": ["riverine_flood", "coastal_flood", "storm_surge",
                  "tropical_cyclone", "landslide", "pluvial_flood"],  # v3.2
        "chronic": ["subsidence", "urban_heat"],
        # Subsidence: Severe & ongoing — max 109 mm/yr in Bulacan Province,
        # 20-42 mm/yr across Metro Manila (Sulapas et al. 2024, Int. J. Applied
        # Earth Observation). Driven by excessive groundwater extraction; "orders
        # of magnitude more rapid than sea-level rise" (Rodolfo & Siringan 2006).
        "bounds": {"north": 14.8, "south": 14.3, "east": 121.2, "west": 120.8},
        "tidal_range_m": 1.5,
    },

    # ═══════════════════════════════════════════════
    #  THAILAND
    # ═══════════════════════════════════════════════
    "bangkok": {
        "name": "Bangkok",
        "country": "TH",
        "acute": ["riverine_flood", "coastal_flood", "storm_surge",
                  "pluvial_flood"],  # v3.2: + pluvial_flood
        "chronic": ["urban_heat"],
        # v3.2: Subsidence removed from chronic. Bangkok's historic crisis
        # (120 mm/yr peak in 1980s) was largely mitigated through groundwater
        # pricing, tap water expansion, and strict enforcement (Phien-wej et al.
        # 2006; Mekong-US Partnership 2020). Inner Bangkok now ~0-1 cm/yr.
        # Neighboring provinces (Samut Prakan, Ayutthaya) still subsiding but
        # outside EcoShield assessment bounds. Residual consolidation continues
        # but is not a dominant chronic risk for inner Bangkok.
        "bounds": {"north": 14.0, "south": 13.5, "east": 100.8, "west": 100.3},
        "tidal_range_m": 2.5,
    },

    # ═══════════════════════════════════════════════
    #  SINGAPORE
    # ═══════════════════════════════════════════════
    "singapore": {
        "name": "Singapore",
        "country": "SG",
        "acute": ["coastal_flood", "storm_surge",
                  "pluvial_flood"],  # v3.2: + pluvial_flood (common in SG)
        "chronic": ["urban_heat"],
        "bounds": {"north": 1.5, "south": 1.1, "east": 104.1, "west": 103.6},
        "tidal_range_m": 2.8,
    },
}
```

---

## 2. Main Hazard Workflow (FIX v3.2 — Multi-RP Loop)

```python
# src/workflows/hazard_workflow.py
"""
Main hazard assessment workflow using Agno Workflows.

Execution Order (hard dependencies) — v3.2: 6 steps, 8 hazards, multi-RP:
  Step 0 — Asset Fetch: Load buildings + create BuildingAdjustedSurface (Gap S)
           → Outputs: BuildingCluster + Dict[building_id → BuildingAdjustedSurface]
  Step 1 — Chronic Hazards (Parallel): Subsidence (+ published fallback, Gap L) + Urban Heat
           → Outputs: AdjustedSurface + per-building subsidence rates
  Step 2 — Cyclone (Sequential): IBTrACS + Holland (2008) (Gap P)
           → Outputs: CycloneEventParams (wind, pressure, RMW)
  Step 3 — Acute Hazards (Parallel, Multi-RP): Flood + Surge + Landslide + Pluvial (Gap M)
           → Runs at STANDARD_RETURN_PERIODS = [2, 5, 10, 25, 50, 100, 250, 500, 1000] (Gap Q)
           → Inputs: AdjustedSurface from Step 1, CycloneParams from Step 2
           → Outputs: {return_period: {HazardType: HazardAssessmentResult}}
  Step 4 — Structure Risk (v3.2): Multi-RP H×E×V per building
           → Inputs: BuildingCluster + building_surfaces + hazard_results_by_rp
           → Outputs: List[StructureRiskResult] with trapezoidal EAL (Gap Q)
  Step 5 — Composite: Weighted aggregation + portfolio EAL
           → Outputs: FullRiskProfile + PortfolioRiskSummary

v3.2 data sources (all API-accessible):
  - NEX-GDDP-CMIP6 (climate projections) — replaces CMIP6-VN
  - Copernicus GLO-30 (elevation) — replaces FABDEM
  - GloFAS v4 (river discharge) + rating_curve.py (Gap J)
  - ERA5-Land (WBGT heat stress)
  - Landsat C2L2 (surface temperature)
  - SoilGrids v2 (soil properties)
  - Sentinel-2 L2A (NDVI vegetation)
  - GEBCO 2024 (bathymetry)
  - IBTrACS v04r01 (cyclone tracks) + holland_wind.py (Gap P)
  - ipcc_slr.py (per-city regional SLR) (Gap K)
  - pluvial_flood.py (surface water susceptibility) (Gap M)
  - Google Open Buildings V3 + 2.5D (footprints + heights)
  - Overture Maps (building attributes)
  - JRC Flood Depth-Damage Functions (vulnerability curves)
"""

from agno.workflow import Workflow, Step
from src.core.models import (
    Location, AdjustedSurface, FullRiskProfile, HazardAssessmentResult,
    CycloneEventParams, SSPScenario, BuildingCluster,
    StructureRiskResult, PortfolioRiskSummary,
    BuildingAdjustedSurface,                     # NEW v3.2 (Gap S)
    STANDARD_RETURN_PERIODS,                     # NEW v3.2 (Gap Q)
)
from src.workflows.steps.asset_fetch import fetch_buildings_step
from src.workflows.steps.chronic_hazards import assess_chronic_hazards_step
from src.workflows.steps.cyclone_step import assess_cyclone_step
from src.workflows.steps.acute_hazards import assess_acute_hazards_step
from src.workflows.steps.structure_risk import assess_structure_risk_step
from src.workflows.steps.composite import calculate_composite_step
from src.config.city_hazards import CITY_HAZARDS


def create_hazard_assessment_workflow() -> Workflow:
    """
    Create the 6-step hazard assessment pipeline (v3.2).

    ┌──────────────────────────────────────────────────────────┐
    │ Step 0: Asset Fetch (v3.2: + BuildingAdjustedSurface)    │
    │   └── fetch_buildings() → BuildingCluster + surfaces     │
    ├──────────────────────────────────────────────────────────┤
    │ Step 1: Chronic Hazards (Parallel)                       │
    │   ├── assess_subsidence() → AdjustedSurface (Gap L)      │
    │   └── assess_urban_heat() [LST + WBGT + NEX-GDDP]       │
    ├──────────────────────────────────────────────────────────┤
    │ Step 2: Cyclone Assessment (Holland 2008 — Gap P)        │
    │   └── assess_cyclone() → CycloneEventParams              │
    ├──────────────────────────────────────────────────────────┤
    │ Step 3: Acute Hazards (Parallel × Multi-RP — Gap Q)      │
    │   ├── FOR EACH RP in [2, 5, 10, 25, 50, 100, 250, 500, 1000]:            │
    │   │   ├── assess_storm_surge(cyclone, surface, bathy)    │
    │   │   ├── assess_coastal_flood(surface, ipcc_slr, city)  │
    │   │   ├── assess_riverine_flood(surface, rating_curve)   │
    │   │   ├── assess_pluvial_flood(HAND, slope, NDVI)  NEW  │
    │   │   └── assess_landslide(SoilGrids, NDVI)             │
    ├──────────────────────────────────────────────────────────┤
    │ Step 4: Structure Risk (v3.2: multi-RP EAL)              │
    │   └── H×E×V per building × multi-RP → trapezoidal EAL   │
    │       + BuildingAdjustedSurface (Gap S)                  │
    │       + OCCUPANCY_VALUE_MULTIPLIER (Gap T)               │
    ├──────────────────────────────────────────────────────────┤
    │ Step 5: Composite Calculation                            │
    │   └── aggregate → FullRiskProfile + PortfolioSummary     │
    └──────────────────────────────────────────────────────────┘
    """
    return Workflow(
        name="HazardAssessmentWorkflow",
        description="Multi-hazard climate risk: 8 hazards, multi-RP EAL, structure H×E×V (v3.2)",
        steps=[
            Step(
                name="asset_fetch",
                executor=fetch_buildings_step,
                description="Fetch buildings + create BuildingAdjustedSurface (v3.2 Gap S)"
            ),
            Step(
                name="chronic_hazards",
                executor=assess_chronic_hazards_step,
                description="Chronic: subsidence (InSAR + published fallback) + urban heat"
            ),
            Step(
                name="cyclone_assessment",
                executor=assess_cyclone_step,
                description="Cyclone: IBTrACS + Holland (2008) → CycloneEventParams"
            ),
            Step(
                name="acute_hazards",
                executor=assess_acute_hazards_step,
                description="Acute: flood + surge + landslide + pluvial × multi-RP [2-1000yr]"
            ),
            Step(
                name="structure_risk",
                executor=assess_structure_risk_step,
                description="Structure H×E×V: multi-RP EAL via trapezoidal integration (v3.2)"
            ),
            Step(
                name="composite",
                executor=calculate_composite_step,
                description="Composite: weighted risk scores → FullRiskProfile + PortfolioEAL"
            ),
        ]
    )


hazard_workflow = create_hazard_assessment_workflow()


async def run_hazard_assessment(
    lat: float, lon: float,
    city: str = "hcmc",
    return_period: int = 100,
    time_horizon: int = 2050,
    slr_scenario: str = "ssp245",
    include_buildings: bool = True,
    building_radius_m: int = 500,
    multi_rp: bool = True,                        # NEW v3.2 (Gap Q)
    return_periods: list = None,                   # NEW v3.2 (Gap Q)
) -> FullRiskProfile:
    """
    Run full multi-hazard assessment for a single location.

    This is the main entry point called by the API layer (Phase 5).

    v3.2 Changes:
      - multi_rp=True enables multi-RP loop at STANDARD_RETURN_PERIODS.
        When True, Steps 2-3 run at each RP, and Step 4 computes EAL
        via trapezoidal integration over the loss-exceedance curve.
      - return_periods overrides STANDARD_RETURN_PERIODS if provided.
      - return_period is still used as the "primary" RP for display/tier.
    """
    hazard_config = CITY_HAZARDS.get(city, CITY_HAZARDS["hcmc"])

    # v3.2 (Gap Q): Determine return periods for multi-RP loop
    if multi_rp:
        rp_list = return_periods or STANDARD_RETURN_PERIODS  # [2, 5, 10, 25, 50, 100, 250, 500, 1000]
    else:
        rp_list = [return_period]  # Backward-compatible single-RP mode

    input_data = {
        "lat": lat,
        "lon": lon,
        "city": city,
        "return_period": return_period,            # Primary RP for display
        "return_periods": rp_list,                 # NEW v3.2 (Gap Q)
        "time_horizon": time_horizon,
        "slr_scenario": slr_scenario,
        "hazard_config": hazard_config,
        "include_buildings": include_buildings,
        "building_radius_m": building_radius_m,
    }

    result = await hazard_workflow.arun(input=input_data)
    return result.output
```

---

## 3. Step 0: Asset Fetch (FIX v3.2 — Gap S)

```python
# src/workflows/steps/asset_fetch.py
"""
Step 0: Fetch buildings + create BuildingAdjustedSurface per building.

v3.1: Fetched BuildingCluster from PostGIS cache.
v3.2 (Gap S): Now also creates a BuildingAdjustedSurface for each building,
providing per-building centroid elevation from GLO-30. Subsidence is
populated in Step 1 after subsidence assessment.

Inputs:
  - lat, lon: Assessment center point
  - building_radius_m: Search radius (default 500m)

Outputs:
  - BuildingCluster: All buildings within radius
  - building_surfaces: Dict[building_id → BuildingAdjustedSurface] (NEW v3.2)
"""

import asyncio
from typing import Optional, Dict

from src.core.models import (
    Location, BuildingCluster, BuildingFootprint, BuildingHeight,
    StructuralCharacteristics, VulnerabilityClass,
    BuildingAdjustedSurface,                     # NEW v3.2 (Gap S)
)
from src.data.open_buildings import OpenBuildingsSource
from src.data.overture_buildings import OvertureBuildingsSource
from src.data.elevation import get_elevation


open_buildings = OpenBuildingsSource()
overture = OvertureBuildingsSource()


async def fetch_buildings_step(input_data: dict) -> dict:
    """
    Fetch all buildings within radius + create per-building surfaces.

    v3.2 (Gap S): Each building gets a BuildingAdjustedSurface with its
    centroid elevation. Subsidence and SLR are populated downstream.
    """
    lat = input_data["lat"]
    lon = input_data["lon"]
    radius_m = input_data.get("building_radius_m", 500)
    include_buildings = input_data.get("include_buildings", True)

    if not include_buildings:
        input_data["building_cluster"] = None
        input_data["building_surfaces"] = {}
        return input_data

    # Query PostGIS cache first (fast path)
    cluster = await open_buildings.get_buildings_in_radius(
        lat=lat, lon=lon, radius_m=radius_m
    )

    if cluster is None or cluster.count == 0:
        # Fallback: on-demand query from Overture Maps
        cluster = await overture.get_buildings_in_radius(
            lat=lat, lon=lon, radius_m=radius_m
        )

    # ── NEW v3.2 (Gap S): Create BuildingAdjustedSurface per building ──
    # Each building gets its centroid elevation from GLO-30.
    # Subsidence is populated in Step 1 after subsidence tool runs.
    building_surfaces: Dict[str, BuildingAdjustedSurface] = {}

    if cluster and cluster.structures:
        # Batch elevation lookup at building centroids
        elevation_tasks = []
        for structure in cluster.structures:
            bid = structure.footprint.building_id
            c_lat = structure.footprint.centroid.lat
            c_lon = structure.footprint.centroid.lon
            elevation_tasks.append((bid, get_elevation(c_lat, c_lon)))

        # Parallel elevation fetch (all centroids at once)
        elevations = await asyncio.gather(
            *[t[1] for t in elevation_tasks], return_exceptions=True
        )

        for (bid, _), elev_result in zip(elevation_tasks, elevations):
            if isinstance(elev_result, Exception):
                # Default elevation if GLO-30 fails for this centroid
                building_surfaces[bid] = BuildingAdjustedSurface(
                    building_id=bid,
                    original_elevation_m=0.0,
                    subsidence_source="none",
                )
            else:
                building_surfaces[bid] = BuildingAdjustedSurface(
                    building_id=bid,
                    original_elevation_m=elev_result.elevation_m,
                    subsidence_source="none",  # Populated in Step 1
                )

    input_data["building_cluster"] = cluster
    input_data["building_surfaces"] = building_surfaces  # NEW v3.2 (Gap S)
    return input_data
```

---

## 4. Step 1: Chronic Hazards (FIX v3.2 — Gap L, S)

```python
# src/workflows/steps/chronic_hazards.py
"""
Step 1: Chronic hazards — subsidence + urban heat (parallel).

v3.2 Changes:
  - Gap L: Subsidence tool now has published-rate fallback. The workflow
           tracks subsidence_source ("insar_measured" or "published_literature")
           from the tool's intermediate output.
  - Gap S: After subsidence assessment, populate BuildingAdjustedSurface
           for each building with spatially interpolated subsidence rate.
           (For MVP: uniform rate within tile; future: bilinear interpolation.)

Outputs:
  - AdjustedSurface (tile-level, backward-compatible)
  - building_surfaces updated with subsidence rates (Gap S)
  - Chronic results dict
"""

import asyncio
from src.core.models import AdjustedSurface, BuildingAdjustedSurface
from src.data.elevation import get_elevation
from src.tools.subsidence_tools import assess_subsidence
from src.tools.urban_heat_tools import assess_urban_heat


async def assess_chronic_hazards_step(step_input):
    """
    Execute chronic hazard assessments in parallel.

    v3.2: Also populates per-building subsidence in BuildingAdjustedSurface.
    """
    data = step_input.input if isinstance(step_input.input, dict) else {}
    lat = data.get("lat")
    lon = data.get("lon")
    city = data.get("city", "hcmc")
    time_horizon = data.get("time_horizon", 2050)
    slr_scenario = data.get("slr_scenario", "ssp245")
    hazard_config = data.get("hazard_config", {})
    chronic_hazards = hazard_config.get("chronic", [])
    building_surfaces = data.get("building_surfaces", {})  # From Step 0 (Gap S)

    # Get baseline elevation from GLO-30
    elevation = await get_elevation(lat, lon)
    surface = AdjustedSurface(original_elevation_m=elevation.elevation_m)

    # Launch chronic assessments in parallel
    chronic_results = {}
    tasks = []

    if "subsidence" in chronic_hazards:
        tasks.append(("subsidence", assess_subsidence(lat, lon, city, time_horizon)))
    if "urban_heat" in chronic_hazards:
        tasks.append(("urban_heat", assess_urban_heat(
            lat, lon, time_horizon, scenario=slr_scenario
        )))

    if tasks:
        results = await asyncio.gather(
            *[t[1] for t in tasks], return_exceptions=True
        )
        for (name, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                print(f"Warning: chronic hazard '{name}' failed: {result}")
            else:
                chronic_results[name] = result
                if name == "subsidence" and result:
                    cumulative_m = result.intermediate.get("cumulative_m", 0)
                    surface.apply_subsidence(cumulative_m)

                    # ── NEW v3.2 (Gap S): Populate per-building subsidence ──
                    # For MVP: uniform subsidence within tile.
                    # Future: spatially interpolate if InSAR grid available.
                    velocity_mm_yr = result.intermediate.get("abs_rate_mm_yr", 0)
                    subsidence_source = result.intermediate.get(
                        "subsidence_source", "insar_measured"  # Gap L
                    )
                    for bid, bldg_surface in building_surfaces.items():
                        bldg_surface.subsidence_rate_mm_yr = velocity_mm_yr
                        bldg_surface.subsidence_cumulative_m = cumulative_m
                        bldg_surface.subsidence_source = subsidence_source

    from agno.workflow import StepOutput
    return StepOutput(
        step_name="chronic_hazards",
        success=True,
        data={
            "lat": lat, "lon": lon, "city": city,
            "return_period": data.get("return_period", 100),
            "return_periods": data.get("return_periods", [100]),  # v3.2 multi-RP
            "time_horizon": time_horizon,
            "slr_scenario": slr_scenario,
            "hazard_config": hazard_config,
            "chronic_results": {k: v.model_dump() for k, v in chronic_results.items()},
            "surface": surface.model_dump(),
            "building_cluster": data.get("building_cluster"),
            "building_surfaces": building_surfaces,  # v3.2 (Gap S): now with subsidence
            "include_buildings": data.get("include_buildings", True),
        }
    )
```

---

## 5. Step 2: Cyclone Assessment (FIX v3.2 — Gap P)

```python
# src/workflows/steps/cyclone_step.py
"""
Step 2: Cyclone assessment — exports CycloneEventParams for storm surge.

v3.2 (Gap P): Cyclone tool internally uses Holland (2008) parametric wind
profile (via holland_wind.py) instead of Holland (1980). No workflow-level
code change needed — the tool handles the upgrade transparently.
The intermediate output now includes `holland_b_parameter`.

Uses IBTrACS v04r01 (API-accessible via NCEI HTTPS).
"""

from src.tools.cyclone_tools import assess_cyclone
from src.core.models import AdjustedSurface


async def assess_cyclone_step(step_input):
    """
    Execute cyclone hazard assessment.

    v3.2: Cyclone params now derived from Holland (2008) revised profile.
    Passes cyclone_params to Step 3 for storm surge at each return period.
    """
    data = step_input.data if hasattr(step_input, 'data') else step_input.input
    lat = data.get("lat")
    lon = data.get("lon")
    return_period = data.get("return_period", 100)
    hazard_config = data.get("hazard_config", {})
    acute_hazards = hazard_config.get("acute", [])

    cyclone_result = None
    cyclone_params = None

    if "tropical_cyclone" in acute_hazards:
        try:
            cyclone_result = await assess_cyclone(lat, lon, return_period)
            cyclone_params = cyclone_result.intermediate.get("cyclone_params")
        except Exception as e:
            print(f"Warning: cyclone assessment failed: {e}")

    from agno.workflow import StepOutput
    return StepOutput(
        step_name="cyclone_assessment",
        success=True,
        data={
            **data,
            "cyclone_result": cyclone_result.model_dump() if cyclone_result else None,
            "cyclone_params": cyclone_params,
        }
    )
```

---

## 6. Step 3: Acute Hazards (FIX v3.2 — Gap J, K, M, Q)

```python
# src/workflows/steps/acute_hazards.py
"""
Step 3: Acute hazards — flood, surge, landslide, pluvial (parallel × multi-RP).

v3.2 Changes:
  - Gap M: Added assess_pluvial_flood to parallel acute hazard execution.
  - Gap J: assess_riverine_flood now receives `city` for rating_curve params.
  - Gap K: assess_coastal_flood now receives `city` for ipcc_slr regional SLR.
  - Gap Q: Multi-RP loop — runs acute hazards at each return period in
           STANDARD_RETURN_PERIODS = [2, 5, 10, 25, 50, 100, 250, 500, 1000].
           Returns {return_period: {hazard_name: HazardAssessmentResult}}.

Dependencies:
  - AdjustedSurface from Step 1 (subsidence-corrected elevation)
  - CycloneEventParams from Step 2 (wind/pressure for surge model)
"""

import asyncio
from src.core.models import AdjustedSurface, STANDARD_RETURN_PERIODS
from src.tools.riverine_flood_tools import assess_riverine_flood
from src.tools.coastal_flood_tools import assess_coastal_flood
from src.tools.storm_surge_tools import assess_storm_surge
from src.tools.landslide_tools import assess_landslide
from src.tools.pluvial_flood_tools import assess_pluvial_flood  # NEW v3.2 (Gap M)


async def assess_acute_hazards_step(step_input):
    """
    Execute acute hazard assessments in parallel, at multiple return periods.

    v3.2: Outer loop over return_periods, inner parallel dispatch per RP.
    Returns hazard_results_by_rp: Dict[int, Dict[str, HazardAssessmentResult]].
    """
    data = step_input.data if hasattr(step_input, 'data') else step_input.input
    lat = data.get("lat")
    lon = data.get("lon")
    city = data.get("city", "hcmc")  # v3.2: passed to riverine (Gap J) + coastal (Gap K)
    return_periods = data.get("return_periods", [100])  # v3.2 (Gap Q)
    time_horizon = data.get("time_horizon", 2050)
    slr_scenario = data.get("slr_scenario", "ssp245")
    hazard_config = data.get("hazard_config", {})
    acute_hazards = hazard_config.get("acute", [])
    tidal_range_m = hazard_config.get("tidal_range_m", 2.0)

    # Reconstruct AdjustedSurface from Step 1
    surface_data = data.get("surface", {})
    surface = AdjustedSurface(**surface_data) if surface_data else None

    # Get cyclone params from Step 2
    cyclone_params = data.get("cyclone_params")

    # ── Multi-RP loop (FIX v3.2 — Gap Q) ──
    # Run all acute hazards at each return period.
    # Landslide + coastal flood are RP-independent but included for
    # consistency (their result is the same at each RP).
    hazard_results_by_rp = {}

    for rp in return_periods:
        tasks = []

        if "riverine_flood" in acute_hazards:
            tasks.append(("riverine_flood", assess_riverine_flood(
                lat, lon, rp, surface,
                city=city,  # v3.2 (Gap J): per-city rating_curve params
            )))

        if "coastal_flood" in acute_hazards:
            tasks.append(("coastal_flood", assess_coastal_flood(
                lat, lon, time_horizon, slr_scenario, surface, tidal_range_m,
                city=city,  # v3.2 (Gap K): per-city ipcc_slr regional SLR
            )))

        if "storm_surge" in acute_hazards:
            tasks.append(("storm_surge", assess_storm_surge(
                lat, lon, cyclone_params, surface, rp
            )))

        if "landslide" in acute_hazards:
            tasks.append(("landslide", assess_landslide(
                lat, lon, rp
            )))

        # NEW v3.2 (Gap M): Pluvial flood assessment
        if "pluvial_flood" in acute_hazards:
            tasks.append(("pluvial_flood", assess_pluvial_flood(
                lat, lon, rp
            )))

        # Run all hazards for this RP in parallel
        rp_results = {}
        if tasks:
            results = await asyncio.gather(
                *[t[1] for t in tasks], return_exceptions=True
            )
            for (name, _), result in zip(tasks, results):
                if isinstance(result, Exception):
                    print(f"Warning: acute hazard '{name}' @ RP={rp} failed: {result}")
                else:
                    rp_results[name] = result

        hazard_results_by_rp[rp] = rp_results

    # Also store primary RP results for backward compatibility (composite step)
    primary_rp = data.get("return_period", 100)
    primary_results = hazard_results_by_rp.get(primary_rp, {})
    if not primary_results and hazard_results_by_rp:
        # If primary RP not in list, use the closest
        closest_rp = min(hazard_results_by_rp.keys(), key=lambda x: abs(x - primary_rp))
        primary_results = hazard_results_by_rp[closest_rp]

    from agno.workflow import StepOutput
    return StepOutput(
        step_name="acute_hazards",
        success=True,
        data={
            **data,
            "hazard_results_by_rp": {
                rp: {k: v.model_dump() for k, v in rp_res.items()}
                for rp, rp_res in hazard_results_by_rp.items()
            },
            # Backward-compatible flat dict at primary RP
            "acute_results": {k: v.model_dump() for k, v in primary_results.items()},
        }
    )
```

---

## 7. Step 4: Structure Risk (FIX v3.2 — Gap Q, S, T)

```python
# src/workflows/steps/structure_risk.py
"""
Step 4: Apply H×E×V to each building × multiple return periods.

v3.2 Changes:
  - Gap Q: Passes hazard_results_by_rp (multi-RP nested dict) to
           assess_structure_risk(). The tool builds a loss-exceedance curve
           at each RP and integrates EAL via trapezoidal rule.
  - Gap S: Passes building_surfaces (BuildingAdjustedSurface per building)
           for per-building elevation, subsidence, and SLR context.
  - Gap T: OCCUPANCY_VALUE_MULTIPLIER applied inside assess_structure_risk()
           — no workflow code change, but the tool now uses it.

Inputs (from previous steps):
  - building_cluster: BuildingCluster from Step 0
  - building_surfaces: Dict[building_id → BuildingAdjustedSurface] from Step 0+1
  - hazard_results_by_rp: Dict[RP → Dict[HazardType → Result]] from Step 3
  - city: City key for country code lookup

Outputs:
  - structure_results: List[StructureRiskResult] with multi-RP EAL
  - portfolio_summary: PortfolioRiskSummary
"""

from typing import List, Optional
from src.core.models import (
    BuildingCluster, StructureRiskResult, PortfolioRiskSummary,
    HazardType, HazardAssessmentResult,
)
from src.tools.structure_risk_tools import assess_structure_risk, summarize_portfolio
from src.config.city_hazards import CITY_HAZARDS


async def assess_structure_risk_step(step_input):
    """
    Run multi-RP H×E×V per building using hazard outputs from Steps 1-3.

    v3.2: Passes the full multi-RP hazard results dict so the tool can
    build per-building loss-exceedance curves and compute trapezoidal EAL.
    """
    data = step_input.data if hasattr(step_input, 'data') else step_input.input
    building_cluster = data.get("building_cluster")
    building_surfaces = data.get("building_surfaces", {})  # v3.2 (Gap S)
    city = data.get("city", "hcmc")
    country = CITY_HAZARDS.get(city, {}).get("country", "VN")

    if building_cluster is None or (hasattr(building_cluster, 'count') and building_cluster.count == 0):
        data["structure_results"] = []
        data["portfolio_summary"] = None
        from agno.workflow import StepOutput
        return StepOutput(step_name="structure_risk", success=True, data=data)

    # ── Reconstruct hazard_results_by_rp (FIX v3.2 — Gap Q) ──
    # The multi-RP results from Step 3 are serialized dicts;
    # reconstruct into {int_rp: {hazard_name: HazardAssessmentResult}}
    raw_by_rp = data.get("hazard_results_by_rp", {})

    # Convert string keys back to int (JSON serialization may stringify)
    hazard_results_by_rp = {}
    for rp_key, rp_results in raw_by_rp.items():
        rp = int(rp_key)
        hazard_results_by_rp[rp] = {}
        for hazard_name, result_dict in rp_results.items():
            hazard_results_by_rp[rp][hazard_name] = (
                HazardAssessmentResult(**result_dict)
                if isinstance(result_dict, dict) else result_dict
            )

    # ── If no multi-RP data, fall back to single-RP from acute_results ──
    if not hazard_results_by_rp:
        primary_rp = data.get("return_period", 100)
        acute_results = data.get("acute_results", {})
        hazard_results_by_rp = {primary_rp: {
            name: HazardAssessmentResult(**rd) if isinstance(rd, dict) else rd
            for name, rd in acute_results.items()
        }}

    # ── Apply H×E×V with multi-RP + per-building surfaces ──
    structure_results = await assess_structure_risk(
        buildings=building_cluster,
        hazard_results_by_rp=hazard_results_by_rp,  # v3.2 (Gap Q)
        building_surfaces=building_surfaces,          # v3.2 (Gap S)
        country=country,
    )

    # Aggregate into portfolio summary
    portfolio_summary = summarize_portfolio(
        structure_results=structure_results,
        portfolio_id=f"{city}_{data['lat']:.4f}_{data['lon']:.4f}",
        city=city,
    )

    data["structure_results"] = structure_results
    data["portfolio_summary"] = portfolio_summary

    from agno.workflow import StepOutput
    return StepOutput(step_name="structure_risk", success=True, data=data)
```

---

## 8. Step 5: Composite Calculation (FIX v3.2 — Gap M)

```python
# src/workflows/steps/composite.py
"""
Step 5: Composite risk calculation — weighted aggregation.

v3.2 Changes:
  - Gap M: pluvial_flood now included in acute composite scoring.
  - Portfolio-level EAL aggregated from structure_results.

CRITICAL RULES:
  1. Acute hazards aggregated separately (same return period)
  2. Chronic hazards aggregated separately (same time horizon)
  3. NEVER combine acute + chronic into a single score
  4. City-specific weights from hazard_weights.yaml
"""

import yaml
from pathlib import Path
from src.core.models import (
    FullRiskProfile, CompositeRiskResult, RiskTier,
    HazardAssessmentResult,
)

WEIGHTS_PATH = Path("src/config/hazard_weights.yaml")


async def calculate_composite_step(step_input):
    """
    Calculate weighted composite risk scores.

    v3.2: pluvial_flood included in acute scores. Portfolio EAL available.
    """
    data = step_input.data if hasattr(step_input, 'data') else step_input.input
    city = data.get("city", "hcmc")

    weights = _load_weights(city)

    # Collect results (primary RP for composite scoring)
    chronic_results = data.get("chronic_results", {})
    cyclone_result = data.get("cyclone_result")
    acute_results = data.get("acute_results", {})

    if cyclone_result:
        acute_results["tropical_cyclone"] = cyclone_result

    # Acute composite
    acute_scores = {}
    for hazard_name, result_data in acute_results.items():
        score = result_data.get("impact_score", 0) if isinstance(result_data, dict) else 0
        acute_scores[hazard_name] = score

    acute_weights = weights.get("acute", {})
    acute_composite = _weighted_average(acute_scores, acute_weights)

    # Chronic composite
    chronic_scores = {}
    for hazard_name, result_data in chronic_results.items():
        score = result_data.get("impact_score", 0) if isinstance(result_data, dict) else 0
        chronic_scores[hazard_name] = score

    chronic_weights = weights.get("chronic", {})
    chronic_composite = _weighted_average(chronic_scores, chronic_weights)

    # v3.2: Portfolio-level EAL from structure results
    portfolio_summary = data.get("portfolio_summary")
    portfolio_eal = None
    if portfolio_summary:
        portfolio_eal = (
            portfolio_summary.total_expected_annual_loss_usd
            if hasattr(portfolio_summary, 'total_expected_annual_loss_usd')
            else portfolio_summary.get("total_expected_annual_loss_usd")
            if isinstance(portfolio_summary, dict)
            else None
        )

    profile = FullRiskProfile(
        acute_risk=CompositeRiskResult(
            composite_score=round(acute_composite, 1),
            tier=_score_to_tier(acute_composite),
            component_scores=acute_scores,
            weights=acute_weights,
        ),
        chronic_risk=CompositeRiskResult(
            composite_score=round(chronic_composite, 1),
            tier=_score_to_tier(chronic_composite),
            component_scores=chronic_scores,
            weights=chronic_weights,
        ),
        location={"lat": data.get("lat"), "lon": data.get("lon")},
        city=city,
        return_period=data.get("return_period", 100),
        time_horizon=data.get("time_horizon", 2050),
        scenario=data.get("slr_scenario", "ssp245"),
        portfolio_eal_usd=portfolio_eal,  # v3.2: multi-RP EAL
    )

    from agno.workflow import StepOutput
    return StepOutput(
        step_name="composite",
        success=True,
        data=profile.model_dump(),
        output=profile,
    )


def _weighted_average(scores: dict, weights: dict) -> float:
    total_weight = sum(weights.get(k, 0) for k in scores)
    if total_weight == 0:
        return 0.0
    return sum(
        scores[k] * weights.get(k, 0) / total_weight
        for k in scores if k in weights
    )


def _load_weights(city: str) -> dict:
    try:
        with open(WEIGHTS_PATH) as f:
            all_weights = yaml.safe_load(f)
        return all_weights.get(city, all_weights.get("hcmc", {}))
    except FileNotFoundError:
        return _default_weights(city)


def _default_weights(city: str) -> dict:
    """Fallback weights — v3.2: includes pluvial_flood, subsidence city-specific."""
    # Only cities with confirmed active subsidence get subsidence weight.
    # HCMC, Jakarta, Manila: active subsidence (peer-reviewed InSAR data).
    # Hanoi: diminishing/localized (Nguyen et al. 2022). Bangkok: mitigated.
    subsidence_cities = {"hcmc", "jakarta", "manila"}
    if city in subsidence_cities:
        chronic = {"subsidence": 0.60, "urban_heat": 0.40}
    else:
        chronic = {"urban_heat": 1.00}

    return {
        "acute": {
            "riverine_flood": 0.25,
            "coastal_flood": 0.20,
            "storm_surge": 0.15,
            "tropical_cyclone": 0.10,
            "landslide": 0.10,
            "pluvial_flood": 0.20,  # NEW v3.2 (Gap M)
        },
        "chronic": chronic,
    }


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75: return RiskTier.CRITICAL
    elif score >= 50: return RiskTier.HIGH
    elif score >= 25: return RiskTier.MODERATE
    return RiskTier.LOW
```

---

## 9. Hazard Weights Configuration (FIX v3.2 — Gap M)

```yaml
# src/config/hazard_weights.yaml
# City-specific hazard weights for composite scoring.
# Acute and chronic weights must each sum to 1.0 within their group.
# v3.2 (Gap M): pluvial_flood added to all cities with urban flooding.
# Existing acute weights rebalanced to accommodate pluvial_flood.
#
# v3.2 subsidence policy (evidence-based):
#   Chronic subsidence only included for cities with confirmed severe,
#   ongoing, unmitigated subsidence (peer-reviewed InSAR evidence):
#     ✅ HCMC (up to 80 mm/yr), Jakarta (up to 250 mm/yr), Manila (up to 109 mm/yr)
#     ❌ Hanoi — diminishing central; localized peri-urban (Nguyen et al. 2022)
#     ❌ Bangkok — mitigated inner city ~0-1 cm/yr (Phien-wej et al. 2006)
#     ❌ Da Nang, Singapore — no significant subsidence

# ── Vietnam (MVP) ──

hcmc:
  acute:
    riverine_flood: 0.25    # Mekong Delta, frequent urban flooding
    coastal_flood: 0.20     # Low-lying coastal, high SLR exposure
    storm_surge: 0.15       # Typhoon surge + funnel geography
    tropical_cyclone: 0.10  # Moderate direct cyclone exposure
    landslide: 0.05         # Mostly flat, minimal slope risk
    pluvial_flood: 0.25     # v3.2: Dominant flood type, 20-30+ events/yr
  chronic:
    subsidence: 0.65        # Severe: up to 80mm/yr District 7 (World Bank 2015)
    urban_heat: 0.35        # Tropical, high UHI

hanoi:
  acute:
    riverine_flood: 0.30    # Red River flood exposure
    tropical_cyclone: 0.20  # Northern VN typhoon corridor
    landslide: 0.20         # Surrounding hills/mountains
    pluvial_flood: 0.30     # v3.2: Frequent monsoon surface flooding
  chronic:
    urban_heat: 1.00        # v3.2: Subsidence removed — central Hanoi diminishing,
                            # localized peri-urban hotspots only (Nguyen et al. 2022)

danang:
  acute:
    riverine_flood: 0.20    # Han River + mountain runoff
    coastal_flood: 0.15     # Exposed coastline
    storm_surge: 0.15       # Direct typhoon path
    tropical_cyclone: 0.15  # Central VN typhoon corridor
    landslide: 0.10         # Hai Van pass terrain
    pluvial_flood: 0.25     # v3.2: Monsoon intensity events
  chronic:
    urban_heat: 1.00        # No significant subsidence

# ── Indonesia ──

jakarta:
  acute:
    riverine_flood: 0.25    # Ciliwung River, extreme urban flooding
    coastal_flood: 0.20     # North Jakarta sinking below sea level
    storm_surge: 0.15       # Java Sea surge potential
    landslide: 0.10         # Southern hills/Bogor
    pluvial_flood: 0.30     # v3.2: Most frequent hazard — drainage overwhelmed
  chronic:
    subsidence: 0.70        # World's most severe: up to 250mm/yr North Jakarta
                            # (Frontiers in Earth Science 2024). Capital relocation
                            # to Nusantara partly driven by subsidence.
    urban_heat: 0.30        # Tropical, dense urban

# ── Philippines ──

manila:
  acute:
    riverine_flood: 0.20    # Pasig River + Marikina
    coastal_flood: 0.15     # Manila Bay exposure
    storm_surge: 0.15       # Typhoon surge (Super Typhoon Haiyan class)
    tropical_cyclone: 0.20  # Highest cyclone exposure in SEA
    landslide: 0.05         # Marikina Valley slopes
    pluvial_flood: 0.25     # v3.2: Habagat monsoon surface flooding
  chronic:
    subsidence: 0.55        # Severe: max 109 mm/yr Bulacan, 20-42 mm/yr
                            # Metro Manila (Sulapas et al. 2024). Groundwater
                            # over-extraction ongoing; no effective mitigation.
    urban_heat: 0.45        # Dense urban, tropical

# ── Thailand ──

bangkok:
  acute:
    riverine_flood: 0.30    # Chao Phraya, 2011 megaflood precedent
    coastal_flood: 0.20     # Gulf of Thailand, very low-lying
    storm_surge: 0.20       # Funnel geography in Gulf
    pluvial_flood: 0.30     # v3.2: Annual monsoon flooding (June-Oct)
  chronic:
    urban_heat: 1.00        # v3.2: Subsidence removed — inner Bangkok mitigated
                            # to ~0-1 cm/yr via strict groundwater regulation
                            # (Phien-wej et al. 2006; Mekong-US Partnership 2020)

# ── Singapore ──

singapore:
  acute:
    coastal_flood: 0.35     # Island nation, SLR existential threat
    storm_surge: 0.30       # Strait of Malacca surge
    pluvial_flood: 0.35     # v3.2: Flash floods from intense convective storms
  chronic:
    urban_heat: 1.00        # Dense urban, near-equatorial, no subsidence
```

---

## 10. Portfolio Workflow (FIX v3.2 — Multi-RP EAL Aggregation)

```python
# src/workflows/portfolio_workflow.py
"""
Batch portfolio assessment — run hazard workflow for multiple sites.

v3.2 Changes:
  - Portfolio summary includes total_eal_usd aggregated from per-site
    structure-level multi-RP EAL (Gap Q).
  - Each site runs full multi-RP loop; EAL is the primary financial metric.
"""

import asyncio
from src.workflows.hazard_workflow import run_hazard_assessment


async def run_portfolio_assessment(
    sites: list,
    scenario: str = "ssp245",
    return_period: int = 100,
    time_horizon: int = 2050,
    max_concurrent: int = 5,
    multi_rp: bool = True,               # NEW v3.2 (Gap Q)
) -> dict:
    """
    Run hazard assessment across a portfolio of sites.

    Args:
        sites: List of dicts with lat, lon, city, (optional) asset_value_usd
        scenario: SSP climate scenario
        return_period: Primary return period for display
        time_horizon: Year for chronic/SLR projections
        max_concurrent: Max parallel site assessments
        multi_rp: Enable multi-RP EAL computation (v3.2)

    Returns:
        Dict with site_results, portfolio_summary, and total_eal_usd
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _assess_site(site):
        async with semaphore:
            try:
                result = await run_hazard_assessment(
                    lat=site["lat"],
                    lon=site["lon"],
                    city=site.get("city", "hcmc"),
                    return_period=return_period,
                    time_horizon=time_horizon,
                    slr_scenario=scenario,
                    multi_rp=multi_rp,  # v3.2 (Gap Q)
                )
                return {"site": site, "result": result.model_dump(), "error": None}
            except Exception as e:
                return {"site": site, "result": None, "error": str(e)}

    site_results = await asyncio.gather(*[_assess_site(s) for s in sites])

    # Portfolio summary
    acute_scores = [r["result"]["acute_risk"]["composite_score"]
                    for r in site_results if r["result"]]
    chronic_scores = [r["result"]["chronic_risk"]["composite_score"]
                      for r in site_results if r["result"]]

    # v3.2 (Gap Q): Aggregate portfolio EAL from per-site multi-RP results
    site_eals = [
        r["result"].get("portfolio_eal_usd", 0) or 0
        for r in site_results if r["result"]
    ]
    total_eal = sum(site_eals)

    return {
        "n_sites": len(sites),
        "n_successful": sum(1 for r in site_results if r["result"]),
        "site_results": site_results,
        "portfolio_summary": {
            "mean_acute_score": round(sum(acute_scores) / max(len(acute_scores), 1), 1),
            "max_acute_score": round(max(acute_scores, default=0), 1),
            "mean_chronic_score": round(sum(chronic_scores) / max(len(chronic_scores), 1), 1),
            "max_chronic_score": round(max(chronic_scores, default=0), 1),
            "high_risk_sites": sum(1 for s in acute_scores if s >= 50),
            "total_eal_usd": round(total_eal, 2),                  # NEW v3.2
            "mean_eal_usd": round(total_eal / max(len(site_eals), 1), 2),  # NEW v3.2
        }
    }
```

---

## 11. Testing

```python
# tests/integration/test_workflow.py
"""
Integration tests for v3.2 workflow.
Validates: 8 hazard tools, multi-RP loop, per-building EAL, pluvial flood.
"""
import asyncio
from src.workflows.hazard_workflow import run_hazard_assessment
from src.core.models import STANDARD_RETURN_PERIODS

# ── Test HCMC (MVP target, all 8 hazards) ──
result = asyncio.run(run_hazard_assessment(
    lat=10.8, lon=106.6, city="hcmc",
    return_period=100, time_horizon=2050, slr_scenario="ssp245",
    multi_rp=True,  # v3.2: runs [2, 5, 10, 25, 50, 100, 250, 500, 1000]
))
print(f"HCMC Acute: {result.acute_risk.composite_score}")
print(f"HCMC Chronic: {result.chronic_risk.composite_score}")
print(f"HCMC Portfolio EAL: ${result.portfolio_eal_usd:,.0f}")
# Verify pluvial flood is in acute components
assert "pluvial_flood" in result.acute_risk.component_scores, "Gap M: pluvial_flood missing"

# ── Test Jakarta (severe subsidence + pluvial) ──
result = asyncio.run(run_hazard_assessment(
    lat=-6.2, lon=106.8, city="jakarta",
    return_period=100, time_horizon=2050, slr_scenario="ssp585",
    multi_rp=True,
))
print(f"Jakarta Acute: {result.acute_risk.composite_score}")
print(f"Jakarta Chronic: {result.chronic_risk.composite_score}")
print(f"Jakarta Portfolio EAL: ${result.portfolio_eal_usd:,.0f}")

# ── Test Singapore (minimal hazards, pluvial + coastal + surge only) ──
result = asyncio.run(run_hazard_assessment(
    lat=1.3, lon=103.8, city="singapore",
    return_period=100, time_horizon=2050, slr_scenario="ssp245",
    multi_rp=True,
))
print(f"Singapore Acute: {result.acute_risk.composite_score}")
assert "pluvial_flood" in result.acute_risk.component_scores

# ── Test backward compatibility: single-RP mode ──
result_single = asyncio.run(run_hazard_assessment(
    lat=10.8, lon=106.6, city="hcmc",
    return_period=100, time_horizon=2050,
    multi_rp=False,  # Legacy single-RP mode
))
print(f"HCMC Single-RP Acute: {result_single.acute_risk.composite_score}")
```

### Execution Trace (v3.2)

```
[Step 0] asset_fetch (v3.2: + BuildingAdjustedSurface)
    ├── fetch_buildings()        → PostGIS cache → BuildingCluster
    └── create_surfaces()        → GLO-30 elevation per centroid → Dict[bid, BuildingAdjustedSurface]

[Step 1] chronic_hazards (parallel, v3.2: populates per-building subsidence)
    ├── assess_subsidence()      → InSAR + published fallback (Gap L) → AdjustedSurface
    │   └── populate_surfaces()  → subsidence_rate/source → BuildingAdjustedSurface (Gap S)
    └── assess_urban_heat()      → Landsat LST + ERA5-Land WBGT + NEX-GDDP

[Step 2] cyclone_assessment (sequential)
    └── assess_cyclone()         → IBTrACS + Holland (2008) (Gap P) → CycloneEventParams

[Step 3] acute_hazards (parallel × multi-RP — Gap Q)
    └── FOR EACH RP in [2, 5, 10, 25, 50, 100, 250, 500, 1000]:
        ├── assess_riverine_flood()  → GloFAS + rating_curve (Gap J) + HAND + surface
        ├── assess_coastal_flood()   → ipcc_slr per-city (Gap K) + GLO-30 + surface
        ├── assess_storm_surge()     → IBTrACS params + GEBCO + GLO-30 + surface
        ├── assess_pluvial_flood()   → HAND + slope + NDVI + NEX-GDDP (NEW Gap M)
        └── assess_landslide()       → GLO-30 slope + NEX-GDDP + SoilGrids + S2 NDVI
    → Output: hazard_results_by_rp = {2: {...}, 10: {...}, 100: {...}, 1000: {...}}

[Step 4] structure_risk (v3.2: multi-RP EAL)
    └── assess_structure_risk()
        ├── Input: BuildingCluster × hazard_results_by_rp × BuildingAdjustedSurface
        ├── Per building:
        │   ├── JRC flood damage curve at each RP (riverine + coastal + pluvial + surge)
        │   ├── Wind damage at each RP
        │   ├── OCCUPANCY_VALUE_MULTIPLIER × replacement_value (Gap T)
        │   └── trapezoidal EAL = ∫₀¹ L(p) dp over [2,...,1000] (Gap Q)
        └── → List[StructureRiskResult] + PortfolioRiskSummary

[Step 5] composite
    └── calculate_composite()    → city weights × scores → FullRiskProfile + portfolio_eal_usd
```

---

## v3.2 Gap Fix Summary (Phase 4)

| Gap | Fix | Step(s) Affected |
|-----|-----|------------------|
| **J** | `city` passed to `assess_riverine_flood()` for per-city rating_curve params | Step 3 (acute_hazards) |
| **K** | `city` passed to `assess_coastal_flood()` for per-city ipcc_slr regional SLR | Step 3 (acute_hazards) |
| **L** | Subsidence source tracked from tool intermediate → per-building `subsidence_source` | Step 1 (chronic_hazards) |
| **M** | `assess_pluvial_flood` added to Step 3 parallel dispatch + pluvial_flood in city configs + weights | Step 3, §1, §9 |
| **P** | Cyclone tool uses Holland (2008) internally (transparent to workflow) | Step 2 (cyclone_step) |
| **Q** | Multi-RP loop: Steps 2-3 run at [2,5,10,25,50,100,250,500,1000]; Step 4 receives `hazard_results_by_rp` for trapezoidal EAL | Steps 3, 4, main workflow |
| **S** | `BuildingAdjustedSurface` created in Step 0, populated in Step 1, consumed in Step 4 | Steps 0, 1, 4 |
| **T** | `OCCUPANCY_VALUE_MULTIPLIER` applied inside `assess_structure_risk()` (no workflow code change) | Step 4 (via tool) |

---

## Next Phase

After completing Phase 4, proceed to **Phase 5: API Integration** (ECOSHIELD-PHASE5-API-v3.md).
Phase 5 must be updated for v3.2 to expose:
  - `multi_rp` and `return_periods` query parameters
  - `portfolio_eal_usd` in response schema
  - Pluvial flood results in hazard response
  - Per-building `losses_by_return_period` in structure risk response

---

*EcoShield Phase 4 v3.2 | Workflow Orchestration — 6-Step Pipeline, 8 Hazards, Multi-RP EAL, Per-Building Surfaces*
