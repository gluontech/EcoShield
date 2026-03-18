# src/api/schemas/requests.py
"""Pydantic request models for the EcoShield API (schema v3.0).

Changes from v2:
- Location contains geographic coordinates only.
- Structure is a separate model with hierarchical category/type validation.
- Hazards removed — auto-detected from city via CITY_HAZARDS.
- TimeHorizon is structured (start_year/end_year) instead of a free string.
- Return periods simplified to a single validated list.
- ResponseProfile replaces ambiguous include_details boolean.
- request_id is required (provided by the client).
"""

from typing import Optional, List

from pydantic import BaseModel, Field, field_validator, model_validator

from src.core.models import SSPScenario
from src.core.models.enums import (
    ResponseProfile,
    StructureCategory,
    StructureType,
    RoofType,
    WallMaterial,
)

# Valid structure_type values per category — used for cross-validation
CATEGORY_TYPES = {
    StructureCategory.RESIDENTIAL: {
        StructureType.TUBE_HOUSE,
        StructureType.SINGLE_DWELLING,
        StructureType.MULTISTORY_DWELLING,
        StructureType.APARTMENT_BUILDING,
        StructureType.INFORMAL_SETTLEMENT,
    },
    StructureCategory.COMMERCIAL: {
        StructureType.HOTEL,
        StructureType.SHOPPING_MALL,
        StructureType.BANK,
        StructureType.GYM,
        StructureType.OFFICE_BUILDING,
        StructureType.RETAIL_SHOP,
        StructureType.RESTAURANT,
        StructureType.HOSPITAL,
        StructureType.SCHOOL,
        StructureType.MUSEUM,
        StructureType.CONVENTION_CENTER,
        # Adaptive reuse: commercial function in residential/industrial envelope
        StructureType.CONVERTED_TUBE_HOUSE_HOTEL,
        StructureType.CONVERTED_TUBE_HOUSE_SHOP,
        StructureType.CONVERTED_TUBE_HOUSE_RESTAURANT,
        StructureType.CONVERTED_VILLA_HOTEL,
        StructureType.CONVERTED_VILLA_RESTAURANT,
        StructureType.CONVERTED_SHOPHOUSE_HOTEL,
        StructureType.CONVERTED_WAREHOUSE_COMMERCIAL,
    },
    StructureCategory.INDUSTRIAL: {
        StructureType.FACTORY,
        StructureType.WAREHOUSE,
    },
}


# ── Sub-models ──────────────────────────────────────────────────────────────

class Location(BaseModel):
    """Geographic coordinates only."""
    lat: float = Field(..., ge=-90, le=90, description="Latitude")
    lon: float = Field(..., ge=-180, le=180, description="Longitude")


class Structure(BaseModel):
    """Asset classification with hierarchical category/type validation."""
    category: StructureCategory = Field(
        ..., description="Top-level building category: residential, commercial, industrial",
    )
    type: StructureType = Field(
        ..., description="Specific structure type within category (e.g. hotel, tube_house)",
    )
    name: Optional[str] = Field(None, description="Building or asset name")
    address: Optional[str] = Field(None, description="Physical address")
    description: Optional[str] = Field(None, description="Additional context or description")
    roof_type: Optional[RoofType] = Field(None, description="Premium: Roof structural type")
    wall_material: Optional[WallMaterial] = Field(None, description="Premium: Exterior wall material")
    ground_floor_height_m: Optional[float] = Field(None, ge=0, description="Premium: Height of first floor above grade")
    num_floors: Optional[int] = Field(None, ge=1, description="Premium: Total number of floors")

    @field_validator("type")
    @classmethod
    def validate_type_matches_category(cls, v: StructureType, info) -> StructureType:
        """Ensure structure type belongs to the declared category."""
        cat = info.data.get("category")
        if cat is None:
            return v
        allowed = CATEGORY_TYPES.get(cat, set())
        if v not in allowed:
            raise ValueError(
                f"structure type '{v.value}' is not valid for category '{cat.value}'. "
                f"Valid types: {sorted(t.value for t in allowed)}"
            )
        return v


class TimeHorizon(BaseModel):
    """Structured climate projection time window."""
    start_year: int = Field(..., ge=2020, le=2150, description="Start year of projection window")
    end_year: int = Field(..., ge=2020, le=2150, description="End year of projection window")

    @model_validator(mode="after")
    def start_before_end(self) -> "TimeHorizon":
        """Validate start_year < end_year."""
        if self.start_year >= self.end_year:
            raise ValueError(
                f"start_year ({self.start_year}) must be before end_year ({self.end_year})"
            )
        return self

    @property
    def midpoint(self) -> int:
        """Representative year (used for model lookups)."""
        return (self.start_year + self.end_year) // 2

    def __str__(self) -> str:
        return f"{self.start_year}-{self.end_year}"


# ── Primary request models ─────────────────────────────────────────────────

