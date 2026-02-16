
# EcoShield Phase 4: AsyncIO Pipeline Orchestration — v3.2

> **Phase 4 v3.2**: Complete workflow orchestration with **Custom AsyncIO Pipeline**.
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
>   and Bangkok. Retained for HCMC, Jakarta, Manila.
> - Expanded city hazard configurations + weights for all SEA target cities.

---

## Overview

Phase 4 implements the **Custom AsyncIO Pipeline** layer — a lightweight, deterministic system that coordinates the **8** hazard tools from Phase 3 into a dependency-respecting execution graph.

### Why Custom Pipeline (Replacing Agno)

| Feature | Agno Workflows | Custom AsyncIO Pipeline |
|---------|----------------|-------------------------|
| **Execution** | Deterministic | **Deterministic & Low-Overhead** |
| **Dependencies** | Framework-managed | **Explicit in Code (Step Sequence)** |
| **State** | Session-based | **Dict-based Data Flow** |
| **Complexity** | High (Agents/LLM bindings) | **Low (Pure Python AsyncIO)** |
| **Debugging** | Opaque (Framework internals) | **Transparent (Standard Stack Traces)** |

**EcoShield uses this custom pipeline** to eliminate unnecessary framework overhead while maintaining strict execution order: subsidence must complete before flood calculations can use the adjusted surface.

### Files Created

```
src/workflows/
├── __init__.py
├── pipeline.py                 # Core Pipeline & PipelineStep classes (NEW v3.2)
├── hazard_workflow.py          # Main 6-step workflow (uses Pipeline class)
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
(Same as v3.1, unchanged logic)
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
        "bounds": {"north": 11.2, "south": 10.4, "east": 107.0, "west": 106.3},
        "tidal_range_m": 3.5,
    },
    # ... (other cities same as before)
}
```

---

## 2. Main Hazard Workflow (FIX v3.2 — Multi-RP Loop)

```python
# src/workflows/hazard_workflow.py
"""
Main hazard assessment workflow using Custom AsyncIO Pipeline.

Execution Order (hard dependencies) — v3.2: 6 steps, 8 hazards, multi-RP:
  Step 0 — Asset Fetch: Load buildings + create BuildingAdjustedSurface (Gap S)
  Step 1 — Chronic Hazards: Subsidence (Gap L) + Urban Heat
  Step 2 — Cyclone: IBTrACS + Holland (2008) (Gap P)
  Step 3 — Acute Hazards: Flood + Surge + Landslide + Pluvial (Gap M)
           (Runs at multi-RP [2-1000yr] Gap Q)
  Step 4 — Structure Risk: Multi-RP H×E×V per building (Gap Q)
  Step 5 — Composite: Weighted aggregation + portfolio EAL
"""

from src.core.models import (
    FullRiskProfile, STANDARD_RETURN_PERIODS
)
from src.workflows.pipeline import Pipeline, PipelineStep
from src.workflows.steps.asset_fetch import fetch_buildings_step
from src.workflows.steps.chronic_hazards import assess_chronic_hazards_step
from src.workflows.steps.cyclone_step import assess_cyclone_step
from src.workflows.steps.acute_hazards import assess_acute_hazards_step
from src.workflows.steps.structure_risk import assess_structure_risk_step
from src.workflows.steps.composite import calculate_composite_step
from src.config.city_hazards import CITY_HAZARDS


def create_hazard_assessment_pipeline() -> Pipeline:
    """
    Create the 6-step hazard assessment pipeline (v3.2).
    """
    return Pipeline(
        name="HazardAssessment",
        steps=[
            PipelineStep(
                name="asset_fetch",
                executor=fetch_buildings_step,
                description="Fetch buildings + create BuildingAdjustedSurface (v3.2 Gap S)"
            ),
            PipelineStep(
                name="chronic_hazards",
                executor=assess_chronic_hazards_step,
                description="Chronic: subsidence (InSAR + published) + urban heat"
            ),
            PipelineStep(
                name="cyclone_assessment",
                executor=assess_cyclone_step,
                description="Cyclone: IBTrACS + Holland (2008) → CycloneEventParams"
            ),
            PipelineStep(
                name="acute_hazards",
                executor=assess_acute_hazards_step,
                description="Acute: flood + surge + landslide + pluvial × multi-RP"
            ),
            PipelineStep(
                name="structure_risk",
                executor=assess_structure_risk_step,
                description="Structure H×E×V: multi-RP EAL via trapezoidal integration"
            ),
            PipelineStep(
                name="composite",
                executor=calculate_composite_step,
                description="Composite: weighted risk scores → FullRiskProfile"
            ),
        ]
    )

hazard_pipeline = create_hazard_assessment_pipeline()

async def run_hazard_assessment(
    lat: float, lon: float,
    city: str = "hcmc",
    return_period: int = 100,
    time_horizon: int = 2050,
    slr_scenario: str = "ssp245",
    include_buildings: bool = True,
    building_radius_m: int = 500,
    multi_rp: bool = True,
    return_periods: list = None,
) -> FullRiskProfile:
    """
    Run full multi-hazard assessment for a single location.
    """
    hazard_config = CITY_HAZARDS.get(city, CITY_HAZARDS["hcmc"])

    # v3.2 (Gap Q): Determine return periods for multi-RP loop
    if multi_rp:
        rp_list = return_periods or STANDARD_RETURN_PERIODS
    else:
        rp_list = [return_period]

    input_data = {
        "lat": lat,
        "lon": lon,
        "city": city,
        "return_period": return_period,
        "return_periods": rp_list,
        "time_horizon": time_horizon,
        "slr_scenario": slr_scenario,
        "hazard_config": hazard_config,
        "include_buildings": include_buildings,
        "building_radius_m": building_radius_m,
    }

    result_data = await hazard_pipeline.run(input_data)
    return result_data["output"]
```

