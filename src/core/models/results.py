# src/core/models/results.py
"""Hazard assessment result models."""

from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field, computed_field
from .enums import RiskTier, HazardType, VulnerabilityClass, ConfidenceLevel, ValidationStatus
from .hazard import HazardIntensity
from .exposure import ExposureProfile
from .vulnerability import VulnerabilityAssessment
from .geometry import DataLineage

from .vulnerability import VulnerabilityAssessment



class ValidationMetrics(BaseModel):
    """
    Model validation metrics (Gap 2.1).
    Required for "calibrated" status.
    """
    rmse: Optional[float] = Field(None, description="Root Mean Square Error")
    bias: Optional[float] = Field(None, description="Mean Bias Error")
    r2_score: Optional[float] = Field(None, description="R-squared")
    data_coverage_pct: Optional[float] = Field(None, ge=0, le=100)
    validation_source: str = Field(
        default="none",
        description="Source of ground truth (e.g. gauge_data, reports)"
    )


class HazardAssessmentResult(BaseModel):
    """
    Complete hazard assessment with clean HxE×V separation.
    This is the standard return type for all hazard tools.
    """
    # Core components
    hazard: HazardIntensity = Field(..., description="Hazard intensity (H)")
    exposure: ExposureProfile = Field(..., description="Exposure profile (E)")
    vulnerability: Optional[VulnerabilityAssessment] = Field(
        None, 
        description="Vulnerability (V)"
    )
    
    # Computed impact
    impact_score: float = Field(
        default=0.0, 
        ge=0, 
        le=100, 
        description="Impact score (0-100)"
    )
    impact_tier: RiskTier = Field(default=RiskTier.LOW, description="Risk tier")
    
    # Validation (Gap 2.1)
    validation: Optional[ValidationMetrics] = None
    status: ValidationStatus = Field(
        default=ValidationStatus.UNVALIDATED,
        description="Validation status"
    )
    
    # Intermediate values (for transparency)
    intermediate: Dict[str, Any] = Field(default_factory=dict)
    
    # Aggregation metadata
    can_aggregate_with: List[HazardType] = Field(
        default_factory=list,
        description="Compatible hazards"
    )
    dependency_order: int = Field(
        default=99,
        description="Execution order in dependency graph"
    )

    model_config = {"use_enum_values": True}


class ReturnPeriodLoss(BaseModel):
    """
    Financial loss for a specific return period event.
    """
    return_period_years: int = Field(..., ge=1, description="Event return period")
    loss_usd: float = Field(..., ge=0, description="Financial loss (USD)")
    loss_ratio: float = Field(..., ge=0, le=1.0, description="Loss ratio (0-1)")
    
    model_config = {"use_enum_values": True}


class StructureRiskResult(BaseModel):
    """
    Aggregated risk result for a single structure across all hazards.
    """
    structure_id: str = Field(..., description="Building/Asset ID")
    overall_risk_score: float = Field(..., ge=0, le=100, description="0-100 Risk Score")
    risk_tier: RiskTier = Field(..., description="Overall risk tier")
    
    # Per-hazard breakdown
    hazard_assessments: Dict[HazardType, HazardAssessmentResult] = Field(
        default_factory=dict,
        description="Detailed assessment per hazard type"
    )
    
    # Financial metrics
    aal_usd: Optional[float] = Field(None, ge=0, description="Average Annual Loss (USD)")
    probable_max_loss_usd: Optional[float] = Field(None, ge=0, description="PML (USD)")
    replacement_value_usd: Optional[float] = Field(None, ge=0)
    
    data_lineage: Optional[DataLineage] = None
    
    model_config = {"use_enum_values": True}


# Gap Q: Standard return periods for EAL calculation
STANDARD_RETURN_PERIODS: List[int] = [2, 5, 10, 25, 50, 100, 200, 500, 1000]


def compute_eal_trapezoidal(return_periods: List[int], losses: List[float]) -> float:
    """
    Compute Expected Annual Loss (EAL) using trapezoidal integration of the loss-frequency curve.
    
    Args:
        return_periods: List of return periods in years (e.g. [2, 10, 100])
        losses: Corresponding financial losses in USD
    
    Returns:
        EAL in USD
    """
    if len(return_periods) != len(losses) or len(return_periods) < 2:
        return 0.0
        
    # Sort by probability (1/RP) descending (high freq to low freq)
    data = sorted(zip(return_periods, losses), key=lambda x: x[0])
    rps, ls = zip(*data)
    
    probs = [1.0 / rp for rp in rps]
    eal = 0.0
    
    # Trapezoidal rule
    for i in range(len(probs) - 1):
        p1, p2 = probs[i], probs[i+1] # p1 > p2 (1/2 > 1/5)
        l1, l2 = ls[i], ls[i+1]
        
        prob_diff = p1 - p2
        avg_loss = (l1 + l2) / 2.0
        eal += prob_diff * avg_loss
        
    # Tail risk approximation (optional/simple for now)
    return eal


class PortfolioRiskSummary(BaseModel):
    """
    Aggregated risk summary for a portfolio of assets.
    Used for dashboard reporting.
    """
    portfolio_id: str = Field(..., description="Portfolio Identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    total_assets: int = Field(..., ge=0)
    total_replacement_value_usd: float = Field(..., ge=0)
    
    total_aal_usd: float = Field(..., ge=0, description="Total Annual Average Loss")
    portfolio_risk_score: float = Field(..., ge=0, le=100)
    
    risk_tier_counts: Dict[RiskTier, int] = Field(
        default_factory=dict, 
        description="Count of assets per risk tier"
    )
    
    top_risk_assets: List[StructureRiskResult] = Field(
        default_factory=list,
        description="Top 10 highest risk assets"
    )
    
    model_config = {"use_enum_values": True}
