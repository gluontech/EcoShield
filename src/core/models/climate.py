# src/core/models/climate.py
"""Climate data models for NEX-GDDP-CMIP6 and ERA5-Land outputs."""

from datetime import datetime
from typing import Optional, Dict

from pydantic import BaseModel, Field
from .enums import SSPScenario, ConfidenceLevel, DataSource
from .geometry import DataLineage



class ExtremePrecipitationResult(BaseModel):
    """
    Result from extreme precipitation analysis.
    Used by: Riverine Flood, Landslide tools.
    """
    precip_mm_per_day: float = Field(
        ...,
        ge=0,
        description="Precipitation intensity (mm/day)"
    )
    return_period_years: int = Field(
        ...,
        ge=2,
        le=1000,
        description="Return period in years"
    )
    uncertainty_p5: float = Field(
        ...,
        ge=2,
        le=1000,
        description="Return period in years"
    )
    uncertainty_p95: float = Field(
        ...,
        ge=0,
        description="95th percentile (upper bound)"
    )
    scenario: SSPScenario = Field(
        default=SSPScenario.SSP245,
        description="Climate scenario"
    )
    period: str = Field(
        default="historical",
        description="Time period (historical or future range)"
    )
    data_source: DataSource = Field(
        default=DataSource.NEX_GDDP_CMIP6,
        description="Data source"
    )
    ensemble_size: int = Field(
        default=1,
        ge=1,
        description="Number of models in ensemble"
    )
    confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.MODERATE,
        description="Confidence level"
    )
    # Gap 4.3: Data lineage
    lineage: Optional[DataLineage] = Field(None, description="Data provenance")

    model_config = {"use_enum_values": True}


class HistoricalClimateResult(BaseModel):
    """
    Historical climate statistics.
    Used by: Urban Heat baseline, climate context.
    """
    variable: str = Field(
        ...,
        description="Climate variable (tas, pr, tasmax, tasmin)"
    )
    annual_mean: float = Field(..., description="Annual mean value")
    monthly_means: Dict[int, float] = Field(
        default_factory=dict,
        description="Monthly means (1-12)"
    )
    percentile_90: float = Field(..., description="90th percentile")
    percentile_95: float = Field(..., description="95th percentile")
    percentile_99: float = Field(..., description="99th percentile")
    std_dev: float = Field(..., ge=0, description="Standard deviation")
    baseline_period: tuple[int, int] = Field(
        default=(1991, 2020),
        description="Baseline period (start, end year)"
    )
    unit: str = Field(..., description="Unit (C, mm/day, etc.)")
    data_source: DataSource = Field(default=DataSource.NEX_GDDP_CMIP6)

    model_config = {"use_enum_values": True}


class ClimateProjectionResult(BaseModel):
    """
    Climate projection results for future scenarios.
    Used by: Urban Heat projections, future flood analysis.
    """
    variable: str = Field(..., description="Climate variable")
    baseline_mean: float = Field(..., description="Baseline period mean")
    future_mean: float = Field(..., description="Future period mean")
    change: float = Field(..., description="Absolute change")
    change_percent: Optional[float] = Field(
        None,
        description="Percent change (for precip)"
    )
    scenario: SSPScenario = Field(..., description="SSP scenario")
    future_period: str = Field(
        ...,
        description="Future period (e.g., '2041-2060')"
    )
    uncertainty_p5: float = Field(..., description="5th percentile change")
    uncertainty_p95: float = Field(..., description="95th percentile change")
    ensemble_size: int = Field(default=1, ge=1)
    hot_days_change: Optional[int] = Field(
        None,
        description="Change in days above threshold (for temperature)"
    )
    unit: str = Field(..., description="Unit")
    data_source: DataSource = Field(default=DataSource.NEX_GDDP_CMIP6)
    confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.MODERATE,
        description="Confidence level"
    )
    # Gap 4.3: Data lineage
    lineage: Optional[DataLineage] = Field(None, description="Data provenance")
    
    model_config = {"use_enum_values": True}



class TemperatureBaselineResult(BaseModel):
    """Temperature baseline for urban heat analysis."""
    location_lat: float
    location_lon: float
    annual_mean_c: float = Field(..., description="Annual mean C")
    monthly_means_c: Dict[int, float] = Field(
        default_factory=dict,
        description="Monthly means C (1-12)"
    )
    p90_temperature_c: float = Field(..., description="90th percentile C")
    p95_temperature_c: float = Field(..., description="95th percentile C")
    heat_wave_threshold_c: float = Field(
        default=35.0,
        description="Heat wave threshold C"
    )
    data_source: DataSource = Field(default=DataSource.NEX_GDDP_CMIP6)

    model_config = {"use_enum_values": True}
