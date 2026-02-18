
import logging
import asyncio
from typing import Dict, Any
from datetime import datetime

from src.tools.subsidence_tools import assess_subsidence
from src.tools.urban_heat_tools import assess_urban_heat
from src.core.models.surface import AdjustedSurface
from src.core.models import (
    HazardAssessmentResult, HazardIntensity, HazardEventContext,
    HazardType, ConfidenceLevel, RiskTier, DataSource
)
from src.core.models.exposure import ExposureProfile
from src.core.models.asset import StructuralCharacteristics, BuildingFootprint
from src.core.models.geometry import Location

logger = logging.getLogger(__name__)


async def assess_chronic_hazards_step(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 1: Chronic Hazards (Parallel)
    
    Inputs:
        data["lat"]: float
        data["lon"]: float
        data["city"]: str
        data["time_horizon"]: int
        data["building_surfaces"]: Dict[str, BuildingAdjustedSurface] (from Step 0)
        
    Outputs:
        data["chronic_results"]: Dict[str, HazardAssessmentResult]
        data["adjusted_surface"]: AdjustedSurface (tile-level)
        data["building_surfaces"]: Updated with subsidence rates
    """
    lat = data["lat"]
    lon = data["lon"]
    city = data.get("city", "hcmc")
    horizon = data.get("time_horizon", 2050)
    
    logger.info(f"Assessing chronic hazards for {city}...")
    
    
    chronic_config = data.get("hazard_config", {}).get("chronic", [])
    
    # Run assessments in parallel if enabled
    tasks = []
    task_names = []
    
    if "subsidence" in chronic_config:
        tasks.append(assess_subsidence(
            lat=lat, lon=lon, city=city, time_horizon=horizon
        ))
        task_names.append("subsidence")
    
    if "urban_heat" in chronic_config:
        tasks.append(assess_urban_heat(
            lat=lat, lon=lon, time_horizon=horizon, scenario=data.get("slr_scenario", "ssp245")
        ))
        task_names.append("urban_heat")
        
    if not tasks:
        logger.info("No chronic hazards enabled for this city.")
        results = []
    else:
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    chronic_results = {}
    subsidence_result = None
    
    for i, name in enumerate(task_names):
        res = results[i]
        if isinstance(res, Exception):
            logger.error(f"{name} assessment failed: {res}")
            # Create failed result so it appears in output
            chronic_results[name] = HazardAssessmentResult(
                hazard=HazardIntensity(
                    hazard_type=HazardType(name),
                    event_context=HazardEventContext(event_type="chronic", return_period_years=1),
                    intensity_value=0.0,
                    intensity_unit="unknown",
                    uncertainty_type="failed",
                    native_resolution_m=30,
                    effective_resolution_m=30,
                    confidence=ConfidenceLevel.LOW,
                    limitations=[f"Assessment failed: {str(res)}"]
                ),
                exposure=ExposureProfile(
                    location=Location(lat=lat, lon=lon),
                    elevation_m=0.0,
                    structure=StructuralCharacteristics(
                        footprint=BuildingFootprint(
                            building_id="fallback",
                            source=DataSource.GOOGLE_OPEN_BUILDINGS_V3, # generic
                            centroid=Location(lat=lat, lon=lon),
                            area_m2=100.0
                        )
                    )
                ),
                intermediate={},
                impact_score=0.0,
                impact_tier=RiskTier.LOW,
                can_aggregate_with=[],
                dependency_order=1
            )
        else:
            chronic_results[name] = res
            if name == "subsidence":
                subsidence_result = res
                
    data["chronic_results"] = chronic_results
    
    # ── Update Surfaces (Gap S) ──
    
    # 1. Tile-level AdjustedSurface (for acute hazards if they use it)
    base_elev = 0.0
    if subsidence_result:
        base_elev = subsidence_result.intermediate.get("original_elevation_m", 0.0)
        cumulative_m = subsidence_result.intermediate.get("cumulative_m", 0.0)
        
        adj_surface = AdjustedSurface(
            original_elevation_m=base_elev,
            subsidence_adjustment_m=cumulative_m
        )
        # Mark as applied since we initialized it with the value
        # But AdjustedSurface.subsidence_adjustment_m is a field. 
        # We need to call applySubsidence to set the _subsidence_applied flag if needed?
        # Actually AdjustedSurface logic is: 
        #   subsidence_adjustment_m = Field(default=0.0)
        #   _subsidence_applied = PrivateAttr(default=False)
        # If we just set the field in constructor, _subsidence_applied is False.
        # But acute hazards might check .subsidenceApplied.
        # Let's force it or use the method.
        adj_surface = AdjustedSurface(original_elevation_m=base_elev)
        adj_surface.applySubsidence(cumulative_m)
        
        data["adjusted_surface"] = adj_surface
        
        # 2. Per-building surfaces (Gap S)
        # Apply the tile-level subsidence rate to all buildings
        # (Unless we had per-building InSAR distinct points, but the tool provides a single point result for lat/lon)
        # A refinement would be to sample InSAR grid at each building, but currently assess_subsidence returns 
        # a single HazardAssessmentResult for the center point.
        # So we apply the center point rate to all buildings in the cluster (valid for 500m radius).
        
        rate_mm_yr = subsidence_result.intermediate.get("velocity_mm_yr", 0.0)
        source = subsidence_result.intermediate.get("subsidence_source", "none")
        current_year = datetime.now().year
        years = max(0, horizon - current_year)
        
        building_surfaces = data.get("building_surfaces", {})
        for bid, surf in building_surfaces.items():
            if not surf.subsidence_applied:
                surf.apply_subsidence(rate_mm_yr, horizon_years=years)
                # Also track source
                surf.subsidence_source = source
                
    else:
        # If failure, create dummy surface
        from src.data.elevation import get_elevation
        elev = await get_elevation(lat, lon)
        data["adjusted_surface"] = AdjustedSurface(original_elevation_m=elev)

    return data
