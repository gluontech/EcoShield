"""
POST /v1/buildings/assess — structure-level risk assessment.

Features:
  - Per-building H×E×V at single or multiple return periods
  - Multi-RP loop in workflow
  - Per-building losses_by_return_period exposes full loss-exceedance curve
  - expected_annual_loss_usd computed via trapezoidal integration
  - pluvial_damage_ratio from pluvial flood tool
  - occupancy_class + replacement_value_source
"""

import time
from typing import List, Optional

from fastapi import APIRouter, HTTPException

from src.api.schemas.requests import BuildingAssessRequest
from src.api.schemas.responses import (
    BuildingAssessResponse, BuildingRiskItem, BuildingPortfolioSummary,
    ReturnPeriodLossItem,
)
from src.api.utils import parse_time_horizon
from src.workflows.hazard_workflow import run_hazard_assessment

router = APIRouter()


@router.post("/buildings/assess", response_model=BuildingAssessResponse)
async def assess_buildings(request: BuildingAssessRequest):
    """
    Assess structure-level risk for all buildings within a radius.

    Runs the full 6-step workflow:
      Step 0: Fetch buildings + create BuildingAdjustedSurface
      Steps 1-3: Hazard assessment (chronic → cyclone → acute × multi-RP)
      Step 4: Multi-RP H×E×V per building → trapezoidal EAL
      Step 5: Composite aggregation + portfolio EAL

    Returns per-building loss curves at each assessed return period,
    pluvial flood damage, occupancy class, and trapezoidal EAL.
    """
    start = time.monotonic()
    time_horizon_val = parse_time_horizon(request.time_horizon)

    try:
        result = await run_hazard_assessment(
            lat=request.lat,
            lon=request.lon,
            city=request.city,
            return_period=request.return_period,
            time_horizon=time_horizon_val,
            slr_scenario=request.scenario.value,
            include_buildings=True,
            building_radius_m=request.radius_m,
            multi_rp=request.multi_rp,
            return_periods=request.return_periods,
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Building data not available for this area: {e}. "
                   f"Run buildings_ingest.py --city {request.city} first.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Extract structure results from FullRiskProfile (populated by composite step)
    structure_results = result.structure_results
    portfolio_summary = result.portfolio_summary

    # Determine actual return periods assessed
    rps_assessed = None
    if request.multi_rp:
        from src.core.models import STANDARD_RETURN_PERIODS
        rps_assessed = request.return_periods or STANDARD_RETURN_PERIODS

    # Build response items (cap at max_buildings)
    building_items = []
    for sr in structure_results[:request.max_buildings]:
        # Build per-building loss-exceedance curve
        rp_losses: Optional[List[ReturnPeriodLossItem]] = None
        raw_losses = getattr(sr, "losses_by_return_period", None)
        if raw_losses:
            rp_losses = [
                ReturnPeriodLossItem(
                    return_period=rpl.return_period_years,
                    annual_exceedance_probability=round(1.0 / rpl.return_period_years, 6),
                    flood_damage_ratio=rpl.damage_ratio,
                    wind_damage_ratio=None,
                    pluvial_damage_ratio=None,
                    max_damage_ratio=rpl.damage_ratio,
                    estimated_loss_usd=rpl.loss_usd,
                )
                for rpl in raw_losses
            ]

        building_items.append(BuildingRiskItem(
            building_id=sr.building_id,
            latitude=sr.latitude,
            longitude=sr.longitude,
            footprint_area_m2=sr.footprint_area_m2,
            vulnerability_class=sr.vulnerability_class.value,
            occupancy_class=getattr(sr, "occupancy_class", None),
            flood_damage_ratio=sr.flood_damage_ratio,
            flood_depth_at_building_m=sr.flood_depth_at_building_m,
            pluvial_damage_ratio=getattr(sr, "pluvial_damage_ratio", None),
            wind_damage_ratio=getattr(sr, "wind_damage_ratio", None),
            max_damage_ratio=sr.max_damage_ratio,
            risk_score=sr.combined_risk_score,
            risk_tier=sr.risk_tier.value,
            replacement_value_usd=sr.replacement_value_usd,
            replacement_value_source=getattr(
                sr, "replacement_value_source", None
            ),
            expected_annual_loss_usd=sr.expected_annual_loss_usd,
            losses_by_return_period=rp_losses,
        ))

    # Build portfolio summary
    # getattr(portfolio_summary, ...) is safe
    ps = BuildingPortfolioSummary(
        total_buildings=portfolio_summary.total_buildings if portfolio_summary else 0,
        buildings_by_tier={
            "critical": portfolio_summary.buildings_critical if portfolio_summary else 0,
            "high": portfolio_summary.buildings_high if portfolio_summary else 0,
            "moderate": portfolio_summary.buildings_moderate if portfolio_summary else 0,
            "low": portfolio_summary.buildings_low if portfolio_summary else 0,
        },
        total_replacement_value_usd=getattr(
            portfolio_summary, "total_replacement_value_usd", 0
        ),
        total_expected_annual_loss_usd=getattr(
            portfolio_summary, "total_expected_annual_loss_usd", 0
        ),
        portfolio_eal_usd=getattr(
            portfolio_summary, "total_expected_annual_loss_usd", None
        ),
        mean_damage_ratio=getattr(portfolio_summary, "mean_damage_ratio", 0),
        pml_250yr_usd=getattr(portfolio_summary, "pml_250yr_usd", None),
    )

    return BuildingAssessResponse(
        center={"lat": request.lat, "lon": request.lon},
        radius_m=request.radius_m,
        city=request.city,
        scenario=request.scenario.value,
        return_period=request.return_period,
        multi_rp=request.multi_rp,
        return_periods_assessed=rps_assessed,
        n_buildings=len(building_items),
        buildings=building_items,
        portfolio_summary=ps,
        data_sources=[
            "Google Open Buildings V3", "Google Open Buildings 2.5D Temporal",
            "Overture Maps Buildings", "JRC Global Flood Depth-Damage Functions",
            "Copernicus GLO-30 DEM", "GloFAS v4", "NEX-GDDP-CMIP6",
            "IPCC AR6 SLR Projections",
            "IBTrACS v04r01 + Holland (2008)",
        ],
        processing_time_ms=elapsed_ms,
    )
