
import logging
from typing import Dict, Any

from src.tools.cyclone_tools import assess_cyclone

logger = logging.getLogger(__name__)


async def assess_cyclone_step(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 2: Cyclone Assessment (Holland 2008 — Gap P)
    
    Inputs:
        data["lat"]: float
        data["lon"]: float
        data["return_period"]: int (primary RP for single-value display)
        
    Outputs:
        data["cyclone_result"]: HazardAssessmentResult
        data["cyclone_params"]: Dict (intermediate params for storm surge)
    """
    lat = data["lat"]
    lon = data["lon"]
    rp = data.get("return_period", 100)
    
    logger.info(f"Assessing cyclone hazard (RP={rp})...")
    
    # Assess cyclone hazard
    cyclone_result = await assess_cyclone(
        lat=lat, lon=lon, return_period=rp,
        region="southeast_asia" # Could be dynamic based on city, but defaults to SEA
    )
    
    data["cyclone_result"] = cyclone_result
    
    # Extract params for storm surge tool (Step 3)
    # The tool returns 'intermediate' dict with 'cyclone_params'
    if cyclone_result.intermediate and "cyclone_params" in cyclone_result.intermediate:
        data["cyclone_params"] = cyclone_result.intermediate["cyclone_params"]
    else:
        # Fallback if intermediate missing (shouldn't happen with current tool)
        data["cyclone_params"] = {}
        
    return data
