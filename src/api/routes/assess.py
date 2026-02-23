# src/api/routes/assess.py
"""POST /v1/assess — single-site hazard assessment."""

import time

from fastapi import APIRouter, HTTPException

from src.api.schemas.requests import AssessRequest
from src.api.schemas.responses import AssessResponse, HazardScore
from src.api.utils import parse_time_horizon, score_to_category
from src.workflows.hazard_workflow import run_hazard_assessment

router = APIRouter()

# Map request hazard aliases to internal hazard names used in FullRiskProfile
_REQUEST_ALIAS_MAP = {
    "heat": ["urban_heat"],
    "flood": ["riverine_flood", "coastal_flood"],
    "pluvial": ["pluvial_flood"],
    "surge": ["storm_surge"],
    "cyclone": ["tropical_cyclone"],
    "wind": ["tropical_cyclone"],
    "subsidence": ["subsidence"],
    "landslide": ["landslide"],
}


@router.post("/assess", response_model=AssessResponse)
async def assess_site(request: AssessRequest):
    """
    Perform multi-hazard climate risk assessment for a single location.

    Runs requested hazard modules in parallel and returns normalised
    risk scores with confidence levels and key drivers.

    When multi_rp=True, runs assessment at multiple return periods
    [10, 25, 50, 100, 250] (or custom return_periods) and computes
    trapezoidal EAL. Pluvial flood is now a valid hazard type.
    """
    start = time.monotonic()
    time_horizon_val = parse_time_horizon(request.time_horizon)

    try:
        result = await run_hazard_assessment(
            lat=request.location.lat,
            lon=request.location.lon,
            city=request.city,
            slr_scenario=request.scenario.value,
            time_horizon=time_horizon_val,
            return_period=request.return_period,
            include_buildings=True,
            multi_rp=request.multi_rp,
            return_periods=request.return_periods,
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Data not available: {e}. Run ingestion first.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Merge chronic and acute hazard details from FullRiskProfile
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result
    chronic = result_dict.get("chronic_hazard_details", {})
    acute = result_dict.get("acute_hazard_details", {})
    hazards_data = {**chronic, **acute}

    # Expand request hazard aliases into internal names
    requested_hazards: set = set()
    for req in request.hazards:
        requested_hazards.update(_REQUEST_ALIAS_MAP.get(req, [req]))

    hazard_scores = []
    scores = []
    data_sources: set = set()

    for hazard_type, hazard_result in hazards_data.items():
        if hazard_type not in requested_hazards:
            continue

        raw_score = hazard_result.get("impact_score", 0.0)
        # impact_score is 0-100; normalise to 0-1 for the API response
        norm_score = raw_score / 100.0 if raw_score > 1 else raw_score
        scores.append(raw_score)

        # Data sources live in hazard.limitations or hazard.data_sources
        # Try both paths defensively
        hazard_node = hazard_result.get("hazard", {})
        ds = hazard_node.get("data_sources", [])
        if not ds:
            ds = hazard_node.get("limitations", [])
        data_sources.update(ds)

        hazard_scores.append(HazardScore(
            hazard_type=hazard_type,
            risk_score=round(norm_score, 4),
            risk_category=score_to_category(norm_score),
            confidence=str(hazard_node.get("confidence", "moderate")),
            key_drivers=[],
            details=hazard_result if request.include_details else None,
        ))

    # Add any requested hazards that were not assessed
    assessed_hazards_set = {h.hazard_type for h in hazard_scores}
    for req_hz in requested_hazards:
        if req_hz not in assessed_hazards_set:
            hazard_scores.append(HazardScore(
                hazard_type=req_hz,
                risk_score=0.0,
                risk_category="Not Assessed",
                confidence="low",
                key_drivers=["Hazard not configured or supported for this location"],
                details=None,
            ))

    overall = sum(scores) / len(scores) if scores else 0.0
    overall_norm = overall / 100.0 if overall > 1 else overall

    portfolio_eal = result_dict.get("portfolio_eal_usd")

    rps_assessed = None
    if request.multi_rp:
        from src.core.models import STANDARD_RETURN_PERIODS
        rps_assessed = request.return_periods or STANDARD_RETURN_PERIODS

    return AssessResponse(
        location={
            "lat": request.location.lat,
            "lon": request.location.lon,
            "name": request.location.name,
        },
        scenario=request.scenario.value,
        time_horizon=request.time_horizon,
        return_period=request.return_period,
        multi_rp=request.multi_rp,
        return_periods_assessed=rps_assessed,
        overall_risk_score=round(overall_norm, 3),
        overall_risk_category=score_to_category(overall_norm),
        aggregation_method="composite_weighted_average",
        hazard_weights={"primary": 0.6, "secondary": 0.25, "tertiary": 0.15},
        hazards=hazard_scores,
        portfolio_eal_usd=portfolio_eal,
        data_sources=sorted(data_sources),
        processing_time_ms=elapsed_ms,
    )
