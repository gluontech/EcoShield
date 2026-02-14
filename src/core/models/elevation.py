
# src/core/models/elevation.py
"""Elevation and terrain models."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, computed_field
from .enums import DataSource, ConfidenceLevel
from .geometry import DataLineage


class ElevationResult(BaseModel):
    """
    Elevation query result from DEM.
    Used by: All flood hazards, landslide.
    """
    elevation_m: float = Field(
        ...,
        description="Elevation in meters above MSL"
    )
    uncertainty_m: float = Field(
        default=0.5,
        ge=0,
        description="Vertical uncertainty (m)"
    )
    resolution_m: int = Field(
        default=30,
        ge=1,
        description="Native DEM resolution (m)"
    )
    data_source: DataSource = Field(default=DataSource.COPERNICUS_GLO30)
    is_interpolated: bool = Field(
        default=False,
        description="Whether value was interpolated"
    )

    model_config = {"use_enum_values": True}


class HANDResult(BaseModel):
    """
    Height Above Nearest Drainage (HAND) result.
    Used by: Riverine flood tool.
    """
    hand_value_m: float = Field(
        ...,
        ge=0,
        description="HAND value in meters"
    )
    nearest_drainage_distance_m: float = Field(
        ...,
        ge=0,
        description="Distance to nearest drainage (m)"
    )
    drainage_area_km2: Optional[float] = Field(
        None,
        ge=0,
        description="Upstream drainage area (km2)"
    )
    flow_accumulation: Optional[int] = Field(
        None,
        ge=0,
        description="Flow accumulation value"
    )
    resolution_m: int = Field(default=30, ge=1)
    data_source: DataSource = Field(default=DataSource.COPERNICUS_GLO30)

    @property
    def flood_susceptibility(self) -> str:
        """Classify flood susceptibility from HAND value."""
        if self.hand_value_m < 2:
            return "very_high"
        elif self.hand_value_m < 5:
            return "high"
        elif self.hand_value_m < 10:
            return "moderate"
        elif self.hand_value_m < 20:
            return "low"
        return "very_low"

    model_config = {"use_enum_values": True}


class SlopeResult(BaseModel):
    """
    Terrain slope result.
    Used by: Landslide tool.
    """
    slope_degrees: float = Field(
        ...,
        ge=0,
        le=90,
        description="Slope angle in degrees"
    )
    aspect_degrees: Optional[float] = Field(
        None,
        ge=0,
        le=360,
        description="Slope aspect (0=N, 90=E, 180=S, 270=W)"
    )
    elevation_m: Optional[float] = Field(
        None,
        description="Elevation at center pixel (m)"
    )
    curvature: Optional[float] = Field(
        None,
        description="Terrain curvature"
    )
    resolution_m: int = Field(default=30, ge=1)
    data_source: DataSource = Field(default=DataSource.COPERNICUS_GLO30)
    lineage: Optional[DataLineage] = None

    model_config = {"use_enum_values": True}


class InSARVelocityResult(BaseModel):
    """
    InSAR subsidence velocity result.
    Used by: Subsidence tool.
    """
    velocity_mm_per_year: float = Field(
        ...,
        description="Subsidence velocity (mm/year, negative = sinking)"
    )
    uncertainty_mm_per_year: float = Field(
        default=2.0,
        ge=0,
        description="Velocity uncertainty (mm/year)"
    )
    coherence: float = Field(
        ...,
        ge=0,
        le=1,
        description="InSAR coherence (0-1)"
    )
    observation_period: tuple[str, str] = Field(
        ...,
        description="Observation period (start_date, end_date)"
    )
    num_observations: int = Field(
        ...,
        ge=0,
        description="Number of SAR acquisitions"
    )
    resolution_m: int = Field(default=100, ge=1)
    data_source: DataSource = Field(default=DataSource.SENTINEL1_INSAR)
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MODERATE)

    # Gap 4.2 Fix: Subsidence source flag
    subsidence_source: str = Field(
        default="insar_measured",
        description="Source type: insar_measured, published_literature, interpolated"
    )
    lineage: Optional[DataLineage] = None

    @property
    def is_reliable(self) -> bool:
        """Check if measurement is reliable based on coherence."""
        return self.coherence >= 0.6

    model_config = {"use_enum_values": True}


class FloodReturnPeriodResult(BaseModel):
    """
    GloFAS river discharge return period result.
    Used by: Riverine flood tool.
    """
    discharge_m3s: float = Field(
        ...,
        ge=0,
        description="River discharge (m3/s)"
    )
    return_period_years: int = Field(
        ...,
        ge=2,
        le=1000,
        description="Return period in years"
    )
    upstream_area_km2: Optional[float] = Field(
        None,
        ge=0,
        description="Upstream catchment area (km2)"
    )
    estimated_water_level_m: Optional[float] = Field(
        None,
        ge=0,
        description="Estimated water level above bankfull (m)"
    )
    data_source: DataSource = Field(default=DataSource.GLOFAS_V4)
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MODERATE)
    lineage: Optional[DataLineage] = None

    model_config = {"use_enum_values": True}


class SoilPropertiesResult(BaseModel):
    """
    SoilGrids soil property result.
    Used by: Landslide susceptibility tool.
    """
    clay_fraction: float = Field(
        ...,
        ge=0,
        le=100,
        description="Clay content (%)"
    )
    sand_fraction: float = Field(
        ...,
        ge=0,
        le=100,
        description="Sand content (%)"
    )
    silt_fraction: float = Field(
        ...,
        ge=0,
        le=100,
        description="Silt content (%)"
    )
    organic_carbon_g_kg: Optional[float] = Field(
        None,
        ge=0,
        description="Soil organic carbon (g/kg)"
    )
    depth_cm: int = Field(
        default=30,
        description="Sample depth (cm)"
    )
    data_source: DataSource = Field(default=DataSource.SOILGRIDS_V2)
    lineage: Optional[DataLineage] = None

    model_config = {"use_enum_values": True}


class BathymetryResult(BaseModel):
    """
    GEBCO bathymetry result.
    Used by: Storm surge parametric model.
    """
    depth_m: float = Field(
        ...,
        description="Ocean depth (negative = below sea level)"
    )
    shelf_width_km: Optional[float] = Field(
        None,
        ge=0,
        description="Continental shelf width at location (km)"
    )
    slope_degrees: Optional[float] = Field(
        None,
        ge=0,
        le=90,
        description="Nearshore slope"
    )
    data_source: DataSource = Field(default=DataSource.GEBCO_2024)
    lineage: Optional[DataLineage] = None

    model_config = {"use_enum_values": True}


class NDVIStatisticsResult(BaseModel):
    """
    Sentinel-2 NDVI statistics for a location.
    Used by: Landslide tool (vegetation stability factor).
    """
    ndvi_median: Optional[float] = Field(
        None, ge=-1, le=1,
        description="Median NDVI over date range"
    )
    ndvi_min: Optional[float] = Field(
        None, ge=-1, le=1,
        description="Minimum NDVI (dry season vulnerability)"
    )
    ndvi_std: Optional[float] = Field(
        None, ge=0,
        description="NDVI standard deviation (seasonal variability)"
    )
    pixel_count: int = Field(default=0, description="Valid pixels in sample")
    date_range: str = Field(..., description="Date range queried (YYYY-MM-DD/YYYY-MM-DD)")
    data_source: DataSource = Field(default=DataSource.SENTINEL2_L2A)
    lineage: Optional[DataLineage] = None

    model_config = {"use_enum_values": True}


class LSTStatisticsResult(BaseModel):
    """
    Landsat Land Surface Temperature statistics.
    Used by: Urban heat tool (UHI effect quantification).
    """
    lst_median_c: Optional[float] = Field(
        None,
        description="Median LST in Celsius over date range"
    )
    lst_p95_c: Optional[float] = Field(
        None,
        description="95th percentile LST (extreme heat days)"
    )
    lst_night_median_c: Optional[float] = Field(
        None,
        description="Median nighttime LST (nocturnal UHI)"
    )
    uhi_intensity_c: Optional[float] = Field(
        None, ge=0,
        description="Estimated UHI intensity (LST minus rural baseline)"
    )
    pixel_count: int = Field(default=0, description="Valid pixels in sample")
    date_range: str = Field(..., description="Date range queried")
    data_source: DataSource = Field(default=DataSource.LANDSAT_C2L2)
    lineage: Optional[DataLineage] = None

    model_config = {"use_enum_values": True}


class WBGTComponentsResult(BaseModel):
    """
    ERA5-Land WBGT (Wet Bulb Globe Temperature) statistics.
    Used by: Urban heat tool (heat stress assessment).
    """
    mean_wbgt_c: float = Field(..., description="Mean daily max WBGT (C)")
    max_wbgt_c: float = Field(..., description="Peak WBGT (C)")
    days_risk_high: int = Field(default=0, ge=0, description="Days with WBGT > 28C (High Risk)")
    days_risk_extreme: int = Field(default=0, ge=0, description="Days with WBGT > 32C (Extreme)")
    data_source: DataSource = Field(default=DataSource.ERA5_LAND)
    lineage: Optional[DataLineage] = None

    model_config = {"use_enum_values": True}
