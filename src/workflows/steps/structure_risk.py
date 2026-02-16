
import logging
from typing import Dict, Any

from src.tools.structure_risk_tools import assess_structure_risk
from src.core.models.asset import BuildingCluster

logger = logging.getLogger(__name__)


async def assess_structure_risk_step(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 4: Structure Risk (v3.2: multi-RP EAL via trapezoidal integration)
    
    Inputs:
        data["building_cluster"]: BuildingCluster (from Step 0)
        data["hazard_results_by_rp"]: Dict (from Step 3)
        data["building_surfaces"]: Dict (from Step 0/1)
        data["city"]: str
        
    Outputs:
        data["structure_results"]: List[StructureRiskResult]
    """
    cluster = data.get("building_cluster")
    hazard_results_by_rp = data.get("hazard_results_by_rp", {})
    building_surfaces = data.get("building_surfaces", {})
    city = data.get("city", "hcmc")
    
    # If no buildings found (Step 0 skipped or empty), return empty list
    # But check if cluster is None or empty
    if not cluster or not cluster.buildings:
        logger.info("No buildings to assess (cluster empty).")
        data["structure_results"] = []
        return data
        
    logger.info(f"Assessing risk for {len(cluster.buildings)} buildings in {city}...")
    
    # Map city to country for JRC
    country_map = {
        "hcmc": "VN", "hanoi": "VN", "danang": "VN",
        "jakarta": "ID", "bandung": "ID", "surabaya": "ID",
        "manila": "PH", "cebu": "PH", "davao": "PH",
        "bangkok": "TH", "phuket": "TH",
        "singapore": "SG",
    }
    country = country_map.get(city, "VN")
    
    # Execute HxExV assessment
    results = await assess_structure_risk(
        buildings=cluster,
        hazard_results_by_rp=hazard_results_by_rp,
        building_surfaces=building_surfaces,
        country=country
    )
    
    data["structure_results"] = results
    
    return data
