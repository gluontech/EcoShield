# src/core/models/surface.py
"""Adjusted surface for dependency tracking (prevents double-counting)."""

from typing import Optional
from pydantic import BaseModel, Field, PrivateAttr, computed_field
from .geometry import DataLineage
from .enums import DataSource


class AdjustedSurface(BaseModel):
    """
    Tracks cumulative adjustments to elevation and water levels.
    Ensures subsidence and SLR are applied exactly once.
    """
    original_elevation_m: float = Field(
        ...,
        description="Original ground elevation"
    )
    subsidence_adjustment_m: float = Field(
        default=0.0,
        ge=0,
        description="Subsidence (m)"
    )
    slr_adjustment_m: float = Field(
        default=0.0,
        ge=0,
        description="Sea level rise (m)"
    )

    # Private tracking (not serialized)
    _subsidence_applied: bool = PrivateAttr(default=False)
    _slr_applied: bool = PrivateAttr(default=False)

    @computed_field
    @property
    def subsidence_adjusted_elevation_m(self) -> float:
        """Ground elevation after subsidence (excludes SLR)."""
        return self.original_elevation_m - self.subsidence_adjustment_m

    def applySubsidence(self, cumulativeM: float) -> None:
        """Apply subsidence adjustment (once only)."""
        if self._subsidence_applied:
            raise ValueError("Subsidence already applied - would double-count")
        self.subsidence_adjustment_m = cumulativeM
        self._subsidence_applied = True

    def applySlr(self, slrM: float) -> None:
        """Apply SLR adjustment (once only)."""
        if self._slr_applied:
            raise ValueError("SLR already applied - would double-count")
        self.slr_adjustment_m = slrM
        self._slr_applied = True

    def getEffectiveFloodDepth(self, waterLevelM: float) -> float:
        """Calculate flood depth with all adjustments."""
        adjustedWater = waterLevelM + self.slr_adjustment_m
        return max(0, adjustedWater - self.adjusted_elevation_m)

    @property
    def subsidenceApplied(self) -> bool:
        """Check if subsidence has been applied."""
        return self._subsidence_applied

    @property
    def slr_applied(self) -> bool:
        """Check if SLR has been applied."""
        return self._slr_applied

    model_config = {"arbitrary_types_allowed": True}


class BuildingAdjustedSurface(BaseModel):
    """
    Per-building surface adjustment (NEW v3.2 - Gap S).
    
    Replaces tile-level AdjustedSurface for structure-level workflow.
    Handles spatially varying subsidence at individual building centroid.
    """
    building_id: str = Field(..., description="Building ID from asset layer")
    
    # Per-building elevation (from GLO-30 at centroid)
    original_elevation_m: float = Field(
        ..., description="Ground elevation at building centroid (m MSL)"
    )
    
    # Per-building subsidence (spatially varying)
    subsidence_rate_mm_yr: float = Field(
        default=0.0,
        description="Annual subsidence rate at building location (mm/yr)"
    )
    subsidence_cumulative_m: float = Field(
        default=0.0, ge=0,
        description="Cumulative subsidence over projection horizon (m)"
    )
    # Gap 4.2: Subsidence source tracking
    subsidence_source: str = Field(
        default="none",
        description="Source: insar_measured, published_literature, interpolated, none"
    )
    
    # SLR (uniform per coastal zone, but only applied to coastal buildings)
    slr_m: float = Field(
        default=0.0, ge=0,
        description="Sea level rise contribution (m). Zero for inland buildings."
    )
    slr_scenario: Optional[str] = Field(None, description="SSP scenario for SLR")
    slr_year: Optional[int] = Field(None, description="Target year for SLR projection")
    
    # Tracking
    _subsidence_applied: bool = PrivateAttr(default=False)
    _slr_applied: bool = PrivateAttr(default=False)
    lineage: Optional[DataLineage] = None
    
    @computed_field
    @property
    def effective_elevation_m(self) -> float:
        """Ground elevation after subsidence (land goes down)."""
        return self.original_elevation_m - self.subsidence_cumulative_m
    
    @computed_field
    @property
    def effective_water_level_increase_m(self) -> float:
        """Total effective water level increase from subsidence + SLR."""
        return self.subsidence_cumulative_m + self.slr_m
    
    def get_flood_depth_at_building(
        self,
        water_level_msl: float,
        ground_floor_offset_m: float = 0.0
    ) -> float:
        """
        Calculate flood depth at a building's ground floor.
        """
        effective_floor = self.effective_elevation_m + ground_floor_offset_m
        adjusted_water = water_level_msl + self.slr_m
        return max(0.0, adjusted_water - effective_floor)
    
    def apply_subsidence(self, rate_mm_yr: float, horizon_years: int = 30) -> None:
        """Apply subsidence (once only to prevent double-count)."""
        if self._subsidence_applied:
            raise ValueError("Subsidence already applied to this building surface")
        self.subsidence_rate_mm_yr = rate_mm_yr
        self.subsidence_cumulative_m = abs(rate_mm_yr) * horizon_years / 1000.0
        self._subsidence_applied = True
    
    def apply_slr(self, slr_m: float, scenario: str = "ssp245", year: int = 2050) -> None:
        """Apply SLR (once only to prevent double-count)."""
        if self._slr_applied:
            raise ValueError("SLR already applied to this building surface")
        self.slr_m = slr_m
        self.slr_scenario = scenario
        self.slr_year = year
        self.slr_scenario = scenario
        self.slr_year = year
        self._slr_applied = True
    
    @property
    def subsidence_applied(self) -> bool:
        """Check if subsidence has been applied."""
        return self._subsidence_applied

    model_config = {"arbitrary_types_allowed": True}