---

## 3. Step 0: Asset Fetch (FIX v3.2 — Gap S)

```python
# src/workflows/steps/asset_fetch.py
"""
Step 0: Fetch buildings + create BuildingAdjustedSurface per building.
"""
import asyncio
from typing import Dict, Any
from src.core.models import BuildingAdjustedSurface
from src.data.open_buildings import OpenBuildingsSource
from src.data.elevation import get_elevation

async def fetch_buildings_step(data: Dict[str, Any]) -> Dict[str, Any]:
    # ... implementation details (fetch from PostGIS/Overture) ...
    # ... Create BuildingAdjustedSurface for each building ...
    
    data["building_cluster"] = cluster
    data["building_surfaces"] = building_surfaces
    return data
```

---

## 4. Step 1: Chronic Hazards (FIX v3.2 — Gap L, S)

```python
# src/workflows/steps/chronic_hazards.py
"""
Step 1: Chronic hazards — subsidence + urban heat (parallel).
"""
import asyncio
from typing import Dict, Any
from src.tools.subsidence_tools import assess_subsidence
from src.tools.urban_heat_tools import assess_urban_heat

async def assess_chronic_hazards_step(data: Dict[str, Any]) -> Dict[str, Any]:
    # ...
    # Run assessments in parallel
    results = await asyncio.gather(subsidence_task, heat_task)
    
    # Store results
    data["chronic_results"] = { ... }
    data["adjusted_surface"] = surface # Tile level
    
    # Populate per-building surfaces with subsidence (Gap S)
    for bid, b_surf in data["building_surfaces"].items():
        b_surf.apply_subsidence(...)
        
    return data
```

---

## 5. Step 2: Cyclone Assessment (FIX v3.2 — Gap P)

```python
# src/workflows/steps/cyclone_step.py
"""
Step 2: Cyclone assessment — exports CycloneEventParams for storm surge.
"""
from typing import Dict, Any
from src.tools.cyclone_tools import assess_cyclone

async def assess_cyclone_step(data: Dict[str, Any]) -> Dict[str, Any]:
    # ...
    cyclone_result = await assess_cyclone(...)
    data["cyclone_result"] = cyclone_result
    data["cyclone_params"] = cyclone_result.intermediate["cyclone_params"]
    return data
```

