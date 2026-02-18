
import asyncio
import logging
from typing import Dict, Any, List

from src.core.models import (
    HazardType, HazardAssessmentResult, HazardIntensity, 
    HazardEventContext, ConfidenceLevel, RiskTier, DataSource
)
from src.core.models.exposure import ExposureProfile
from src.core.models.asset import StructuralCharacteristics, BuildingFootprint
from src.core.models.geometry import Location
from src.tools.storm_surge_tools import assess_storm_surge
from src.tools.coastal_flood_tools import assess_coastal_flood
from src.tools.riverine_flood_tools import assess_riverine_flood
from src.tools.pluvial_flood_tools import assess_pluvial_flood
from src.tools.landslide_tools import assess_landslide
from src.core.models.surface import AdjustedSurface

logger = logging.getLogger(__name__)


async def assess_acute_hazards_step(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 3: Acute Hazards (Parallel × Multi-RP — Gap Q)
    
    Inputs:
        data["lat"], data["lon"]
        data["return_periods"]: List[int] (v3.2)
        data["cyclone_params"]: Dict (from Step 2)
        data["adjusted_surface"]: AdjustedSurface (from Step 1)
        data["scenario"]: str
        data["city"]: str
        
    Outputs:
        data["hazard_results_by_rp"]: Dict[int, Dict[str, HazardAssessmentResult]]
        # e.g. {100: {"storm_surge": ..., "riverine_flood": ...}, 10: {...}}
    """
    lat = data["lat"]
    lon = data["lon"]
    rps = data.get("return_periods", [100])
    scenario = data.get("slr_scenario", "ssp245")
    city = data.get("city", "hcmc")
    horizon = data.get("time_horizon", 2050)
    
    cyclone_params = data.get("cyclone_params", {})
    surface = data.get("adjusted_surface")
    
    logger.info(f"Assessing acute hazards for RPs: {rps}")
    
    all_results = {}
    
    # We can run all RPs in parallel, but that might be 5 hazards * 9 RPs = 45 tasks.
    # That's fine for asyncio.
    
    async def _assess_rp(rp: int) -> tuple[int, Dict[str, Any]]:
        # Determine active hazards from config (M2)
        active_hazards = data.get("hazard_config", {}).get("acute", [])
        
        # Map active hazards to assessment functions and HazardType keys
        # This keeps the order consistent
        task_map = []
        
        if "storm_surge" in active_hazards:
            task_map.append((
                HazardType.STORM_SURGE.value,
                assess_storm_surge(
                    lat=lat, lon=lon, cyclone_params=cyclone_params, 
                    surface=surface, return_period=rp
                )
            ))
            
        if "coastal_flood" in active_hazards:
            task_map.append((
                HazardType.COASTAL_FLOOD.value,
                assess_coastal_flood(
                    lat=lat, lon=lon, time_horizon=horizon, 
                    scenario=scenario, surface=surface, city=city, return_period=rp
                )
            ))
            
        if "riverine_flood" in active_hazards:
            task_map.append((
                HazardType.RIVERINE_FLOOD.value,
                assess_riverine_flood(
                    lat=lat, lon=lon, return_period=rp, 
                    surface=surface, city=city
                )
            ))
            
        if "pluvial_flood" in active_hazards:
            task_map.append((
                HazardType.PLUVIAL_FLOOD.value,
                assess_pluvial_flood(
                    lat=lat, lon=lon, return_period=rp, 
                    scenario=scenario
                )
            ))
            
        if "landslide" in active_hazards:
            task_map.append((
                HazardType.LANDSLIDE.value,
                assess_landslide(
                    lat=lat, lon=lon, return_period=rp, 
                    scenario=scenario
                )
            ))
            
        if not task_map:
            return rp, {}

        # Extract tasks
        keys = [item[0] for item in task_map]
        tasks = [item[1] for item in task_map]
        
        # Gather results for this RP
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        rp_map = {}
        
        for k, res in zip(keys, results):
            if isinstance(res, Exception):
                logger.error(f"Hazard {k} (RP={rp}) failed: {res}")
                # Fallback for failed hazard
                rp_map[k] = HazardAssessmentResult(
                    hazard=HazardIntensity(
                        hazard_type=HazardType(k),
                        event_context=HazardEventContext(
                            event_type="acute", 
                            return_period_years=rp
                        ),
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
                                source=DataSource.GOOGLE_OPEN_BUILDINGS_V3,
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
                rp_map[k] = res
                
        return rp, rp_map

    # Launch all RP tasks
    rp_tasks = [_assess_rp(rp) for rp in rps]
    rp_results_list = await asyncio.gather(*rp_tasks)
    
    for rp, res_map in rp_results_list:
        all_results[rp] = res_map
        
    data["hazard_results_by_rp"] = all_results
    
    return data
