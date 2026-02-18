# src/api/routes/portfolio.py
"""POST /v1/portfolio — batch portfolio analysis."""

import asyncio
import time

from fastapi import APIRouter, HTTPException

from src.api.schemas.requests import PortfolioRequest
from src.api.schemas.responses import PortfolioResponse, PortfolioSiteResult
from src.workflows.hazard_workflow import run_hazard_assessment

router = APIRouter()


def _score_to_category(score: float) -> str:
    if score < 0.2:
        return "Low"
    elif score < 0.4:
        return "Moderate"
    elif score < 0.6:
        return "High"
    elif score < 0.8:
        return "Very High"
    return "Extreme"


@router.post("/portfolio", response_model=PortfolioResponse)
async def assess_portfolio(request: PortfolioRequest):
    """
    Run hazard assessment across a portfolio of sites.

    Sites are assessed in parallel (up to 10 concurrently).

    When multi_rp=True, each site runs multi-RP assessment and
    returns trapezoidal EAL (portfolio_eal_usd) instead of simplified
    risk_score × asset_value estimate.
    """
    start = time.monotonic()
    semaphore = asyncio.Semaphore(10)

    # Time horizon parsing
    try:
         if "-" in request.time_horizon:
             parts = request.time_horizon.split("-")
             avg_year = int((int(parts[0]) + int(parts[1])) / 2)
             time_horizon_val = avg_year
         else:
             time_horizon_val = int(request.time_horizon) 
    except ValueError:
         time_horizon_val = 2050

    async def _assess_one(site):
        async with semaphore:
            try:
                result = await run_hazard_assessment(
                    lat=site.location.lat,
                    lon=site.location.lon,
                    city="hcmc", # Defaulting
                    slr_scenario=request.scenario.value,
                    time_horizon=time_horizon_val,
                    return_period=request.return_period,
                    multi_rp=request.multi_rp,
                    return_periods=request.return_periods,
                )
            except Exception as e:
                return PortfolioSiteResult(
                    location={
                        "lat": site.location.lat,
                        "lon": site.location.lon,
                        "name": site.location.name,
                    },
                    overall_risk_score=0.0,
                    overall_risk_category="Error",
                    hazard_scores={},
                    asset_value_usd=site.asset_value_usd,
                    expected_annual_loss_usd=None,
                    portfolio_eal_usd=None,
                )

            result_dict = result.model_dump() if hasattr(result, "model_dump") else result
            hazards_data = result_dict.get("hazards", {})

            # Calculate scores (normalize 0-100 -> 0-1)
            hazard_scores = {}
            for h, r in hazards_data.items():
                val = r.get("impact_score", 0.0)
                hazard_scores[h] = val / 100.0 if val > 1 else val
            
            overall = sum(hazard_scores.values()) / max(len(hazard_scores), 1)

            # Use multi-RP trapezoidal EAL from workflow
            # if available; fall back to simplified estimate
            workflow_eal = result_dict.get("portfolio_eal_usd")
            
            if workflow_eal is not None:
                eal = round(workflow_eal, 2)
            elif site.asset_value_usd:
                # Fallback: simplified EAL = overall_risk × asset_value × 0.01
                eal = round(overall * site.asset_value_usd * 0.01, 2)
            else:
                eal = None

            return PortfolioSiteResult(
                location={
                    "lat": site.location.lat,
                    "lon": site.location.lon,
                    "name": site.location.name,
                },
                overall_risk_score=round(overall, 3),
                overall_risk_category=_score_to_category(overall),
                hazard_scores={k: round(v, 3) for k, v in hazard_scores.items()},
                asset_value_usd=site.asset_value_usd,
                expected_annual_loss_usd=eal,
                portfolio_eal_usd=workflow_eal,
            )

    results = await asyncio.gather(*[_assess_one(s) for s in request.sites])
    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Portfolio summary
    all_scores = [r.overall_risk_score for r in results if r.overall_risk_category != "Error"]
    total_value = sum(s.asset_value_usd or 0 for s in request.sites)
    total_eal = sum(r.expected_annual_loss_usd or 0 for r in results)
    total_portfolio_eal = sum(r.portfolio_eal_usd or 0 for r in results)

    # Determine actual return periods assessed
    rps_assessed = None
    if request.multi_rp:
        from src.core.models import STANDARD_RETURN_PERIODS
        rps_assessed = request.return_periods or STANDARD_RETURN_PERIODS

    return PortfolioResponse(
        n_sites=len(results),
        scenario=request.scenario.value,
        time_horizon=request.time_horizon,
        multi_rp=request.multi_rp,
        return_periods_assessed=rps_assessed,
        sites=results,
        portfolio_summary={
            "mean_risk_score": round(sum(all_scores) / max(len(all_scores), 1), 3),
            "max_risk_score": round(max(all_scores, default=0), 3),
            "total_asset_value_usd": total_value,
            "total_expected_annual_loss_usd": round(total_eal, 2),
            "portfolio_eal_usd": round(total_portfolio_eal, 2),
            "high_risk_sites": sum(1 for s in all_scores if s >= 0.6),
        },
        processing_time_ms=elapsed_ms,
    )
