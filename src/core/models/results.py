# src/core/models/results.py
"""Hazard assessment result models."""

from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field, computed_field, model_validator
from .enums import RiskTier, HazardType, VulnerabilityClass, ConfidenceLevel, ValidationStatus
from .hazard import HazardIntensity
from .exposure import ExposureProfile
from .vulnerability import VulnerabilityAssessment
from .geometry import DataLineage


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
    Complete hazard assessment with clean HxE separation.
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
    Financial loss for a specific return period event (v3.2 — Gap Q).
    """
    return_period_years: int = Field(..., ge=1, description="Event return period")
    exceedance_probability: float = Field(..., ge=0, le=1, description="1/RP")
    damage_ratio: float = Field(..., ge=0, le=1.0, description="Damage as fraction of value")
    loss_usd: float = Field(..., ge=0, description="Financial loss (USD)")
    hazard_intensity: float = Field(default=0.0, description="Dominant hazard intensity")
    hazard_intensity_unit: str = Field(default="m", description="Unit of hazard intensity")

    model_config = {"use_enum_values": True}


# Gap Q: Standard return periods for multi-RP EAL calculation
STANDARD_RETURN_PERIODS: List[int] = [2, 5, 10, 25, 50, 100, 250, 500, 1000]


def compute_eal_trapezoidal(
    rp_losses: List[ReturnPeriodLoss],
) -> float:
    """
    Compute Expected Annual Loss (EAL) using trapezoidal integration
    of the loss-exceedance curve.

    Args:
        rp_losses: List of ReturnPeriodLoss (one per return period)

    Returns:
        EAL in USD
    """
    if len(rp_losses) < 2:
        return 0.0

    # Sort by exceedance probability descending (high freq to low freq)
    sorted_losses = sorted(rp_losses, key=lambda x: -x.exceedance_probability)

    eal = 0.0
    for i in range(len(sorted_losses) - 1):
        p1 = sorted_losses[i].exceedance_probability
        p2 = sorted_losses[i + 1].exceedance_probability
        l1 = sorted_losses[i].loss_usd
        l2 = sorted_losses[i + 1].loss_usd

        prob_diff = p1 - p2
        avg_loss = (l1 + l2) / 2.0
        eal += prob_diff * avg_loss

    return eal


class StructureRiskResult(BaseModel):
    """
    Per-building risk result across all hazards (v3.2 — multi-RP EAL).
    """
    # Building identity
    building_id: str = Field(..., description="Building ID")
    latitude: float = Field(..., description="Building centroid latitude")
    longitude: float = Field(..., description="Building centroid longitude")
    footprint_area_m2: Optional[float] = Field(None, ge=0)

    # Building characteristics
    height_m: Optional[float] = Field(None, ge=0)
    num_stories: int = Field(default=1, ge=1)
    vulnerability_class: Optional[VulnerabilityClass] = None
    ground_floor_elevation_m: float = Field(default=0.0, ge=0)
    replacement_value_usd: Optional[float] = Field(None, ge=0)
    replacement_value_source: str = Field(default="unknown")

    @model_validator(mode='before')
    @classmethod
    def map_structure_id(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if 'structure_id' in data and 'building_id' not in data:
                data['building_id'] = data.pop('structure_id')
        return data

    # Per-hazard damage ratios (at primary RP)
    flood_damage_ratio: float = Field(default=0.0, ge=0, le=1)
    flood_depth_at_building_m: float = Field(default=0.0, ge=0)
    surge_damage_ratio: float = Field(default=0.0, ge=0, le=1)
    surge_depth_at_building_m: float = Field(default=0.0, ge=0)
    pluvial_flood_damage_ratio: float = Field(default=0.0, ge=0, le=1)
    pluvial_depth_at_building_m: float = Field(default=0.0, ge=0)
    wind_damage_ratio: float = Field(default=0.0, ge=0, le=1)
    max_wind_speed_ms: float = Field(default=0.0, ge=0)

    # Subsidence (Gap S)
    subsidence_mm_per_year: float = Field(default=0.0)
    subsidence_cumulative_m: float = Field(default=0.0, ge=0)
    subsidence_source: str = Field(default="none")

    # Multi-RP loss curve (Gap Q)
    losses_by_return_period: List[ReturnPeriodLoss] = Field(default_factory=list)

    # Composite risk
    max_damage_ratio: float = Field(default=0.0, ge=0, le=1)
    combined_risk_score: float = Field(default=0.0, ge=0, le=100)
    risk_tier: RiskTier = Field(default=RiskTier.LOW)
    dominant_hazard: Optional[HazardType] = None

    # Financial impact (v3.2: multi-RP EAL)
    expected_annual_loss_usd: float = Field(default=0.0, ge=0)
    probable_maximum_loss_usd: float = Field(default=0.0, ge=0)

    # Metadata
    data_sources: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)

    model_config = {"use_enum_values": True}


class PortfolioRiskSummary(BaseModel):
    """
    Aggregated risk summary for a portfolio of buildings (v3.2).
    """
    portfolio_id: str = Field(..., description="Portfolio Identifier")
    city: str = Field(default="unknown")
    total_buildings: int = Field(..., ge=0)
    buildings_critical: int = Field(default=0, ge=0)
    buildings_high: int = Field(default=0, ge=0)
    buildings_moderate: int = Field(default=0, ge=0)
    buildings_low: int = Field(default=0, ge=0)
    total_replacement_value_usd: float = Field(default=0.0, ge=0)
    total_expected_annual_loss_usd: float = Field(default=0.0, ge=0)
    mean_damage_ratio: float = Field(default=0.0, ge=0, le=1)

    model_config = {"use_enum_values": True}
