# src/core/models/response_models.py
"""
Strict Pydantic v2 response models for the EcoShield API (schema v2.0).

Key design decisions:
- Asset (footprint, height, material) is defined ONCE at root level, not per-hazard.
- Each hazard uses a discriminated union on ``hazard_type`` with typed intermediates.
- Annotated scalar types enforce physical constraints (lat bounds, unit-float, etc.).
- Cross-field validators catch inconsistent data at serialization time.

Usage:
    from src.core.models.response_models import RiskAssessmentReport
    report = RiskAssessmentReport.model_validate(data)
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .enums import (
    AggregationMethod,
    BuildingMaterial,
    ConfidenceLevel,
    DownscalingMethod,
    EventType,
    HazardType,
    ImpactTier,
    IntensityUnit,
    MatchMethod,
    RiskCategory,
    SLRScenario,
    SSPScenario,
    SignalUniformity,
    UncertaintyType,
    ValidationStatus,
    VulnerabilityClass,
)


# ---------------------------------------------------------------------------
# Config — applied globally via inheritance
# ---------------------------------------------------------------------------

class _Base(BaseModel):
    """Strict base: rejects unknown keys, strips whitespace."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_default=True,
    )


# ---------------------------------------------------------------------------
# Annotated scalar types
# ---------------------------------------------------------------------------

