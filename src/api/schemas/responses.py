# src/api/schemas/responses.py
"""
Pydantic response models for the EcoShield API.
"""

from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field


class HazardScore(BaseModel):
    """Individual hazard score."""
    hazard_type: str
    risk_score: float = Field(..., ge=0, le=1, description="0-1 normalised risk")
    risk_category: str = Field(..., description="Low / Moderate / High / Very High / Extreme")
    confidence: str
    key_drivers: List[str] = Field(default_factory=list)
    details: Optional[Dict[str, Any]] = None


class AssessResponse(BaseModel):
    """Single-site assessment response."""
    location: Dict[str, Any]
    scenario: str
    time_horizon: str
    return_period: int
    multi_rp: bool = Field(False, description="Whether multi-RP was used")
    return_periods_assessed: Optional[List[int]] = Field(
        None, description="Actual RPs assessed when multi_rp=True"
    )
    overall_risk_score: float = Field(..., ge=0, le=1)
    overall_risk_category: str
    hazards: List[HazardScore]
    portfolio_eal_usd: Optional[float] = Field(
        None, description="Multi-RP trapezoidal EAL in USD. "
                          "Only present when multi_rp=True and buildings assessed."
    )
    data_sources: List[str]
    processing_time_ms: int


class PortfolioSiteResult(BaseModel):
    """Result for one site in a portfolio."""
    location: Dict[str, Any]
    overall_risk_score: float
    overall_risk_category: str
    hazard_scores: Dict[str, float]
    asset_value_usd: Optional[float] = None
    expected_annual_loss_usd: Optional[float] = None
    portfolio_eal_usd: Optional[float] = Field(
        None, description="Multi-RP trapezoidal EAL for this site"
    )


class PortfolioResponse(BaseModel):
    """Batch portfolio response."""
    n_sites: int
    scenario: str
    time_horizon: str
    multi_rp: bool = Field(False, description="Whether multi-RP was used")
    return_periods_assessed: Optional[List[int]] = None
    sites: List[PortfolioSiteResult]
    portfolio_summary: Dict[str, Any]
    processing_time_ms: int


class ErrorResponse(BaseModel):
    """Structured error response."""
    error: str
    detail: str
    status_code: int
    retry_after: Optional[int] = None


# ── Structure-level responses ──

class ReturnPeriodLossItem(BaseModel):
    """Loss at a single return period for one building."""
    return_period: int
    annual_exceedance_probability: float = Field(
        ..., description="1/return_period"
    )
    flood_damage_ratio: float = Field(..., ge=0, le=1)
    wind_damage_ratio: Optional[float] = None
    pluvial_damage_ratio: Optional[float] = Field(
        None, ge=0, le=1, description="Pluvial flood damage ratio"
    )
    max_damage_ratio: float = Field(..., ge=0, le=1)
    estimated_loss_usd: Optional[float] = None


class BuildingRiskItem(BaseModel):
    """Per-building risk result."""
    building_id: str
    latitude: float
    longitude: float
    footprint_area_m2: float
    vulnerability_class: str
    occupancy_class: Optional[str] = Field(
        None, description="Building occupancy (residential, commercial, industrial, "
                          "public_service)"
    )
    flood_damage_ratio: float = Field(
        ..., ge=0, le=1,
        description="Combined riverine+coastal+surge flood damage at primary RP"
    )
    flood_depth_at_building_m: float
    pluvial_damage_ratio: Optional[float] = Field(
        None, ge=0, le=1,
        description="Pluvial flood damage ratio at primary RP"
    )
    wind_damage_ratio: Optional[float] = None
    max_damage_ratio: float = Field(..., ge=0, le=1)
    risk_score: float = Field(..., ge=0, le=100)
    risk_tier: str
    replacement_value_usd: Optional[float] = None
    replacement_value_source: Optional[str] = Field(
        None, description="Source: 'jrc_country_occupancy' or 'jrc_country'"
    )
    expected_annual_loss_usd: Optional[float] = Field(
        None, description="Trapezoidal EAL from multi-RP loss curve. "
                          "Falls back to single-RP estimate if multi_rp=False."
    )
    losses_by_return_period: Optional[List[ReturnPeriodLossItem]] = Field(
        None, description="Full loss-exceedance curve per building. "
                          "One entry per assessed return period."
    )


class BuildingPortfolioSummary(BaseModel):
    """Aggregated building portfolio statistics."""
    total_buildings: int
    buildings_by_tier: Dict[str, int]
    total_replacement_value_usd: float
    total_expected_annual_loss_usd: float = Field(
        ..., description="Sum of per-building trapezoidal EAL"
    )
    portfolio_eal_usd: Optional[float] = Field(
        None, description="Alias for total_expected_annual_loss_usd — "
                          "multi-RP trapezoidal integration"
    )
    mean_damage_ratio: float
    pml_250yr_usd: Optional[float] = Field(
        None, description="Probable Maximum Loss at 250-year RP"
    )


class BuildingAssessResponse(BaseModel):
    """Structure-level assessment response."""
    center: Dict[str, float]
    radius_m: int
    city: str
    scenario: str
    return_period: int = Field(..., description="Primary RP for display/tier")
    multi_rp: bool = Field(False, description="Whether multi-RP was used")
    return_periods_assessed: Optional[List[int]] = Field(
        None, description="Actual RPs assessed [10,25,50,100,250]"
    )
    n_buildings: int
    buildings: List[BuildingRiskItem]
    portfolio_summary: BuildingPortfolioSummary
    data_sources: List[str]
    processing_time_ms: int
