"""
EcoShield Climate Risk Assessment — Pydantic v2 Models
=======================================================
Requires: pydantic>=2.0

Usage:
    from models import RiskAssessmentReport
    import json

    with open("response_improved.json") as f:
        data = json.load(f)

    report = RiskAssessmentReport.model_validate(data)
    print(report.model_dump_json(indent=2))
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# ---------------------------------------------------------------------------
# Config — applied globally via inheritance
# ---------------------------------------------------------------------------

class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",          # reject unknown keys
        str_strip_whitespace=True,
        validate_default=True,
    )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SSPScenario(str, Enum):
    SSP119 = "ssp119"
    SSP126 = "ssp126"
    SSP245 = "ssp245"
    SSP370 = "ssp370"
    SSP585 = "ssp585"


class RiskCategory(str, Enum):
    NONE         = "None"
    LOW          = "Low"
    MODERATE     = "Moderate"
    HIGH         = "High"
    EXTREME      = "Extreme"
    NOT_ASSESSED = "Not Assessed"


class ConfidenceLevel(str, Enum):
    LOW      = "low"
    MODERATE = "moderate"
    HIGH     = "high"


class ImpactTier(str, Enum):
    NONE     = "None"
    LOW      = "Low"
    MODERATE = "Moderate"
    HIGH     = "High"
    CRITICAL = "Critical"


class ValidationStatus(str, Enum):
    UNVALIDATED = "unvalidated"
    VALIDATED   = "validated"
    PROVISIONAL = "provisional"


class EventType(str, Enum):
    ACUTE   = "acute"
    CHRONIC = "chronic"


class SignalUniformity(str, Enum):
    GRID_CELL   = "grid_cell"
    DOWNSCALED  = "downscaled"
    STATION     = "station"


class DownscalingMethod(str, Enum):
    TERRAIN_OVERLAY_ONLY = "terrain_overlay_only"
    STATISTICAL          = "statistical"
    DYNAMICAL            = "dynamical"
    HYBRID               = "hybrid"


class BuildingMaterial(str, Enum):
    MASONRY_UNREINFORCED = "masonry_unreinforced"
    MASONRY_REINFORCED   = "masonry_reinforced"
    CONCRETE_RC          = "concrete_rc"
    CONCRETE_PRECAST     = "concrete_precast"
    STEEL                = "steel"
    WOOD                 = "wood"
    MIXED                = "mixed"
    UNKNOWN              = "unknown"


class VulnerabilityClass(str, Enum):
    CLASS_I   = "class_i"
    CLASS_II  = "class_ii"
    CLASS_III = "class_iii"
    CLASS_IV  = "class_iv"
    UNKNOWN   = "unknown"


class HazardType(str, Enum):
    SUBSIDENCE       = "subsidence"
    URBAN_HEAT       = "urban_heat"
    STORM_SURGE      = "storm_surge"
    COASTAL_FLOOD    = "coastal_flood"
    RIVERINE_FLOOD   = "riverine_flood"
    PLUVIAL_FLOOD    = "pluvial_flood"
    TROPICAL_CYCLONE = "tropical_cyclone"
    LANDSLIDE        = "landslide"


class AggregationMethod(str, Enum):
    COMPOSITE_WEIGHTED_AVERAGE = "composite_weighted_average"
    MAX                        = "max"
    WEIGHTED_SUM               = "weighted_sum"


class MatchMethod(str, Enum):
    BUFFER_OVERLAP = "buffer_overlap"
    CENTROID       = "centroid"
    EXACT          = "exact"


class UncertaintyType(str, Enum):
    MEASUREMENT_30PCT          = "measurement_uncertainty_30pct"
    ENSEMBLE_INTER_MODEL       = "ensemble_inter_model_spread"
    PARAMETRIC_MODEL           = "parametric_model_uncertainty"
    IPCC_AR6_SCENARIO_RANGE    = "ipcc_ar6_scenario_range"
    MANNING_35PCT              = "manning_parameter_uncertainty_35pct"
    PROXY_MODEL_HIGH           = "proxy_model_high_uncertainty"
    GUMBEL_FIT                 = "gumbel_fit_uncertainty"


class IntensityUnit(str, Enum):
    MM_YR   = "mm/yr"
    M_S     = "m/s"
    METRES  = "m"
    CELSIUS = "C"
    KPA     = "kPa"
    MM      = "mm"


class SLRScenario(str, Enum):
    LOW    = "low"
    MEDIAN = "median"
    HIGH   = "high"


# ---------------------------------------------------------------------------
# Annotated scalar types
# ---------------------------------------------------------------------------

Latitude  = Annotated[float, Field(ge=-90.0,  le=90.0)]
Longitude = Annotated[float, Field(ge=-180.0, le=180.0)]
UnitFloat = Annotated[float, Field(ge=0.0,    le=1.0)]    # probability / normalised score
Score100  = Annotated[float, Field(ge=0.0,    le=100.0)]  # impact score 0-100
PositiveFloat = Annotated[float, Field(gt=0.0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------

class Coordinate(_Base):
    lat: Latitude
    lon: Longitude


class EngineInfo(_Base):
    version: str = Field(pattern=r"^v\d+\.\d+\.\d+$")
    processor: str = Field(min_length=1)


class Location(_Base):
    lat: Latitude
    lon: Longitude
    name: str = Field(min_length=1)


class HazardWeights(_Base):
    primary:   Annotated[float, Field(gt=0.0, le=1.0)]
    secondary: Annotated[float, Field(gt=0.0, le=1.0)]
    tertiary:  Annotated[float, Field(gt=0.0, le=1.0)]

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> HazardWeights:
        total = round(self.primary + self.secondary + self.tertiary, 6)
        if abs(total - 1.0) > 1e-4:
            raise ValueError(
                f"hazard_weights must sum to 1.0, got {total:.6f}"
            )
        return self


# ---------------------------------------------------------------------------
# Asset models
# ---------------------------------------------------------------------------

class BuildingFootprint(_Base):
    building_id:              str   = Field(min_length=1)
    source:                   str   = Field(min_length=1)
    overture_id:              str | None = None
    osm_id:                   str | None = None
    name:                     str | None = None
    address:                  str | None = None
    name_aliases:             list[str]  = Field(default_factory=list)
    centroid:                 Coordinate
    footprint_wkt:            str        = Field(min_length=10)
    area_m2:                  PositiveFloat
    confidence:               UnitFloat
    match_method:             MatchMethod
    footprint_match_confidence: UnitFloat

    @field_validator("footprint_wkt")
    @classmethod
    def wkt_is_polygon(cls, v: str) -> str:
        if not v.strip().upper().startswith("POLYGON"):
            raise ValueError("footprint_wkt must be a WKT POLYGON geometry")
        return v


class BuildingHeight(_Base):
    height_m:          PositiveFloat
    source:            str = Field(min_length=1)
    year:              int = Field(ge=1900, le=2100)
    uncertainty_m:     NonNegativeFloat
    confidence:        UnitFloat
    building_presence: UnitFloat
    num_floors:        int | None = Field(default=None, ge=1)
    estimated_stories: int | None = Field(default=None, ge=1)


class Asset(_Base):
    footprint:               BuildingFootprint
    height:                  BuildingHeight
    material:                BuildingMaterial
    material_inferred:       bool
    occupancy:               str     # free-text; could be an Enum if values are known
    vulnerability_class:     VulnerabilityClass
    classification_source:   str
    construction_year:       int | None = Field(default=None, ge=1800, le=2100)
    num_stories:             int | None = Field(default=None, ge=1)
    has_basement:            bool
    has_stilts:              bool
    roof_type:               str | None = None
    wall_material:           str | None = None
    ground_elevation_m:      float
    ground_floor_height_m:   NonNegativeFloat
    effective_ground_floor_m: NonNegativeFloat
    poi_validated:           bool
    replacement_value_usd:   NonNegativeFloat | None = None
    replacement_value_source: str
    elevation_m:             float   # can be negative in low-lying areas
    elevation_source:        str
    elevation_uncertainty_m: NonNegativeFloat

    @model_validator(mode="after")
    def effective_floor_gte_ground(self) -> Asset:
        if self.effective_ground_floor_m < self.ground_floor_height_m:
            raise ValueError(
                "effective_ground_floor_m cannot be less than ground_floor_height_m"
            )
        return self


# ---------------------------------------------------------------------------
# Hazard sub-models (shared across hazard types)
# ---------------------------------------------------------------------------

class EventContext(_Base):
    event_type:          EventType
    return_period_years: int | None    = Field(default=None, gt=0)
    time_horizon:        int | None    = Field(default=None, ge=2000, le=2200)
    slr_scenario:        SLRScenario | None = None
    percentile:          int | None    = Field(default=None, ge=1, le=99)
    coupled_to_cyclone:  bool | None   = None

    @model_validator(mode="after")
    def acute_requires_return_period(self) -> EventContext:
        if self.event_type == EventType.ACUTE and self.return_period_years is None:
            raise ValueError(
                "return_period_years is required for acute events"
            )
        if self.event_type == EventType.CHRONIC and self.return_period_years is not None:
            raise ValueError(
                "return_period_years must be null for chronic events"
            )
        return self


class HazardIntensity(_Base):
    value:            float              # can be negative (e.g. temperature anomalies)
    unit:             IntensityUnit
    p5:               float
    p95:              float
    uncertainty_type: UncertaintyType

    @model_validator(mode="after")
    def uncertainty_bounds_ordered(self) -> HazardIntensity:
        if self.p5 > self.p95:
            raise ValueError(f"p5 ({self.p5}) must be <= p95 ({self.p95})")
        # value should sit within or close to [p5, p95]; allow 5% overshoot for rounding
        return self


class ResolutionInfo(_Base):
    climate_forcing_m:  PositiveFloat
    native_m:           PositiveFloat
    effective_m:        PositiveFloat
    signal_uniformity:  SignalUniformity
    downscaling_method: DownscalingMethod

    @model_validator(mode="after")
    def effective_no_finer_than_native(self) -> ResolutionInfo:
        # Effective resolution can equal native but not be artificially finer
        if self.effective_m < self.native_m * 0.5:
            raise ValueError(
                f"effective_m ({self.effective_m}) appears finer than native_m "
                f"({self.native_m}), which is physically implausible"
            )
        return self


class DataLineage(_Base):
    source:    str = Field(min_length=1)
    timestamp: datetime


class ExposureOverrides(_Base):
    adjustments_applied: list[HazardType] = Field(default_factory=list)
    urban_context:       str | None  = None
    slope_degrees:       float | None = Field(default=None, ge=0.0, le=90.0)
    coastal_distance_m:  NonNegativeFloat | None = None
    coastal_type:        str | None  = None


class ImpactResult(_Base):
    score:             UnitFloat
    tier:              ImpactTier
    status:            ValidationStatus
    validation_source: str = Field(min_length=1)

    @model_validator(mode="after")
    def tier_consistent_with_score(self) -> ImpactResult:
        """Soft-check: tier boundaries (informational, not hard-reject)."""
        expected: dict[ImpactTier, tuple[float, float]] = {
            ImpactTier.NONE:     (0.0,  0.0),
            ImpactTier.LOW:      (0.0,  0.25),
            ImpactTier.MODERATE: (0.25, 0.50),
            ImpactTier.HIGH:     (0.50, 0.75),
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
    velocity_mm_yr:       float   # negative = subsiding
    abs_rate_mm_yr:       NonNegativeFloat
    cumulative_mm:        float
    cumulative_m:         float
    years_forward:        int     = Field(gt=0)
    original_elevation_m: float
    adjusted_elevation_m: float
    subsidence_source:    str

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
    baseline_annual_mean_c:   float
    baseline_p95_c:           float
    current_percentile_temp_c: float
    uhi_effect_c:             NonNegativeFloat
    uhi_source:               str
    projected_temp_c:         float
    temperature_change_c:     float
    ensemble_p5_change_c:     float
    ensemble_p95_change_c:    float
    ensemble_size:            int   = Field(ge=1)
    current_wbgt_c:           float
    projected_wbgt_c:         float
    lst_median_c:             float | None = None
    heat_wave_days_change:    float
    scenario:                 SSPScenario

    @model_validator(mode="after")
    def ensemble_bounds_ordered(self) -> UrbanHeatIntermediate:
        if self.ensemble_p5_change_c > self.ensemble_p95_change_c:
            raise ValueError(
                "ensemble_p5_change_c must be <= ensemble_p95_change_c"
            )
        return self


class StormSurgeIntermediate(_Base):
    cyclone_wind_kts:    NonNegativeFloat
    pressure_deficit_mb: NonNegativeFloat
    base_surge_m:        NonNegativeFloat
    shelf_factor:        PositiveFloat
    total_surge_m:       NonNegativeFloat
    effective_elevation_m: float
    inundation_depth_m:  NonNegativeFloat
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
    raw_elevation_m:       float
    effective_elevation_m: float
    slr_median_m:          NonNegativeFloat
    slr_p5_m:              NonNegativeFloat
    slr_p95_m:             NonNegativeFloat
    slr_source:            str
    tidal_range_m:         NonNegativeFloat
    total_water_level_m:   NonNegativeFloat
    inundation_depth_m:    NonNegativeFloat
    subsidence_effect_m:   NonNegativeFloat
    scenario:              SSPScenario
    time_horizon:          int     = Field(ge=2000, le=2200)
    is_coastal:            bool

    @model_validator(mode="after")
    def slr_bounds_ordered(self) -> CoastalFloodIntermediate:
        if self.slr_p5_m > self.slr_p95_m:
            raise ValueError("slr_p5_m must be <= slr_p95_m")
        return self


class RiverineFloodIntermediate(_Base):
    _MAX_PLAUSIBLE_DEPTH_M: float = 15.0

    hand_value_m:        NonNegativeFloat
    discharge_m3s:       NonNegativeFloat
    water_level_m:       NonNegativeFloat
    channel_width_m:     PositiveFloat
    manning_n:           Annotated[float, Field(gt=0.0, le=0.2)]
    subsidence_effect_m: NonNegativeFloat
    effective_hand_m:    float
    flood_depth_m:       NonNegativeFloat
    flooded:             bool
    is_urban:            bool
    flood_susceptibility: Literal["low", "moderate", "high", "very_high"]
    depth_capped: bool = Field(default=False)

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
        if self.flood_depth_m > self._MAX_PLAUSIBLE_DEPTH_M:
            import warnings
            warnings.warn(
                f"flood_depth_m ({self.flood_depth_m}) exceeds plausible max "
                f"({self._MAX_PLAUSIBLE_DEPTH_M}m) — capping",
                stacklevel=2,
            )
            object.__setattr__(self, "flood_depth_m", self._MAX_PLAUSIBLE_DEPTH_M)
            object.__setattr__(self, "depth_capped", True)
        return self


class PluvialFloodIntermediate(_Base):
    hand_value_m:         NonNegativeFloat
    slope_degrees:        Annotated[float, Field(ge=0.0, le=90.0)]
    impervious_fraction:  UnitFloat
    design_rainfall_mm:   PositiveFloat
    susceptibility_index: UnitFloat
    estimated_depth_m:    NonNegativeFloat
    runoff_coefficient:   UnitFloat
    scenario:             SSPScenario


class CycloneParams(_Base):
    max_wind_ms:            NonNegativeFloat
    central_pressure_mb:   Annotated[float, Field(ge=800.0, le=1050.0)]
    rmw_km:                PositiveFloat
    heading_deg:           Annotated[float, Field(ge=0.0, lt=360.0)]
    forward_speed_ms:      NonNegativeFloat
    saffir_simpson_category: Annotated[int, Field(ge=1, le=5)]


class TropicalCycloneIntermediate(_Base):
    return_period_wind_ms:   NonNegativeFloat
    site_wind_ms:            NonNegativeFloat
    central_pressure_mb:     Annotated[float, Field(ge=800.0, le=1050.0)]
    rmw_km:                  PositiveFloat
    holland_b_parameter:     float | None = None
    saffir_simpson_category: Annotated[int, Field(ge=1, le=5)]
    cyclone_params:          CycloneParams
    max_wind_kts:            NonNegativeFloat

    @model_validator(mode="after")
    def wind_speed_unit_consistency(self) -> TropicalCycloneIntermediate:
        # 1 m/s ≈ 1.944 kts; allow 5% tolerance for rounding
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
    risk_score:      UnitFloat
    risk_category:   RiskCategory
    confidence:      ConfidenceLevel
    key_drivers:     list[str]          = Field(default_factory=list)
    event_context:   EventContext
    intensity:       HazardIntensity
    resolution:      ResolutionInfo
    data_sources:    list[str]          = Field(min_length=1)
    limitations:     list[str]          = Field(default_factory=list)
    lineage:         DataLineage
    exposure_overrides: ExposureOverrides
    impact:          ImpactResult
    can_aggregate_with: list[HazardType] = Field(default_factory=list)
    dependency_order: int               = Field(ge=1, le=10)

    @model_validator(mode="after")
    def risk_score_consistent_with_category(self) -> _HazardBase:
        thresholds: dict[RiskCategory, tuple[float, float]] = {
            RiskCategory.LOW:      (0.0,  0.33),
            RiskCategory.MODERATE: (0.25, 0.55),
            RiskCategory.HIGH:     (0.45, 0.75),
            RiskCategory.EXTREME:  (0.65, 1.0),
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
        # Prevent self-referential aggregation
        own_type = getattr(self, "hazard_type", None)
        if own_type and own_type in self.can_aggregate_with:
            raise ValueError(
                f"hazard_type '{own_type}' cannot list itself in can_aggregate_with"
            )
        return self


class SubsidenceHazard(_HazardBase):
    hazard_type:  Literal[HazardType.SUBSIDENCE]
    intermediate: SubsidenceIntermediate


class UrbanHeatHazard(_HazardBase):
    hazard_type:  Literal[HazardType.URBAN_HEAT]
    intermediate: UrbanHeatIntermediate


class StormSurgeHazard(_HazardBase):
    hazard_type:  Literal[HazardType.STORM_SURGE]
    intermediate: StormSurgeIntermediate


class CoastalFloodHazard(_HazardBase):
    hazard_type:  Literal[HazardType.COASTAL_FLOOD]
    intermediate: CoastalFloodIntermediate


class RiverineFloodHazard(_HazardBase):
    hazard_type:  Literal[HazardType.RIVERINE_FLOOD]
    intermediate: RiverineFloodIntermediate


class PluvialFloodHazard(_HazardBase):
    hazard_type:  Literal[HazardType.PLUVIAL_FLOOD]
    intermediate: PluvialFloodIntermediate


class TropicalCycloneHazard(_HazardBase):
    hazard_type:  Literal[HazardType.TROPICAL_CYCLONE]
    intermediate: TropicalCycloneIntermediate


class UnassessedHazard(_Base):
    """Hazard present in the system but not evaluated for this location."""
    hazard_type:   HazardType
    risk_score:    Literal[0]
    risk_category: Literal[RiskCategory.NOT_ASSESSED]
    confidence:    ConfidenceLevel
    key_drivers:   list[str] = Field(min_length=1)  # must explain why not assessed


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
    ],
    Field(discriminator="hazard_type"),
]

# Full union: try assessed (discriminated) first, fall back to unassessed
HazardRecord = Union[_AssessedHazard, UnassessedHazard]


# ---------------------------------------------------------------------------
# Root model
# ---------------------------------------------------------------------------

_TIME_HORIZON_RE = re.compile(r"^\d{4}-\d{4}$")


class RiskAssessmentReport(_Base):
    schema_version:         str         = Field(pattern=r"^\d+\.\d+$")
    engine:                 EngineInfo
    location:               Location
    scenario:               SSPScenario
    time_horizon:           str         # e.g. "2041-2060"
    return_period:          int         = Field(gt=0)
    multi_rp:               bool
    return_periods_assessed: list[int]  = Field(min_length=1)
    asset:                  Asset
    overall_risk_score:     UnitFloat
    overall_risk_category:  RiskCategory
    aggregation_method:     AggregationMethod
    hazard_weights:         HazardWeights
    hazards:                list[HazardRecord] = Field(min_length=1)
    portfolio_eal_usd:      NonNegativeFloat
    data_sources:           list[str]   = Field(min_length=1)

    @field_validator("time_horizon")
    @classmethod
    def time_horizon_format(cls, v: str) -> str:
        if not _TIME_HORIZON_RE.match(v):
            raise ValueError(
                f"time_horizon must be in 'YYYY-YYYY' format, got '{v}'"
            )
        start, end = int(v[:4]), int(v[5:])
        if start >= end:
            raise ValueError(
                f"time_horizon start year ({start}) must be before end year ({end})"
            )
        return v

    @field_validator("return_periods_assessed")
    @classmethod
    def return_periods_positive(cls, v: list[int]) -> list[int]:
        if any(rp <= 0 for rp in v):
            raise ValueError("All return_periods_assessed must be > 0")
        return v

    @model_validator(mode="after")
    def return_period_in_assessed_list(self) -> RiskAssessmentReport:
        if self.return_period not in self.return_periods_assessed:
            raise ValueError(
                f"return_period ({self.return_period}) must be present in "
                f"return_periods_assessed ({self.return_periods_assessed})"
            )
        return self

    @model_validator(mode="after")
    def no_duplicate_hazard_types(self) -> RiskAssessmentReport:
        types = [h.hazard_type for h in self.hazards]
        duplicates = {t for t in types if types.count(t) > 1}
        if duplicates:
            raise ValueError(
                f"Duplicate hazard_type entries found: {duplicates}"
            )
        return self

    @model_validator(mode="after")
    def overall_score_matches_category(self) -> RiskAssessmentReport:
        """Soft-check overall risk score vs. category label."""
        thresholds = {
            RiskCategory.LOW:      (0.0, 0.33),
            RiskCategory.MODERATE: (0.25, 0.55),
            RiskCategory.HIGH:     (0.45, 0.75),
            RiskCategory.EXTREME:  (0.65, 1.0),
        }
        if self.overall_risk_category != RiskCategory.NOT_ASSESSED:
            lo, hi = thresholds[self.overall_risk_category]
            if not (lo <= self.overall_risk_score <= hi + 0.01):
                import warnings
                warnings.warn(
                    f"overall_risk_score {self.overall_risk_score} is outside "
                    f"expected range [{lo}, {hi}] for category "
                    f"'{self.overall_risk_category.value}'",
                    stacklevel=2,
                )
        return self

    @model_validator(mode="after")
    def aggregation_targets_reference_known_hazards(self) -> RiskAssessmentReport:
        """All can_aggregate_with entries must reference a hazard_type present in
        the hazards list (or could be added in future — emit warning only)."""
        known = {h.hazard_type for h in self.hazards}
        for hazard in self.hazards:
            for target in getattr(hazard, "can_aggregate_with", []):
                if target not in known:
                    import warnings
                    warnings.warn(
                        f"Hazard '{hazard.hazard_type}' lists '{target}' in "
                        f"can_aggregate_with but that hazard_type is not in "
                        f"the hazards list.",
                        stacklevel=2,
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


# ---------------------------------------------------------------------------
# Quick smoke-test (run: python models.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json, sys, pathlib

    candidate = pathlib.Path(__file__).parent / "response_improved.json"
    if not candidate.exists():
        print("response_improved.json not found next to models.py — skipping test.")
        sys.exit(0)

    print("Validating response_improved.json …")
    try:
        report = load_report(str(candidate))
    except Exception as exc:
        print(f"VALIDATION FAILED:\n{exc}")
        sys.exit(1)

    print(f"  schema_version : {report.schema_version}")
    print(f"  location       : {report.location.name} ({report.location.lat}, {report.location.lon})")
    print(f"  scenario       : {report.scenario.value}  |  horizon: {report.time_horizon}")
    print(f"  overall risk   : {report.overall_risk_score} ({report.overall_risk_category.value})")
    print(f"  hazards ({len(report.hazards)}):")
    for h in report.hazards:
        assessed = isinstance(h, _HazardBase)
        tag = f"score={h.risk_score:.3f}" if assessed else "NOT ASSESSED"
        print(f"    {h.hazard_type.value:<20} [{h.risk_category.value:<13}] {tag}")

    print("\nAll validations passed ✓")