Latitude = Annotated[float, Field(ge=-90.0, le=90.0)]
Longitude = Annotated[float, Field(ge=-180.0, le=180.0)]
UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]
Score100 = Annotated[float, Field(ge=0.0, le=100.0)]
PositiveFloat = Annotated[float, Field(gt=0.0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------

class Coordinate(_Base):
    """Latitude/longitude pair with bounds enforcement."""

    lat: Latitude
    lon: Longitude


class EngineInfo(_Base):
    """Processing engine metadata."""

    version: str = Field(pattern=r"^v\d+\.\d+\.\d+$")
    processor: str = Field(min_length=1)


class Location(_Base):
    """User-supplied location with validated coordinates."""

    lat: Latitude
    lon: Longitude
    name: str = Field(min_length=1)


class TimeHorizonResponse(_Base):
    """Structured time horizon with representative year for model lookups."""

    start_year: int = Field(ge=2020, le=2150)
    end_year: int = Field(ge=2020, le=2150)
    representative_year: int = Field(ge=2020, le=2150)

    @model_validator(mode="after")
    def years_valid(self) -> TimeHorizonResponse:
        if self.start_year >= self.end_year:
            raise ValueError(
                f"start_year ({self.start_year}) must be before end_year ({self.end_year})"
            )
        if not (self.start_year <= self.representative_year <= self.end_year):
            raise ValueError(
                f"representative_year ({self.representative_year}) must be within "
                f"[{self.start_year}, {self.end_year}]"
            )
        return self


class DataSourceRef(_Base):
    """Structured data source reference — deduplicated by id."""

    id: str = Field(min_length=1, description="Machine-readable source key")
    name: str = Field(min_length=1, description="Human-readable source name")
    version: str | None = Field(default=None, description="Source version")


class ConfidenceScore(_Base):
    """Unified confidence with both numeric score and categorical level."""

    score: UnitFloat
    category: ConfidenceLevel

    @model_validator(mode="after")
    def category_consistent_with_score(self) -> ConfidenceScore:
        """Soft-check: warn if category/score mismatch."""
        expected = {
            ConfidenceLevel.LOW: (0.0, 0.33),
            ConfidenceLevel.MODERATE: (0.25, 0.66),
            ConfidenceLevel.HIGH: (0.55, 1.0),
        }
        lo, hi = expected.get(self.category, (0.0, 1.0))
        if not (lo <= self.score <= hi + 0.01):
            import warnings
            warnings.warn(
                f"confidence score {self.score} outside expected range "
                f"[{lo}, {hi}] for category '{self.category.value}'",
                stacklevel=2,
            )
        return self


class HazardWeights(_Base):
    """Aggregation weights — must sum to 1.0."""

    primary: Annotated[float, Field(gt=0.0, le=1.0)]
    secondary: Annotated[float, Field(gt=0.0, le=1.0)]
    tertiary: Annotated[float, Field(gt=0.0, le=1.0)]

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> HazardWeights:
        total = round(self.primary + self.secondary + self.tertiary, 6)
        if abs(total - 1.0) > 1e-4:
            raise ValueError(
                f"hazard_weights must sum to 1.0, got {total:.6f}"
            )
        return self


# ---------------------------------------------------------------------------
# Asset models (defined ONCE at root, NOT per-hazard)
# ---------------------------------------------------------------------------

class BuildingFootprint(_Base):
    """Matched building polygon with validation."""

    building_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    overture_id: str | None = None
    osm_id: str | None = None
    name: str | None = None
    address: str | None = None
    name_aliases: list[str] = Field(default_factory=list)
    centroid: Coordinate
    footprint_wkt: str = Field(min_length=10)
    area_m2: PositiveFloat
    confidence: UnitFloat
    match_method: MatchMethod
    footprint_match_confidence: UnitFloat

    @field_validator("footprint_wkt")
    @classmethod
    def wkt_is_polygon(cls, v: str) -> str:
        if not v.strip().upper().startswith("POLYGON"):
            raise ValueError("footprint_wkt must be a WKT POLYGON geometry")
        return v


class BuildingHeight(_Base):
    """Building height with uncertainty and source tracking."""

    height_m: PositiveFloat
    source: str = Field(min_length=1)
    year: int = Field(ge=1900, le=2100)
    uncertainty_m: NonNegativeFloat
    confidence: UnitFloat
    building_presence: UnitFloat
    num_floors: int | None = Field(default=None, ge=1)
    estimated_stories: int | None = Field(default=None, ge=1)


class Asset(_Base):
    """Complete building characterization — appears once at report root."""

    footprint: BuildingFootprint
    height: BuildingHeight
    material: BuildingMaterial
    material_inferred: bool
    occupancy: str
    vulnerability_class: VulnerabilityClass
    classification_source: str
    construction_year: int | None = Field(default=None, ge=1800, le=2100)
    num_stories: int | None = Field(default=None, ge=1)
    has_basement: bool
    has_stilts: bool
    roof_type: str | None = None
    wall_material: str | None = None
    ground_elevation_m: float
    ground_floor_height_m: NonNegativeFloat
    effective_ground_floor_m: NonNegativeFloat
    poi_validated: bool
    replacement_value_usd: NonNegativeFloat | None = None
    replacement_value_source: str
    elevation_m: float
    elevation_source: str
    elevation_uncertainty_m: NonNegativeFloat

    @model_validator(mode="after")
    def effective_floor_gte_ground(self) -> Asset:
        if self.effective_ground_floor_m < self.ground_floor_height_m:
            raise ValueError(
                "effective_ground_floor_m cannot be less than ground_floor_height_m"
            )
        return self


# ---------------------------------------------------------------------------
# Hazard sub-models
# ---------------------------------------------------------------------------

class EventContext(_Base):
    """Event framing: acute (return-period) or chronic (time-horizon)."""

    event_type: EventType
    return_period_years: int | None = Field(default=None, gt=0)
    time_horizon: int | None = Field(default=None, ge=2000, le=2200)
    slr_scenario: SLRScenario | None = None
    percentile: int | None = Field(default=None, ge=1, le=99)
    coupled_to_cyclone: bool | None = None


class HazardIntensityInfo(_Base):
    """Primary intensity value with uncertainty bounds."""

    value: float
    unit: IntensityUnit
    p5: float
    p95: float
    uncertainty_type: UncertaintyType

    @model_validator(mode="after")
    def uncertainty_bounds_ordered(self) -> HazardIntensityInfo:
        if self.p5 > self.p95:
            raise ValueError(f"p5 ({self.p5}) must be <= p95 ({self.p95})")
        return self


class ResolutionInfo(_Base):
    """Spatial resolution transparency."""

    climate_forcing_m: PositiveFloat
    native_m: PositiveFloat
    effective_m: PositiveFloat
    signal_uniformity: SignalUniformity
    downscaling_method: DownscalingMethod

    @model_validator(mode="after")
    def effective_no_finer_than_native(self) -> ResolutionInfo:
        if self.effective_m < self.native_m * 0.5:
            raise ValueError(
                f"effective_m ({self.effective_m}) appears finer than native_m "
                f"({self.native_m}), which is physically implausible"
            )
        return self


class DataLineage(_Base):
    """Provenance tracking for reproducibility."""

    source: str = Field(min_length=1)
    timestamp: datetime


class ExposureOverrides(_Base):
    """Per-hazard exposure adjustments (e.g. subsidence corrections)."""

    adjustments_applied: list[HazardType] = Field(default_factory=list)
    urban_context: str | None = None
    slope_degrees: float | None = Field(default=None, ge=0.0, le=90.0)
    coastal_distance_m: NonNegativeFloat | None = None
    coastal_type: str | None = None


class ImpactResult(_Base):
    """Impact score (0-1 normalized), tier, and validation status."""

    score: UnitFloat
    tier: ImpactTier
    status: ValidationStatus
    validation_source: str = Field(min_length=1)

    @model_validator(mode="after")
    def tier_consistent_with_score(self) -> ImpactResult:
        """Soft-check: warn if tier/score mismatch."""
        expected: dict[ImpactTier, tuple[float, float]] = {
            ImpactTier.NONE: (0.0, 0.0),
            ImpactTier.LOW: (0.0, 0.25),
            ImpactTier.MODERATE: (0.25, 0.50),
            ImpactTier.HIGH: (0.50, 0.75),
            ImpactTier.CRITICAL: (0.75, 1.0),
        }
        low, high = expected[self.tier]
        if not (low <= self.score <= high + 0.01):
            import warnings
            warnings.warn(
                f"impact score {self.score} is outside expected range "
                f"[{low}, {high}] for tier '{self.tier.value}'",
                stacklevel=2,
            )
        return self


# ---------------------------------------------------------------------------
# Per-hazard typed intermediate models
# ---------------------------------------------------------------------------

class SubsidenceIntermediate(_Base):
    """InSAR-derived subsidence projections."""

    velocity_mm_yr: float
    abs_rate_mm_yr: NonNegativeFloat
    cumulative_mm: float
    cumulative_m: float
    years_forward: int = Field(gt=0)
    original_elevation_m: float
    adjusted_elevation_m: float
    subsidence_source: str

    @model_validator(mode="after")
    def cumulative_consistent(self) -> SubsidenceIntermediate:
        expected_m = round(abs(self.velocity_mm_yr) * self.years_forward / 1000.0, 4)
        if abs(self.cumulative_m - expected_m) > 0.01:
            raise ValueError(
                f"cumulative_m ({self.cumulative_m}) inconsistent with "
                f"abs_rate_mm_yr × years_forward / 1000 = {expected_m}"
            )
        return self

    @model_validator(mode="after")
    def adjusted_elevation_consistent(self) -> SubsidenceIntermediate:
        expected = round(self.original_elevation_m - self.cumulative_m, 3)
        if abs(self.adjusted_elevation_m - expected) > 0.02:
            raise ValueError(
                f"adjusted_elevation_m ({self.adjusted_elevation_m}) should be "
                f"original_elevation_m - cumulative_m = {expected}"
            )
        return self


class UrbanHeatIntermediate(_Base):
    """NEX-GDDP + UHI heat projection."""

    baseline_annual_mean_c: float
    baseline_p95_c: float
    current_percentile_temp_c: float
    uhi_effect_c: NonNegativeFloat
    uhi_source: str
    projected_temp_c: float
    temperature_change_c: float
    ensemble_p5_change_c: float
    ensemble_p95_change_c: float
    ensemble_size: int = Field(ge=1)
    current_wbgt_c: float
    projected_wbgt_c: float
    lst_median_c: float | None = None
    heat_wave_days_change: float
    scenario: SSPScenario

    @model_validator(mode="after")
    def ensemble_bounds_ordered(self) -> UrbanHeatIntermediate:
        if self.ensemble_p5_change_c > self.ensemble_p95_change_c:
            raise ValueError(
                "ensemble_p5_change_c must be <= ensemble_p95_change_c"
            )
        return self


class StormSurgeIntermediate(_Base):
    """Parametric storm surge model output."""

    cyclone_wind_kts: NonNegativeFloat
    pressure_deficit_mb: NonNegativeFloat
    base_surge_m: NonNegativeFloat
    shelf_factor: PositiveFloat
    total_surge_m: NonNegativeFloat
    effective_elevation_m: float
    inundation_depth_m: NonNegativeFloat
    subsidence_effect_m: NonNegativeFloat

    @model_validator(mode="after")
    def total_surge_equals_base_times_shelf(self) -> StormSurgeIntermediate:
        expected = round(self.base_surge_m * self.shelf_factor, 4)
        if abs(self.total_surge_m - expected) > 0.01:
            raise ValueError(
                f"total_surge_m ({self.total_surge_m}) should equal "
                f"base_surge_m × shelf_factor = {expected}"
            )
        return self


class CoastalFloodIntermediate(_Base):
    """IPCC AR6 sea-level rise bathtub model output."""

    raw_elevation_m: float
    effective_elevation_m: float
    slr_median_m: NonNegativeFloat
    slr_p5_m: NonNegativeFloat
    slr_p95_m: NonNegativeFloat
    slr_source: str
    tidal_range_m: NonNegativeFloat
    total_water_level_m: NonNegativeFloat
    inundation_depth_m: NonNegativeFloat
    subsidence_effect_m: NonNegativeFloat
    scenario: SSPScenario
    time_horizon: int = Field(ge=2000, le=2200)
    is_coastal: bool

    @model_validator(mode="after")
    def slr_bounds_ordered(self) -> CoastalFloodIntermediate:
        if self.slr_p5_m > self.slr_p95_m:
            raise ValueError("slr_p5_m must be <= slr_p95_m")
        return self


class RiverineFloodIntermediate(_Base):
    """GloFAS + HAND riverine flood model output."""

    _MAX_PLAUSIBLE_DEPTH_M: float = 15.0
    _MAX_PLAUSIBLE_WATER_LEVEL_M: float = 20.0

    hand_value_m: NonNegativeFloat
    discharge_m3s: NonNegativeFloat
    water_level_m: NonNegativeFloat
    channel_width_m: PositiveFloat
    manning_n: Annotated[float, Field(gt=0.0, le=0.2)]
    subsidence_effect_m: NonNegativeFloat
    effective_hand_m: float
    flood_depth_m: NonNegativeFloat
    flooded: bool
    is_urban: bool
    flood_susceptibility: Literal["low", "moderate", "high", "very_high"]
    depth_capped: bool = Field(
        default=False,
        description="True if flood_depth_m was capped by plausibility guardrail",
    )

    @model_validator(mode="after")
    def flooded_consistent_with_depth(self) -> RiverineFloodIntermediate:
        if self.flooded and self.flood_depth_m <= 0:
            raise ValueError(
                "flooded=True but flood_depth_m is zero — inconsistent"
            )
        if not self.flooded and self.flood_depth_m > 0:
            raise ValueError(
                "flooded=False but flood_depth_m > 0 — inconsistent"
            )
        return self

    @model_validator(mode="after")
    def cap_flood_depth(self) -> RiverineFloodIntermediate:
        """Physical plausibility: cap flood depth at dam-break threshold."""
        if self.flood_depth_m > self._MAX_PLAUSIBLE_DEPTH_M:
            import warnings
            warnings.warn(
                f"flood_depth_m ({self.flood_depth_m}) exceeds plausible max "
                f"({self._MAX_PLAUSIBLE_DEPTH_M}m) — capping. "
                f"Original water_level_m={self.water_level_m}",
                stacklevel=2,
            )
            object.__setattr__(self, "flood_depth_m", self._MAX_PLAUSIBLE_DEPTH_M)
            object.__setattr__(self, "depth_capped", True)
        return self


class PluvialFloodIntermediate(_Base):
    """DEM/HAND proxy pluvial flood model output."""

    hand_value_m: NonNegativeFloat
    slope_degrees: Annotated[float, Field(ge=0.0, le=90.0)]
    impervious_fraction: UnitFloat
    design_rainfall_mm: PositiveFloat
    susceptibility_index: UnitFloat
    estimated_depth_m: NonNegativeFloat
    runoff_coefficient: UnitFloat
    scenario: SSPScenario


class CycloneParams(_Base):
    """Parametric cyclone event parameters."""

    max_wind_ms: NonNegativeFloat
    central_pressure_mb: Annotated[float, Field(ge=800.0, le=1050.0)]
    rmw_km: PositiveFloat
    heading_deg: Annotated[float, Field(ge=0.0, lt=360.0)]
    forward_speed_ms: NonNegativeFloat
    saffir_simpson_category: Annotated[int, Field(ge=1, le=5)]


class TropicalCycloneIntermediate(_Base):
    """IBTrACS + Holland parametric wind model output."""

    _MAX_PLAUSIBLE_WIND_MS: float = 85.0

    return_period_wind_ms: NonNegativeFloat
    site_wind_ms: NonNegativeFloat
    central_pressure_mb: Annotated[float, Field(ge=800.0, le=1050.0)]
    rmw_km: PositiveFloat
    holland_b_parameter: float | None = None
    saffir_simpson_category: Annotated[int, Field(ge=1, le=5)]
    cyclone_params: CycloneParams
    max_wind_kts: NonNegativeFloat
    wind_capped: bool = Field(
        default=False,
        description="True if wind speed was capped by plausibility guardrail",
    )

    @model_validator(mode="after")
    def cap_wind_speed(self) -> TropicalCycloneIntermediate:
        """Physical plausibility: cap wind at Cat 5 upper bound + margin."""
        if self.site_wind_ms > self._MAX_PLAUSIBLE_WIND_MS:
            import warnings
            warnings.warn(
                f"site_wind_ms ({self.site_wind_ms}) exceeds plausible max "
                f"({self._MAX_PLAUSIBLE_WIND_MS} m/s) — capping",
                stacklevel=2,
            )
            capped_kts = round(self._MAX_PLAUSIBLE_WIND_MS * 1.944, 1)
            object.__setattr__(self, "site_wind_ms", self._MAX_PLAUSIBLE_WIND_MS)
            object.__setattr__(self, "return_period_wind_ms", self._MAX_PLAUSIBLE_WIND_MS)
            object.__setattr__(self, "max_wind_kts", capped_kts)
            object.__setattr__(self, "wind_capped", True)
        return self

    @model_validator(mode="after")
    def wind_speed_unit_consistency(self) -> TropicalCycloneIntermediate:
        expected_kts = self.site_wind_ms * 1.944
        if abs(self.max_wind_kts - expected_kts) / max(expected_kts, 1) > 0.06:
            raise ValueError(
                f"max_wind_kts ({self.max_wind_kts}) inconsistent with "
                f"site_wind_ms ({self.site_wind_ms}): expected ~{expected_kts:.1f} kts"
            )
        return self


# ---------------------------------------------------------------------------
# Hazard record — discriminated union on hazard_type
# ---------------------------------------------------------------------------

class _HazardBase(_Base):
    """Fields common to all fully-assessed hazards."""

    risk_score: UnitFloat
    risk_category: RiskCategory
    confidence: ConfidenceScore
    is_applicable: bool = Field(
        default=True,
        description="False when hazard is near-zero impact for this location",
    )
    key_drivers: list[str] = Field(default_factory=list)
    event_context: EventContext | None = None
    intensity: HazardIntensityInfo
    resolution: ResolutionInfo | None = None
    data_sources: list[DataSourceRef] = Field(min_length=1)
    limitations: list[str] | None = None
    lineage: DataLineage | None = None
    exposure_overrides: ExposureOverrides | None = None
    impact: ImpactResult
    can_aggregate_with: list[HazardType] = Field(default_factory=list)
    dependency_order: int = Field(ge=1, le=10)

    @model_validator(mode="after")
    def risk_score_consistent_with_category(self) -> _HazardBase:
        thresholds: dict[RiskCategory, tuple[float, float]] = {
            RiskCategory.NONE: (0.0, 0.0),
            RiskCategory.LOW: (0.0, 0.33),
            RiskCategory.MODERATE: (0.25, 0.55),
            RiskCategory.HIGH: (0.45, 0.75),
            RiskCategory.EXTREME: (0.65, 1.0),
        }
        lo, hi = thresholds[self.risk_category]
        if not (lo <= self.risk_score <= hi + 0.01):
            import warnings
            warnings.warn(
                f"{self.__class__.__name__}: risk_score {self.risk_score} "
                f"outside expected range [{lo}, {hi}] for category "
                f"'{self.risk_category.value}'",
                stacklevel=2,
            )
        return self

    @model_validator(mode="after")
    def aggregation_targets_are_valid_hazards(self) -> _HazardBase:
        own_type = getattr(self, "hazard_type", None)
        if own_type and own_type in self.can_aggregate_with:
            raise ValueError(
                f"hazard_type '{own_type}' cannot list itself in can_aggregate_with"
            )
        return self


class SubsidenceHazard(_HazardBase):
    hazard_type: Literal[HazardType.SUBSIDENCE]
    intermediate: SubsidenceIntermediate | None = None


class UrbanHeatHazard(_HazardBase):
    hazard_type: Literal[HazardType.URBAN_HEAT]
    intermediate: UrbanHeatIntermediate | None = None


class StormSurgeHazard(_HazardBase):
    hazard_type: Literal[HazardType.STORM_SURGE]
    intermediate: StormSurgeIntermediate | None = None


class CoastalFloodHazard(_HazardBase):
    hazard_type: Literal[HazardType.COASTAL_FLOOD]
    intermediate: CoastalFloodIntermediate | None = None


class RiverineFloodHazard(_HazardBase):
    hazard_type: Literal[HazardType.RIVERINE_FLOOD]
    intermediate: RiverineFloodIntermediate | None = None


class PluvialFloodHazard(_HazardBase):
    hazard_type: Literal[HazardType.PLUVIAL_FLOOD]
    intermediate: PluvialFloodIntermediate | None = None


class TropicalCycloneHazard(_HazardBase):
    hazard_type: Literal[HazardType.TROPICAL_CYCLONE]
    intermediate: TropicalCycloneIntermediate | None = None


class LandslideIntermediate(_Base):
    """Multi-factor landslide susceptibility model output."""

    slope_degrees: Annotated[float, Field(ge=0.0, le=90.0)]
    base_susceptibility: NonNegativeFloat
    soil_factor: UnitFloat
    vegetation_factor: UnitFloat
    trigger_ratio: NonNegativeFloat
    triggered: bool
    combined_score: NonNegativeFloat
    precip_mm_day: NonNegativeFloat


class LandslideHazard(_HazardBase):
    hazard_type: Literal[HazardType.LANDSLIDE]
    intermediate: LandslideIntermediate | None = None


class UnassessedHazard(_Base):
    """Hazard present in the system but not evaluated for this location."""

    hazard_type: HazardType
    risk_score: Literal[0]
    risk_category: Literal[RiskCategory.NOT_ASSESSED]
    confidence: ConfidenceLevel
    key_drivers: list[str] = Field(min_length=1)


# Discriminated union for fully-assessed hazards only
_AssessedHazard = Annotated[
    Union[
        SubsidenceHazard,
        UrbanHeatHazard,
        StormSurgeHazard,
        CoastalFloodHazard,
        RiverineFloodHazard,
        PluvialFloodHazard,
        TropicalCycloneHazard,
        LandslideHazard,
    ],
    Field(discriminator="hazard_type"),
]

# Full union: try assessed (discriminated) first, fall back to unassessed
HazardRecord = Union[_AssessedHazard, UnassessedHazard]


# ---------------------------------------------------------------------------
# Root model
# ---------------------------------------------------------------------------

class RiskAssessmentReport(_Base):
    """Top-level response for ``POST /v1/assess`` (schema v3.0)."""

    schema_version: str = Field(pattern=r"^\d+\.\d+$")
    engine: EngineInfo
    location: Location
    scenario: SSPScenario
    time_horizon: TimeHorizonResponse
    return_periods_assessed: list[int] = Field(min_length=1)
    asset: Asset
    overall_risk_score: UnitFloat
    overall_risk_category: RiskCategory
    aggregation_method: AggregationMethod
    hazard_weights: HazardWeights
    hazards: list[HazardRecord] = Field(min_length=1)
    portfolio_eal_usd: NonNegativeFloat
    data_sources: list[DataSourceRef] = Field(min_length=1)

    @field_validator("return_periods_assessed")
    @classmethod
    def return_periods_positive(cls, v: list[int]) -> list[int]:
        if any(rp <= 0 for rp in v):
            raise ValueError("All return_periods_assessed must be > 0")
        return v

    @model_validator(mode="after")
    def no_duplicate_hazard_types(self) -> RiskAssessmentReport:
        types = [h.hazard_type for h in self.hazards]
        duplicates = {t for t in types if types.count(t) > 1}
        if duplicates:
            raise ValueError(
                f"Duplicate hazard_type entries found: {duplicates}"
            )
        return self

    def assessed_hazards(self) -> list[_HazardBase]:
        """Returns only fully-assessed (non-UnassessedHazard) records."""
        return [h for h in self.hazards if isinstance(h, _HazardBase)]

    def hazard_by_type(self, hazard_type: HazardType) -> HazardRecord | None:
        """Lookup a specific hazard by type."""
        for h in self.hazards:
            if h.hazard_type == hazard_type:
                return h
        return None


# ---------------------------------------------------------------------------
# Parse helper
# ---------------------------------------------------------------------------

def load_report(path: str) -> RiskAssessmentReport:
    """Load and validate a risk assessment JSON file."""
    import json
    with open(path) as f:
        data = json.load(f)
    return RiskAssessmentReport.model_validate(data)
