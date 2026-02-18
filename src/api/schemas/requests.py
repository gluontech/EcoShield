# src/api/schemas/requests.py
"""Pydantic request models for the EcoShield API."""

from typing import Optional, List
from pydantic import BaseModel, Field, field_validator

from src.core.models import SSPScenario


class Location(BaseModel):
    """Geographic location."""
    lat: float = Field(..., ge=-60, le=60, description="Latitude")
    lon: float = Field(..., ge=-180, le=180, description="Longitude")
    name: Optional[str] = Field(None, description="Location label")


class AssessRequest(BaseModel):
    """Single-site hazard assessment request."""
    location: Location
    hazards: List[str] = Field(
        default=["flood", "heat", "cyclone", "surge", "subsidence",
                 "landslide", "wind", "pluvial"],
        description="Hazard types to assess",
    )
    city: str = Field(
        default="hcmc",
        description="City key (hcmc, hanoi, danang)",
    )
    scenario: SSPScenario = Field(
        default=SSPScenario.SSP245,
        description="Climate scenario",
    )
    time_horizon: str = Field(
        default="2041-2060",
        description="Future period (e.g. '2041-2060')",
    )
    return_period: int = Field(
        default=100,
        ge=2, le=1000,
        description="Primary return period in years (used for display/tier)",
    )
    multi_rp: bool = Field(
        default=True,
        description="Enable multi-RP assessment at standard return periods "
                    "[10, 25, 50, 100, 250] for EAL computation",
    )
    return_periods: Optional[List[int]] = Field(
        default=None,
        description="Custom return periods (overrides standard [10,25,50,100,250] "
                    "when multi_rp=True). Each must be 2-1000.",
    )
    include_details: bool = Field(
        default=False,
        description="Include detailed component results",
    )

    @field_validator("hazards")
    @classmethod
    def validate_hazards(cls, v):
        valid = {"flood", "heat", "cyclone", "surge", "subsidence",
                 "landslide", "wind", "pluvial"}
        invalid = set(v) - valid
        if invalid:
            raise ValueError(f"Unknown hazard types: {invalid}. Valid: {valid}")
        return v

    @field_validator("return_periods")
    @classmethod
    def validate_return_periods(cls, v):
        """Validate custom return periods are within bounds."""
        if v is not None:
            for rp in v:
                if rp < 2 or rp > 1000:
                    raise ValueError(f"Return period {rp} out of range [2, 1000]")
            if len(v) < 1:
                raise ValueError("return_periods must contain at least 1 value")
            if len(v) > 10:
                raise ValueError("return_periods max 10 values")
        return v


class PortfolioSite(BaseModel):
    """Single site in a portfolio."""
    location: Location
    asset_value_usd: Optional[float] = Field(None, ge=0)
    asset_type: Optional[str] = None


class PortfolioRequest(BaseModel):
    """Batch portfolio analysis request."""
    sites: List[PortfolioSite] = Field(..., min_length=1, max_length=100)
    hazards: List[str] = Field(
        default=["flood", "heat", "cyclone", "surge", "subsidence",
                 "landslide", "wind", "pluvial"],
    )
    scenario: SSPScenario = Field(default=SSPScenario.SSP245)
    time_horizon: str = Field(default="2041-2060")
    return_period: int = Field(default=100, ge=2, le=1000)
    multi_rp: bool = Field(
        default=True,
        description="Enable multi-RP EAL computation",
    )
    return_periods: Optional[List[int]] = Field(
        default=None,
        description="Custom return periods when multi_rp=True",
    )


class HazardQueryParams(BaseModel):
    """Query parameters for hazard-specific lookups."""
    lat: float = Field(..., ge=-60, le=60)
    lon: float = Field(..., ge=-180, le=180)
    return_period: int = Field(default=100, ge=2, le=1000)
    scenario: SSPScenario = Field(default=SSPScenario.SSP245)
    multi_rp: bool = Field(
        default=False,
        description="Enable multi-RP assessment for this hazard",
    )


# ── Structure-level request ──

class BuildingAssessRequest(BaseModel):
    """Structure-level risk assessment request."""
    lat: float = Field(..., ge=-60, le=60, description="Center latitude")
    lon: float = Field(..., ge=-60, le=180, description="Center longitude")
    radius_m: int = Field(
        default=500, ge=50, le=5000,
        description="Search radius in meters",
    )
    city: str = Field(
        default="hcmc",
        description="City key (hcmc, hanoi, danang)", # TODO: add jakarta, manila, bangkok, singapore for next release version
    )
    return_period: int = Field(
        default=100, ge=2, le=1000,
        description="Primary return period for display/tier",
    )
    multi_rp: bool = Field(
        default=True,
        description="Enable multi-RP loop [10,25,50,100,250] for trapezoidal "
                    "EAL computation",
    )
    return_periods: Optional[List[int]] = Field(
        default=None,
        description="Custom return periods when multi_rp=True",
    )
    scenario: SSPScenario = Field(default=SSPScenario.SSP245)
    time_horizon: str = Field(default="2041-2060")
    max_buildings: int = Field(
        default=1000, ge=1, le=10000,
        description="Max buildings to assess (performance limit)",
    )
    
    @field_validator("city")
    @classmethod
    def validate_city(cls, v):
        valid = {"hcmc", "hanoi", "danang"}
        if v not in valid:
             raise ValueError(f"City '{v}' not supported in this version. Valid: {valid}")
        return v
