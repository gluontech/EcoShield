"""
Main hazard assessment workflow using the AsyncIO Pipeline.

Execution Order (hard dependencies) — v3.2: 6 steps, 8 hazards, multi-RP:
  Step 0 — Asset Fetch: Load buildings + create BuildingAdjustedSurface (Gap S)
  Step 1 — Chronic Hazards (Parallel): Subsidence (+ published fallback, Gap L) + Urban Heat
  Step 2 — Cyclone Assessment (Holland 2008 — Gap P)
  Step 3 — Acute Hazards (Parallel × Multi-RP — Gap Q)
  Step 4 — Structure Risk (v3.2: multi-RP EAL)
  Step 5 — Composite Calculation
"""

from src.core.models import FullRiskProfile, STANDARD_RETURN_PERIODS
from src.config.city_hazards import CITY_HAZARDS
from src.workflows.pipeline import Pipeline, PipelineStep
from src.workflows.steps.asset_fetch import fetch_buildings_step
from src.workflows.steps.chronic_hazards import assess_chronic_hazards_step
from src.workflows.steps.cyclone_step import assess_cyclone_step
from src.workflows.steps.acute_hazards import assess_acute_hazards_step
from src.workflows.steps.structure_risk import assess_structure_risk_step
from src.workflows.steps.composite import calculate_composite_step


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
                description="Chronic: subsidence (InSAR + published fallback) + urban heat"
            ),
            PipelineStep(
                name="cyclone_assessment",
                executor=assess_cyclone_step,
                description="Cyclone: IBTrACS + Holland (2008) → CycloneEventParams"
            ),
            PipelineStep(
                name="acute_hazards",
                executor=assess_acute_hazards_step,
                description="Acute: flood + surge + landslide + pluvial × multi-RP [2-1000yr]"
            ),
            PipelineStep(
                name="structure_risk",
                executor=assess_structure_risk_step,
                description="Structure H×E×V: multi-RP EAL via trapezoidal integration (v3.2)"
            ),
            PipelineStep(
                name="composite",
                executor=calculate_composite_step,
                description="Composite: weighted risk scores → FullRiskProfile + PortfolioEAL"
            ),
        ]
    )


# Singleton pipeline instance
hazard_pipeline = create_hazard_assessment_pipeline()


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
    Run full multi-hazard assessment for a single location using the async pipeline.

    This is the main entry point called by the API layer (Phase 5).
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

    # Execute the pipeline
    # The pipeline returns the full context dict; we extract the final 'output'
    # which is the FullRiskProfile created in Step 5.
    result_context = await hazard_pipeline.run(input_data)
    
    if "output" not in result_context:
        raise RuntimeError("Pipeline completed but no 'output' (FullRiskProfile) was produced.")
        
    return result_context["output"]
