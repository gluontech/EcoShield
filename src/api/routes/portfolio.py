# src/api/routes/portfolio.py
"""POST /v1/portfolio — batch portfolio analysis."""

import asyncio
import time

from fastapi import APIRouter, HTTPException

from src.api.schemas.requests import PortfolioRequest
from src.api.schemas.responses import PortfolioResponse, PortfolioSiteResult
from src.api.utils import score_to_category
from src.workflows.hazard_workflow import run_hazard_assessment

router = APIRouter()


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

    async def _assess_one(site):
        async with semaphore:
            try:
                result = await run_hazard_assessment(
                    lat=site.location.lat,
                    lon=site.location.lon,
                    city=site.city,
                    slr_scenario=request.scenario.value,
                    time_horizon=request.time_horizon.midpoint,
                    return_period=request.return_periods[0],
                    multi_rp=len(request.return_periods) > 1,
                    return_periods=request.return_periods,
                    structure_category=site.structure.category if site.structure else None,
                    structure_type=site.structure.type if site.structure else None,
                    roof_type=site.structure.roof_type if site.structure else None,
                    wall_material=site.structure.wall_material if site.structure else None,
                    ground_floor_height_m=site.structure.ground_floor_height_m if site.structure else None,
                    num_floors=site.structure.num_floors if site.structure else None,
                )
            except Exception:
                return PortfolioSiteResult(
                    location={
                        "lat": site.location.lat,
                        "lon": site.location.lon,
                        "name": site.structure.name if site.structure else None,
                    },
                    overall_risk_score=0.0,
                    overall_risk_category="Error",
                    hazard_scores={},
                    asset_value_usd=site.asset_value_usd,
                    expected_annual_loss_usd=None,
                    portfolio_eal_usd=None,
                )

            result_dict = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
            # FullRiskProfile stores hazards under acute_hazard_details and chronic_hazard_details
            chronic = result_dict.get("chronic_hazard_details", {})
            acute = result_dict.get("acute_hazard_details", {})
            hazards_data = {**chronic, **acute}

            # Calculate scores (normalize 0-100 -> 0-1)
            hazard_scores = {}
            for h, r in hazards_data.items():
                val = r.get("impact_score", 0.0)
                hazard_scores[h] = val / 100.0 if val > 1 else val

            overall = sum(hazard_scores.values()) / max(len(hazard_scores), 1)

            # Use multi-RP trapezoidal EAL from workflow if available;
            # fall back to simplified estimate
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
                    "name": site.structure.name if site.structure else None,
                },
                overall_risk_score=round(overall, 3),
                overall_risk_category=score_to_category(overall),
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

    return PortfolioResponse(
        n_sites=len(results),
        scenario=request.scenario.value,
        time_horizon=str(request.time_horizon),
        multi_rp=len(request.return_periods) > 1,
        return_periods_assessed=request.return_periods,
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
