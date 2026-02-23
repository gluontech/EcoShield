# src/core/models/composite.py
"""Composite risk models."""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, computed_field
from .enums import RiskTier, ConfidenceLevel, HazardType
from .geometry import Location, DataLineage
from .results import HazardAssessmentResult, StructureRiskResult, PortfolioRiskSummary


class CompositeRiskResult(BaseModel):
    """Composite risk with full transparency."""
    event_type: str = Field(..., description="Event class (acute/chronic)")
    composite_score: float = Field(..., ge=0, le=100, description="Composite score")
    composite_tier: RiskTier = Field(..., description="Risk tier")
    confidence: ConfidenceLevel = Field(..., description="Overall confidence")

    # Components (full transparency)
    hazard_scores: Dict[str, float] = Field(..., description="Individual scores")
    weights_used: Dict[str, float] = Field(..., description="Weights applied")

    # Uncertainty
    composite_p5: float = Field(..., ge=0, le=100)
    composite_p95: float = Field(..., ge=0, le=100)

    # Metadata
    city: str
    aggregation_valid: bool = Field(
        ...,
        description="All hazards in same event class"
    )
    warnings: List[str] = Field(default_factory=list)
    excluded_hazards: List[str] = Field(default_factory=list)
    lineage: Optional[DataLineage] = None

    model_config = {"use_enum_values": True}



class SurfaceAdjustments(BaseModel):
    """Summary of surface adjustments applied."""
    original_elevation_m: float
    subsidence_applied_m: float
    slr_applied_m: float
    adjusted_elevation_m: float


class FullRiskProfile(BaseModel):
    """Complete risk profile with acute and chronic components."""
    location: Location
    city: str
    assessment_id: Optional[str] = Field(None, description="Unique assessment ID")
    
    # Context (Gap N6)
    return_period: int = Field(..., description="Primary return period for acute hazards")
    time_horizon: int = Field(..., description="Projection year (e.g. 2050)")
    scenario: str = Field(..., description="Climate scenario (e.g. ssp245)")
    portfolio_eal_usd: Optional[float] = Field(None, description="Total portfolio EAL")

    # Separate composites (NEVER combined)
    acute_risk: CompositeRiskResult = Field(
        ...,
        description="Acute hazards composite"
    )
    chronic_risk: CompositeRiskResult = Field(
        ...,
        description="Chronic hazards composite"
    )

    # Individual hazard details
    acute_hazard_details: Dict[str, HazardAssessmentResult]
    chronic_hazard_details: Dict[str, HazardAssessmentResult]

    # Structure-level results (populated when include_buildings=True)
    structure_results: List[StructureRiskResult] = Field(
        default_factory=list,
        description="Per-building risk results (populated when include_buildings=True)"
    )
    portfolio_summary: Optional[PortfolioRiskSummary] = Field(
        None,
        description="Aggregated portfolio statistics across all assessed buildings"
    )

    # Surface tracking
    surface_adjustments: SurfaceAdjustments

    # Methodology
    methodology: Dict[str, str] = Field(default_factory=lambda: {
        "acute_aggregation": "Weighted sum within same return period",
        "chronic_aggregation": "Weighted sum within same time horizon",
        "no_cross_aggregation": "Acute and chronic scores kept separate",
        "dependency_handling": "Subsidence -> SLR -> Flood/Surge (sequential, no double-count)"
    })

    @computed_field
    @property
    def overall_concern_level(self) -> str:
        """Qualitative overall concern (NOT a combined score)."""
        acute = self.acute_risk.composite_score
        chronic = self.chronic_risk.composite_score

        if acute >= 75 or chronic >= 75:
            return "Critical - Immediate attention required"
        elif acute >= 50 or chronic >= 50:
            primary = "Acute" if acute > chronic else "Chronic"
            return f"High - {primary} hazards are primary concern"
        elif acute >= 25 or chronic >= 25:
            return "Moderate - Monitor and plan mitigation"
        return "Low - Standard precautions sufficient"