---

## 6. Step 3: Acute Hazards (FIX v3.2 — Gap J, K, M, Q)

```python
# src/workflows/steps/acute_hazards.py
"""
Step 3: Acute hazards — flood, surge, landslide, pluvial (parallel × multi-RP).
"""
import asyncio
from typing import Dict, Any
from src.tools.storm_surge_tools import assess_storm_surge
# ... other tools ...

async def assess_acute_hazards_step(data: Dict[str, Any]) -> Dict[str, Any]:
    # ...
    # Loop over return_periods (Gap Q)
    all_results = {}
    for rp in return_periods:
        # Run hazards in parallel
        results = await asyncio.gather(...)
        all_results[rp] = { ... }
        
    data["hazard_results_by_rp"] = all_results
    return data
```

---

## 7. Step 4: Structure Risk (FIX v3.2 — Gap Q, S, T)

```python
# src/workflows/steps/structure_risk.py
"""
Step 4: Apply H×E×V to each building × multiple return periods.
"""
from typing import Dict, Any
from src.tools.structure_risk_tools import assess_structure_risk

async def assess_structure_risk_step(data: Dict[str, Any]) -> Dict[str, Any]:
    # ...
    results = await assess_structure_risk(
        buildings=data["building_cluster"],
        hazard_results_by_rp=data["hazard_results_by_rp"],
        building_surfaces=data["building_surfaces"],
        country=country
    )
    
    data["structure_results"] = results
    return data
```

---

## 8. Step 5: Composite Calculation (FIX v3.2 — Gap M)

```python
# src/workflows/steps/composite.py
"""
Step 5: Composite risk calculation — weighted aggregation.
"""
from typing import Dict, Any
from src.core.models.composite import FullRiskProfile

async def calculate_composite_step(data: Dict[str, Any]) -> Dict[str, Any]:
    # ...
    # Aggregate scores (Weighted max/sum)
    # Create FullRiskProfile
    
    profile = FullRiskProfile(...)
    data["output"] = profile
    return data
```

---

## 9. Hazard Weights Configuration

(Same YAML configuration as v3.1, describing weights)

---

## 10. Portfolio Workflow (FIX v3.2)

```python
# src/workflows/portfolio_workflow.py
"""
Batch portfolio assessment.
"""
import asyncio
from src.workflows.hazard_workflow import run_hazard_assessment

async def run_portfolio_assessment(sites: list, ...) -> dict:
    # Use asyncio.Semaphore for concurrency
    async def _assess_site(site):
        return await run_hazard_assessment(...)
        
    results = await asyncio.gather(*[_assess_site(s) for s in sites])
    # Aggregate EAL
    return { ... }
```

---

## 11. Testing

```python
# tests/integration/test_workflow.py
import asyncio
from src.workflows.hazard_workflow import run_hazard_assessment

result = asyncio.run(run_hazard_assessment(
    lat=10.8, lon=106.6, city="hcmc", multi_rp=True
))
print(f"EAL: {result.portfolio_eal_usd}")
```

---

## v3.2 Gap Fix Summary

| Gap | Fix | Step(s) Affected |
|-----|-----|------------------|
| **V** | **Custom AsyncIO Pipeline** replaces Agno Workflows for deterministic execution | All |
| **J** | `city` passed to `assess_riverine_flood()` | Step 3 |
| **K** | `city` passed to `assess_coastal_flood()` | Step 3 |
| **L** | Subsidence source tracked | Step 1 |
| **M** | `assess_pluvial_flood` added | Step 3 |
| **P** | Cyclone tool uses Holland (2008) | Step 2 |
| **Q** | Multi-RP loop for EAL | Steps 3, 4 |
| **S** | `BuildingAdjustedSurface` per building | Steps 0, 1, 4 |
| **T** | `OCCUPANCY_VALUE_MULTIPLIER` application | Step 4 |

---

*EcoShield Phase 4 v3.2 | AsyncIO Pipeline Orchestration*
