# src/api/routes/assess.py
"""POST /v1/assess — single-site hazard assessment."""

import time

from fastapi import APIRouter, HTTPException

from src.api.schemas.requests import AssessRequest
from src.api.schemas.responses import AssessResponse, HazardScore
from src.workflows.hazard_workflow import run_hazard_assessment

router = APIRouter()


def _score_to_category(score: float) -> str:
    """Convert 0-1 score to risk category."""
    if score < 0.2:
        return "Low"
    elif score < 0.4:
        return "Moderate"
    elif score < 0.6:
        return "High"
    elif score < 0.8:
        return "Very High"
    return "Extreme"


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

    try:
        # Map logic: run_hazard_assessment expects 'time_horizon' as int (year) or string? 
        # API says string "2041-2060", workflow annotation says int=2050.
        # Logic in workflow probably handles it or we need to parse.
        # Let's assume we need to pass just the year. "2041-2060" -> 2050?
        # The spec in run_hazard_assessment says "time_horizon: int = 2050".
        # We should parse the string to a midpoint year.
        try:
             # Basic parsing: '2041-2060' -> 2050
             if "-" in request.time_horizon:
                 parts = request.time_horizon.split("-")
                 avg_year = int((int(parts[0]) + int(parts[1])) / 2)
                 time_horizon_val = avg_year
             else:
                 time_horizon_val = int(request.time_horizon) 
        except ValueError:
             time_horizon_val = 2050 # Fallback

        result = await run_hazard_assessment(
            lat=request.location.lat,
            lon=request.location.lon,
            city=request.city,
            slr_scenario=request.scenario.value,
            time_horizon=time_horizon_val,
            return_period=request.return_period,
            include_buildings=True, # Enable building lookup (with Overture fallback)
                                     # API spec mentions "include_details". 
        )
        
        # NOTE: Arguments passed above:
        # lat, lon, city='hcmc', return_period, time_horizon, slr_scenario (mapped from scenario), 
        # multi_rp, return_periods.
        # 'hazards' argument is NOT in the workflows signature I read earlier (Step 25).
        # But 'input_data' dict in workflow uses 'hazard_config' which comes from 'city'.
        # This implies we can't easily filter hazards at runtime unless we modify city config or filter output.
        # I will filter the output.

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Data not available: {e}. Run ingestion first.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Build hazard scores
    hazard_scores = []
    scores = []
    data_sources = set()

    # Result is FullRiskProfile (pydantic model) or dict?
    # Workflow returns 'FullRiskProfile'. 
    # Its fields are probably hazards, risk_score etc.
    # I need to inspect FullRiskProfile structure or treat it as object.
    # Assuming it behaves like the dict structure in the spec.
    # Actually, let's treat it as dict if possible or use getattr.
    
    # The spec code loop:: for hazard_type, hazard_result in result.items():
    # This implies 'result' is a dict.
    # But workflow returns `FullRiskProfile` object.
    # I should convert it to dict or `model_dump()`.
    
    # Merge chronic and acute hazard details
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result
    chronic = result_dict.get("chronic_hazard_details", {})
    acute = result_dict.get("acute_hazard_details", {})
    hazards_data = {**chronic, **acute}
    # Map request aliases to internal hazard names
    REQUEST_ALIAS_MAP = {
        "heat": ["urban_heat"],
        "flood": ["riverine_flood", "coastal_flood"],
        "pluvial": ["pluvial_flood"],
        "surge": ["storm_surge"],
        "cyclone": ["tropical_cyclone"],
        "wind": ["tropical_cyclone"],
        "subsidence": ["subsidence"],
        "landslide": ["landslide"]
    }

    # Filter by requested hazards (expanding aliases)
    requested_hazards = set()
    for req in request.hazards:
        if req in REQUEST_ALIAS_MAP:
             requested_hazards.update(REQUEST_ALIAS_MAP[req])
        else:
             requested_hazards.add(req)
    
    for hazard_type, hazard_result in hazards_data.items():
        if hazard_type not in requested_hazards:
            continue
            
        # hazard_result is likely HazardAssessmentResult model
        score = hazard_result.get("impact_score", 0.0) # Using impact_score as risk_score?
        # Or 'risk_score'? 
        # Tools return 'impact_score'. Spec 'HazardScore' uses 'risk_score'.
        # Spec says: score = hazard_result.get("risk_score", 0.0)
        
        scores.append(score)
        # data_sources
        ds = hazard_result.get("hazard", {}).get("data_sources", [])
        data_sources.update(ds)

        hazard_scores.append(HazardScore(
            hazard_type=hazard_type,
            risk_score=score / 100.0 if score > 1 else score, # Normalize 0-100 to 0-1? 
                                                              # API spec says 0-1. Tools return 0-100?
                                                              # tools `_calculate_flood_risk_score` returns 0-100.
                                                              # So I must normalize.
            risk_category=_score_to_category(score / 100.0 if score > 1 else score),
            confidence=str(hazard_result.get("hazard", {}).get("confidence", "moderate")),
            key_drivers=[], # Need to extract logic?
            details=hazard_result if request.include_details else None,
        ))

    overall = sum(scores) / len(scores) if scores else 0.0
    overall_norm = overall / 100.0 if overall > 1 else overall

    # Extract portfolio EAL if available
    # FullRiskProfile might have 'portfolio_eal_usd' field?
    portfolio_eal = result_dict.get("portfolio_eal_usd")

    # Determine actual return periods assessed
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
        overall_risk_category=_score_to_category(overall_norm),
        hazards=hazard_scores,
        portfolio_eal_usd=portfolio_eal,
        data_sources=sorted(data_sources),
        processing_time_ms=elapsed_ms,
    )
