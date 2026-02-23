# src/core/models/hazard.py
"""Hazard intensity models - pure hazard output (H in HxExV)."""

from datetime import datetime
from typing import Optional, List, Literal, TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator
from .enums import ConfidenceLevel, HazardType
from .geometry import DataLineage

if TYPE_CHECKING:
    from .results import HazardAssessmentResult


class HazardEventContext(BaseModel):
    """Simplified event context embedded in hazard results."""
    event_type: Literal["acute", "chronic"]
    return_period_years: Optional[int] = None
    time_horizon: Optional[int] = None
    slr_scenario: Optional[str] = None
    percentile: Optional[int] = None
    coupled_to_cyclone: Optional[bool] = None


class HazardIntensity(BaseModel):
    """
    Pure hazard intensity output.
    NO building/asset information - separation of HxExV.
    """
    hazard_type: HazardType = Field(..., description="Type of hazard")
    event_context: HazardEventContext = Field(..., description="Event framing")

    # Primary intensity
    intensity_value: float = Field(..., description="Primary intensity value")
    intensity_unit: str = Field(..., description="Unit (m, m/s, C, mm)")

    # Uncertainty bounds
    intensity_p5: Optional[float] = Field(None, description="5th percentile")
    intensity_p95: Optional[float] = Field(None, description="95th percentile")
    uncertainty_type: str = Field(
        default="unspecified",
        description="Uncertainty type"
    )

    # Gap 1.2 / v3.2: Resolution transparency
    climate_forcing_resolution_m: int = Field(
        default=25000,
        ge=1,
        description="Resolution of climate forcing input (NEX-GDDP ~25km). "
                    "All buildings in a ~625km2 grid cell share same climate projection."
    )
    climate_signal_uniformity: str = Field(
        default="grid_cell",
        description="Scale at which climate signal is uniform (grid_cell vs point)"
    )
    downscaling_method: str = Field(
        default="terrain_overlay_only",
        description="Method used to differentiate local hazard (e.g. terrain_overlay_only)"
    )
    native_resolution_m: int = Field(..., ge=1, description="Native resolution of primary hazard layer")
    effective_resolution_m: int = Field(..., ge=1, description="Effective output resolution")

    # Metadata
    data_sources: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.LOW)
    # Gap 4.3: Data lineage
    lineage: Optional[DataLineage] = Field(None, description="Data provenance")

    model_config = {"use_enum_values": True}

    @model_validator(mode='after')
    def ensure_lineage(self) -> "HazardIntensity":
        if self.lineage is None:
            from .enums import DataSource
            source_enum = DataSource.COPERNICUS_GLO30
            if self.data_sources:
                for ds in DataSource:
                    if ds.value in self.data_sources[0].lower():
                        source_enum = ds
                        break
            self.lineage = DataLineage(source=source_enum)
        return self



class CycloneEventParams(BaseModel):
    """
    Cyclone parameters exported for surge coupling.
    Produced by: assess_cyclone()
    Consumed by: assess_storm_surge()
    """
    max_wind_ms: float = Field(..., ge=0, description="Maximum sustained wind (m/s)")
    central_pressure_hpa: float = Field(
        ...,
        ge=850,
        le=1050,
        description="Central pressure (hPa)"
    )
    radius_max_wind_km: float = Field(
        ...,
        ge=10,
        le=200,
        description="Radius of max winds (km)"
    )
    translation_speed_ms: float = Field(
        default=5.0,
        ge=0,
        le=30,
        description="Translation speed (m/s)"
    )
    heading_degrees: float = Field(
        default=315.0,
        ge=0,
        le=360,
        description="Storm heading (degrees)"
    )
    saffir_simpson_category: int = Field(
        ...,
        ge=0,
        le=5,
        description="SS category"
    )
    rainfall_proxy_mm: Optional[float] = Field(
        None,
        ge=0,
        description="Estimated rainfall (mm)"
    )
    # Gap 3.3: Cyclone dynamics
    gust_speed_ms: Optional[float] = Field(
        None, ge=0, description="Peak 3-second gust speed (m/s)"
    )
    duration_hours: Optional[float] = Field(
        None, ge=0, description="Duration of damaging winds > threshold (hours)"
    )


class CycloneAssessmentResponse(BaseModel):
    """
    Combined response for cyclone assessment.
    Wraps tuple return for Pydantic compliance.
    """
    hazard_result: "HazardAssessmentResult"  # Forward reference
    cyclone_params: CycloneEventParams

    model_config = {"arbitrary_types_allowed": True}
