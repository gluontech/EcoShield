
import math
import logging
from typing import Dict, Any, List, Optional

from src.tools.structure_risk_tools import summarize_portfolio
from src.core.models.composite import (
    FullRiskProfile, CompositeRiskResult, SurfaceAdjustments
)
from src.core.models.geometry import Location
from src.core.models.results import HazardAssessmentResult, PortfolioRiskSummary
from src.core.models.asset import BuildingCluster, StructuralCharacteristics
from src.core.models.exposure import ExposureProfile
from src.core.models.enums import RiskTier, ConfidenceLevel
from src.config.hazard_weights import HAZARD_WEIGHTS, load_city_weights

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
    # Use hazard_weights.yaml (M1)
    
    city_weights = load_city_weights(city)
    acute_weights = city_weights.get("acute", {})
    chronic_weights = city_weights.get("chronic", {})
    
    acute_composite = _aggregate_risks(acute_results, "acute", city, acute_weights)
    chronic_composite = _aggregate_risks(chronic_results, "chronic", city, chronic_weights)
    
    # 4. Surface Adjustments
    surface_adj = SurfaceAdjustments(
        original_elevation_m=adj_surface.original_elevation_m if adj_surface else 0.0,
        subsidence_applied_m=adj_surface.subsidence_adjustment_m if adj_surface else 0.0,
        slr_applied_m=adj_surface.slr_adjustment_m if adj_surface else 0.0,
        adjusted_elevation_m=adj_surface.subsidence_adjusted_elevation_m if adj_surface else 0.0
    )
    
    # 4b. Inject real building data into hazard results
    building_cluster = data.get("building_cluster")
    if building_cluster and building_cluster.buildings:
        _inject_building_data(
            lat, lon, building_cluster,
            chronic_results, acute_results
        )
    
    # 5. Create FullRiskProfile
    # v3.2: Methodology tracking + Portfolio EAL (Gap Q)
    profile = FullRiskProfile(
        location=Location(lat=lat, lon=lon),
        city=city,
        assessment_id=f"assess_{city}_{lat}_{lon}_{primary_rp}",
        
        acute_risk=acute_composite,
        chronic_risk=chronic_composite,
        
        acute_hazard_details=acute_results,
        chronic_hazard_details=chronic_results,
        
        surface_adjustments=surface_adj,
        
        return_period=primary_rp,
        time_horizon=data.get("time_horizon", 2050),
        scenario=data.get("slr_scenario", "ssp245"),
        
        methodology={
            "version": "3.2",
            "orchestration": "AsyncIO Pipeline",
            "acute_aggregation": "Weighted sum (City-specific weights)",
            "chronic_aggregation": "Weighted sum (City-specific weights)",
            "composite_logic": "Separated Acute/Chronic (No cross-aggregation)"
        },
        
        portfolio_eal_usd=data.get("portfolio_summary").total_expected_annual_loss_usd if data.get("portfolio_summary") else None
    )
    
    data["output"] = profile
    
    return data


def _aggregate_risks(
    results: Dict[str, HazardAssessmentResult],
    event_type: str,
    city: str,
    weight_map: Dict[str, float]
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
    weighted_sum = 0.0
    total_weight = 0.0
    
    # Uncertainty Tracking (Fix H3/N5)
    p5_weighted_sum = 0.0
    p95_weighted_sum = 0.0
    
    confidences = []
    
    for name, res in results.items():
        s = res.impact_score
        scores[name] = s
        
        # M1: Use configured weight or default to 1.0
        w = weight_map.get(name, 1.0)
        weights[name] = w
        
        # Weighted accumulation
        weighted_sum += s * w
        total_weight += w
        
        confidences.append(res.hazard.confidence)
        
        # H3/N5: Track real uncertainty bounds
        # Use fields on result if available, else fallback to score
        p5 = res.impact_score_p5 if res.impact_score_p5 is not None else s
        p95 = res.impact_score_p95 if res.impact_score_p95 is not None else s
        
        p5_weighted_sum += p5 * w
        p95_weighted_sum += p95 * w
        
    # Compute weighted averages
    composite_score = weighted_sum / total_weight if total_weight > 0 else 0.0
    comp_p5 = p5_weighted_sum / total_weight if total_weight > 0 else 0.0
    comp_p95 = p95_weighted_sum / total_weight if total_weight > 0 else 0.0

    # Determine confidence: lowest confidence of any driver?
    # Or weighted average? Confidence is categorical.
    # Let's take the confidence of the hazard with the highest weight * score contribution?
    # Simple approach: Min confidence (conservative)
    overall_confidence = ConfidenceLevel.LOW
    if confidences:
        # Map to int, take min, map back?
        # Creating a simple map for now
        conf_map = {
            ConfidenceLevel.LOW: 1,
            ConfidenceLevel.MODERATE: 2,
            ConfidenceLevel.HIGH: 3
        }
        min_val = min(conf_map.get(c, 1) for c in confidences)
        rev_map = {1: ConfidenceLevel.LOW, 2: ConfidenceLevel.MODERATE, 3: ConfidenceLevel.HIGH}
        overall_confidence = rev_map.get(min_val, ConfidenceLevel.LOW)

    return CompositeRiskResult(
        event_type=event_type,
        composite_score=composite_score,
        composite_tier=_score_to_tier(composite_score),
        confidence=overall_confidence,
        hazard_scores=scores,
        weights_used=weights,
        composite_p5=comp_p5,
        composite_p95=comp_p95,
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


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance in meters between two lat/lon points."""
    R = 6_371_000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _find_nearest_building(
    lat: float,
    lon: float,
    cluster: BuildingCluster,
) -> Optional[StructuralCharacteristics]:
    """Return the building in *cluster* closest to (lat, lon), or None."""
    best: Optional[StructuralCharacteristics] = None
    best_dist = float("inf")
    for b in cluster.buildings:
        c = b.footprint.centroid
        d = _haversine_m(lat, lon, c.lat, c.lon)
        if d < best_dist:
            best_dist = d
            best = b
    return best


def _inject_building_data(
    lat: float,
    lon: float,
    cluster: BuildingCluster,
    chronic_results: Dict[str, HazardAssessmentResult],
    acute_results: Dict[str, HazardAssessmentResult],
) -> None:
    """Replace placeholder exposure structures with the nearest real building.

    Mutates the HazardAssessmentResult objects in-place.
    """
    nearest = _find_nearest_building(lat, lon, cluster)
    if nearest is None:
        return

    logger.info(
        "Injecting building data: id=%s source=%s area=%.1f m²",
        nearest.footprint.building_id,
        nearest.footprint.source,
        nearest.footprint.area_m2,
    )

    all_results: Dict[str, HazardAssessmentResult] = {
        **chronic_results,
        **acute_results,
    }

    for name, result in all_results.items():
        try:
            # Replace the structure in the exposure profile
            result.exposure.structure = nearest
        except Exception as exc:
            logger.warning("Could not inject building into %s: %s", name, exc)
