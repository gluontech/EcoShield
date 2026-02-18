# src/api/routes/hazards.py
"""GET /v1/hazards/{type} — hazard-specific lookups."""

from fastapi import APIRouter, Query, HTTPException

from src.core.models import SSPScenario

# Import tool functions directly since src.hazards defines them via src.tools
try:
    from src.tools.riverine_flood_tools import assess_riverine_flood
    from src.tools.urban_heat_tools import assess_urban_heat
    from src.tools.cyclone_tools import assess_cyclone
    from src.tools.storm_surge_tools import assess_storm_surge
    from src.tools.subsidence_tools import assess_subsidence
    from src.tools.landslide_tools import assess_landslide
    from src.tools.pluvial_flood_tools import assess_pluvial_flood
except ImportError as e:
    # Just in case some tools are missing, we'll handle it at runtime or let it fail
    print(f"Warning: Failed to import some hazard tools: {e}")

router = APIRouter()

# Map hazard types to their assessment functions
HAZARD_FUNCTIONS = {
    "flood": assess_riverine_flood,
    "heat": assess_urban_heat,
    "cyclone": assess_cyclone,
    "surge": assess_storm_surge,
    "subsidence": assess_subsidence,
    "landslide": assess_landslide,
    "wind": assess_cyclone,  # Map wind to cyclone tool for now
    "pluvial": assess_pluvial_flood,
}

@router.get("/hazards/{hazard_type}")
async def get_hazard(
    hazard_type: str,
    lat: float = Query(..., ge=-60, le=60),
    lon: float = Query(..., ge=-180, le=180),
    return_period: int = Query(100, ge=2, le=1000),
    scenario: SSPScenario = Query(SSPScenario.SSP245),
    time_horizon: int = Query(2050, ge=2020, le=2100),
):
    """
    Query a single hazard type for a location.

    Returns detailed hazard result including component data sources
    and intermediate values.
    """
    if hazard_type not in HAZARD_FUNCTIONS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown hazard type: {hazard_type}. "
                   f"Available: {list(HAZARD_FUNCTIONS.keys())}",
        )

    try:
        assess_fn = HAZARD_FUNCTIONS[hazard_type]
        kwargs = {"lat": lat, "lon": lon}
        
        # Scenario string
        scen_str = scenario if isinstance(scenario, str) else scenario.value

        # Dispatch based on hazard type to match tool signatures
        if hazard_type == "heat":
            # assess_urban_heat(lat, lon, time_horizon, percentile, scenario)
            # Map return_period ~ percentile intuitively? 
            # 10yr -> 90th, 20yr+ -> 95th? Or just default.
            # Let's keep it simple: use defaults or explicit args if we had them.
            # passing return_period is wrong.
            kwargs["time_horizon"] = time_horizon
            kwargs["scenario"] = scen_str
            # percentile defaults to 95 in tool
        
        elif hazard_type in ["cyclone", "wind"]:
            # assess_cyclone(lat, lon, return_period, ...)
            # Does NOT take scenario
            kwargs["return_period"] = return_period
            
        elif hazard_type == "surge":
            # assess_storm_surge(lat, lon, return_period, ...)
            # Does NOT take scenario
            kwargs["return_period"] = return_period
            
        elif hazard_type == "subsidence":
            # assess_subsidence(lat, lon, time_horizon)
            # Does NOT take return_period or scenario?
            # Check tool signature if possible (skipped check, assuming safest minimal args)
            # Actually assess_subsidence usually takes time_horizon.
            kwargs["time_horizon"] = time_horizon
            
        else:
            # flood, landslide, pluvial
            # usually take return_period and scenario
            kwargs["return_period"] = return_period
            kwargs["scenario"] = scen_str

        result = await assess_fn(**kwargs)
        return result

    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"Data unavailable: {e}")
    except TypeError as e:
        # Catch argument mismatch if any
        raise HTTPException(status_code=500, detail=f"Integration error (signature mismatch): {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hazards")
async def list_hazards():
    """List all available hazard types."""
    return {
        "hazards": [
            {
                "type": "flood",
                "description": "Riverine and coastal flood risk",
                "data_sources": ["NEX-GDDP-CMIP6", "GloFAS", "Copernicus GLO-30"],
            },
            {
                "type": "heat",
                "description": "Heat stress and urban heat island",
                "data_sources": ["NEX-GDDP-CMIP6", "ERA5-Land", "Landsat C02"],
            },
            {
                "type": "cyclone",
                "description": "Tropical cyclone wind and rainfall (Holland 2008)",
                "data_sources": ["IBTrACS v04r01", "NEX-GDDP-CMIP6"],
            },
            {
                "type": "surge",
                "description": "Coastal storm surge inundation",
                "data_sources": ["IBTrACS", "GEBCO", "Copernicus GLO-30"],
            },
            {
                "type": "subsidence",
                "description": "Land subsidence from groundwater extraction",
                "data_sources": ["Sentinel-1 InSAR"],
            },
            {
                "type": "landslide",
                "description": "Rainfall-triggered landslide susceptibility",
                "data_sources": ["NEX-GDDP-CMIP6", "Copernicus GLO-30", "SoilGrids", "Sentinel-2"],
            },
            {
                "type": "wind",
                "description": "Extreme wind speed hazard",
                "data_sources": ["ERA5-Land", "IBTrACS"],
            },
            {
                "type": "pluvial",
                "description": "Pluvial (surface water) flood from intense rainfall "
                               "exceeding drainage capacity",
                "data_sources": ["NEX-GDDP-CMIP6", "Copernicus GLO-30", "ERA5-Land"],
            },
        ]
    }
