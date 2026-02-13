# src/core/models/exposure.py
"""Exposure profile models (E in HxExV)."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, computed_field
from .geometry import Location, DataLineage
from .asset import StructuralCharacteristics, BuildingFootprint, BuildingHeight
from .enums import BuildingOccupancy, DataSource



class UrbanContext(BaseModel):
    """Urban morphology from satellite indices."""
    ndvi: float = Field(..., ge=-1, le=1, description="Vegetation index")
    ndbi: float = Field(..., ge=-1, le=1, description="Built-up index")
    impervious_fraction: float = Field(
        ..., 
        ge=0, 
        le=1, 
        description="Impervious surface fraction"
    )
    building_density_per_km2: Optional[float] = Field(
        None, ge=0,
        description="Building count per km2 from Open Buildings"
    )


class ExposureProfile(BaseModel):
    """
    Structure-level exposure: what is at risk and where.
    
    v3.1: Now anchored to a specific building from the asset layer.
    """
    location: Location
    
    # --- Core: the building being assessed ---
    structure: StructuralCharacteristics = Field(
        ...,
        description="The physical building/asset being assessed"
    )
    
    # Elevation context (from GLO-30 at building centroid)
    elevation_m: float = Field(..., description="Ground elevation (m above MSL)")
    elevation_source: str = Field(default="copernicus_glo30")
    elevation_uncertainty_m: float = Field(
        default=0.5,
        ge=0,
        description="Vertical uncertainty (m)"
    )

    # Context
    urban_context: Optional[UrbanContext] = None
    slope_degrees: Optional[float] = Field(
        None,
        ge=0,
        le=90,
        description="Terrain slope"
    )
    coastal_distance_m: Optional[float] = Field(
        None,
        ge=0,
        description="Distance to coast (m)"
    )
    coastal_type: Optional[str] = None

    # Tracking
    adjustments_applied: List[str] = Field(
        default_factory=list,
        description="Adjustments applied"
    )
