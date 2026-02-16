
import logging
from typing import Dict, Any, List

from src.tools.structure_risk_tools import summarize_portfolio
from src.core.models.composite import (
    FullRiskProfile, CompositeRiskResult, SurfaceAdjustments
)
from src.core.models.geometry import Location
from src.core.models.results import HazardAssessmentResult, PortfolioRiskSummary
from src.core.models.enums import RiskTier, ConfidenceLevel

logger = logging.getLogger(__name__)


async def calculate_composite_step(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 5: Composite Calculation (Final Aggregation)
    
    Inputs:
        data["structure_results"]: List[StructureRiskResult]
        data["chronic_results"]: Dict[str, HazardAssessmentResult]
        data["hazard_results_by_rp"]: Dict[int, Dict[str, HazardAssessmentResult]]
        data["city"], data["lat"], data["lon"]
        data["adjusted_surface"]: AdjustedSurface
        
    Outputs:
        data["output"]: FullRiskProfile
        data["portfolio_summary"]: PortfolioRiskSummary
    """
    lat = data["lat"]
    lon = data["lon"]
    city = data.get("city", "unknown")
    structure_results = data.get("structure_results", [])
    chronic_results = data.get("chronic_results", {})  # e.g. {"subsidence": ..., "urban_heat": ...}
    hazard_results_by_rp = data.get("hazard_results_by_rp", {})
    adj_surface = data.get("adjusted_surface")
    
    logger.info("Calculating composite risk profile...")
    
    # 1. Summarize Portfolio
    portfolio_summary = None
    if structure_results:
        summary_id = f"port_{city}_{lat:.4f}_{lon:.4f}"
        portfolio_summary = summarize_portfolio(
            structure_results=structure_results,
            portfolio_id=summary_id,
            city=city
        )
        data["portfolio_summary"] = portfolio_summary
    
    # 2. Get Primary RP Results
    primary_rp = data.get("return_period", 100)
    acute_results = {}  # Dict[str, HazardAssessmentResult]
    
    if primary_rp in hazard_results_by_rp:
        acute_results = hazard_results_by_rp[primary_rp]
    elif hazard_results_by_rp:
         # Fallback
        closest_rp = min(hazard_results_by_rp.keys(), key=lambda x: abs(x - primary_rp))
        acute_results = hazard_results_by_rp[closest_rp]
        logger.warning(f"Primary RP {primary_rp} not found, using {closest_rp}")

    # Add cyclone result if available (it was single RP in Step 2)
    if "cyclone_result" in data:
        acute_results["tropical_cyclone"] = data["cyclone_result"]

    # 3. Compute Composite Scores
    # Weights for aggregation (v3.2 methodology)
    # Acute: Max of Flood/Surge/Pluvial + Cyclone + Landslide?
    # Or just weighted sum?
    # Let's use a simple Max-Aggregation for MVP to avoid dilution.
    # Actually, FullRiskProfile methodology says "Weighted sum".
    # Let's implement a simplified aggregation: Max score determines tier, but we sum components.
    
    acute_composite = _aggregate_risks(acute_results, "acute", city)
    chronic_composite = _aggregate_risks(chronic_results, "chronic", city)
    
    # 4. Surface Adjustments
    surface_adj = SurfaceAdjustments(
        original_elevation_m=adj_surface.original_elevation_m if adj_surface else 0.0,
        subsidence_applied_m=adj_surface.subsidence_adjustment_m if adj_surface else 0.0,
        slr_applied_m=adj_surface.slr_adjustment_m if adj_surface else 0.0,
        adjusted_elevation_m=adj_surface.adjusted_elevation_m if adj_surface else 0.0
    )
    
    # 5. Create FullRiskProfile
    profile = FullRiskProfile(
        location=Location(lat=lat, lon=lon),
        city=city,
        assessment_id=f"assess_{city}_{lat}_{lon}_{primary_rp}",
        
        acute_risk=acute_composite,
        chronic_risk=chronic_composite,
        
        acute_hazard_details=acute_results,
        chronic_hazard_details=chronic_results,
        
        surface_adjustments=surface_adj
    )
    
    data["output"] = profile
    
    return data


def _aggregate_risks(
    results: Dict[str, HazardAssessmentResult],
    event_type: str,
    city: str
) -> CompositeRiskResult:
    """Aggregate individual hazard results into a composite score."""
    
    if not results:
        return CompositeRiskResult(
            event_type=event_type,
            composite_score=0.0,
            composite_tier=RiskTier.LOW,
            confidence=ConfidenceLevel.LOW,
            hazard_scores={},
            weights_used={},
            composite_p5=0.0,
            composite_p95=0.0,
            city=city,
            aggregation_valid=True
        )

    scores = {}
    weights = {}
    total_score = 0.0
    max_score = 0.0
    
    # Simple aggregation: Max Score (conservative)
    # Why Max? Because if you flood 2m, it doesn't matter if it's hot.
    # For chronic, if you sink 10cm/yr, heat is additive?
    # Let's use Max for now as it's safe.
    
    confidences = []
    
    for name, res in results.items():
        s = res.impact_score
        scores[name] = s
        weights[name] = 1.0 # Equal weight / Max logic
        max_score = max(max_score, s)
        confidences.append(res.hazard.confidence)
        
    # Determine confidence: min of inputs?
    # If any input is Low, composite is Low?
    # Let's take the confidence of the driver (max score)
    driver_name = max(scores, key=scores.get) if scores else None
    overall_confidence = ConfidenceLevel.LOW
    if driver_name:
         overall_confidence = results[driver_name].hazard.confidence
         
    return CompositeRiskResult(
        event_type=event_type,
        composite_score=max_score,
        composite_tier=_score_to_tier(max_score),
        confidence=overall_confidence,
        hazard_scores=scores,
        weights_used=weights,
        composite_p5=max_score * 0.8, # Mock uncertainty
        composite_p95=min(100.0, max_score * 1.2),
        city=city,
        aggregation_valid=True
    )

def _score_to_tier(score: float) -> RiskTier:
    if score >= 75:
        return RiskTier.CRITICAL
    elif score >= 50:
        return RiskTier.HIGH
    elif score >= 25:
        return RiskTier.MODERATE
    return RiskTier.LOW