class AssessRequest(BaseModel):
    """Single-site hazard assessment request (v3.0)."""
    request_id: str = Field(
        ..., min_length=1,
        description="Client-provided unique request identifier",
    )
    location: Location
    structure: Structure
    city: str = Field(
        default="hcmc",
        description="City key for hazard config lookup (hcmc, hanoi, danang, jakarta, manila, bangkok, singapore)",
    )
    scenario: SSPScenario = Field(
        default=SSPScenario.SSP245,
        description="SSP climate scenario",
    )
    time_horizon: TimeHorizon = Field(
        default_factory=lambda: TimeHorizon(start_year=2041, end_year=2060),
        description="Climate projection time window",
    )
    return_periods: List[int] = Field(
        default=[10, 25, 50, 100, 250],
        description="Return periods in years for multi-RP EAL computation",
    )
    response_profile: ResponseProfile = Field(
        default=ResponseProfile.STANDARD,
        description="Controls response detail level: summary, standard, or full_debug",
    )

    @field_validator("return_periods")
    @classmethod
    def validate_return_periods(cls, v: List[int]) -> List[int]:
        """Validate return periods are within bounds."""
        if len(v) < 1:
            raise ValueError("return_periods must contain at least 1 value")
        if len(v) > 10:
            raise ValueError("return_periods must contain at most 10 values")
        for rp in v:
            if rp < 2 or rp > 1000:
                raise ValueError(f"Return period {rp} out of range [2, 1000]")
        return sorted(set(v))


class PortfolioSite(BaseModel):
    """Single site in a portfolio."""
    location: Location
    structure: Optional[Structure] = Field(
        None, description="Asset classification for this site",
    )
    city: str = Field(
        default="hcmc",
        description="City key for hazard config lookup",
    )
    asset_value_usd: Optional[float] = Field(None, ge=0)


class PortfolioRequest(BaseModel):
    """Batch portfolio analysis request (v3.0)."""
    request_id: str = Field(
        ..., min_length=1,
        description="Client-provided unique request identifier",
    )
    sites: List[PortfolioSite] = Field(..., min_length=1, max_length=100)
    scenario: SSPScenario = Field(default=SSPScenario.SSP245)
    time_horizon: TimeHorizon = Field(
        default_factory=lambda: TimeHorizon(start_year=2041, end_year=2060),
    )
    return_periods: List[int] = Field(
        default=[10, 25, 50, 100, 250],
        description="Return periods in years for multi-RP EAL computation",
    )
    response_profile: ResponseProfile = Field(
        default=ResponseProfile.STANDARD,
    )

    @field_validator("return_periods")
    @classmethod
    def validate_return_periods(cls, v: List[int]) -> List[int]:
        """Validate return periods are within bounds."""
        if len(v) < 1:
            raise ValueError("return_periods must contain at least 1 value")
        if len(v) > 10:
            raise ValueError("return_periods must contain at most 10 values")
        for rp in v:
            if rp < 2 or rp > 1000:
                raise ValueError(f"Return period {rp} out of range [2, 1000]")
        return sorted(set(v))


class HazardQueryParams(BaseModel):
    """Query parameters for hazard-specific lookups."""
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    return_period: int = Field(default=100, ge=2, le=1000)
    scenario: SSPScenario = Field(default=SSPScenario.SSP245)


# ── Structure-level request ──

class BuildingAssessRequest(BaseModel):
    """Structure-level risk assessment request."""
    lat: float = Field(..., ge=-90, le=90, description="Center latitude")
    lon: float = Field(..., ge=-180, le=180, description="Center longitude")
    radius_m: int = Field(
        default=500, ge=50, le=5000,
        description="Search radius in meters",
    )
    city: str = Field(
        default="hcmc",
        description="City key (hcmc, hanoi, danang)",
    )
    scenario: SSPScenario = Field(default=SSPScenario.SSP245)
    time_horizon: TimeHorizon = Field(
        default_factory=lambda: TimeHorizon(start_year=2041, end_year=2060),
    )
    return_periods: List[int] = Field(
        default=[10, 25, 50, 100, 250],
        description="Return periods in years for multi-RP EAL computation",
    )
    max_buildings: int = Field(
        default=1000, ge=1, le=10000,
        description="Max buildings to assess (performance limit)",
    )

    @field_validator("city")
    @classmethod
    def validate_city(cls, v: str) -> str:
        """Validate city is supported."""
        valid = {"hcmc", "hanoi", "danang", "jakarta", "manila", "bangkok", "singapore"}
        if v not in valid:
            raise ValueError(f"City '{v}' not supported. Valid: {sorted(valid)}")
        return v

    @field_validator("return_periods")
    @classmethod
    def validate_return_periods(cls, v: List[int]) -> List[int]:
        """Validate return periods are within bounds."""
        if len(v) < 1:
            raise ValueError("return_periods must contain at least 1 value")
        if len(v) > 10:
            raise ValueError("return_periods must contain at most 10 values")
        for rp in v:
            if rp < 2 or rp > 1000:
                raise ValueError(f"Return period {rp} out of range [2, 1000]")
        return sorted(set(v))
