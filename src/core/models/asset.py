# src/core/models/asset.py
"""
Building footprint and structural characterization models.

Data sources:
- Google Open Buildings V3: footprint polygons, area, confidence (GEE / GCS)
- Google Open Buildings 2.5D Temporal: building heights at 4m resolution (GEE / GCS)
- Overture Maps Buildings: conflated footprints + OSM attributes (S3 / DuckDB)
- Copernicus GLO-30: ground elevation for each building

These models represent the physical asset that is exposed to climate hazards.
Combined with hazard intensity and vulnerability curves, they enable
structure-level damage estimation (HxE×V per building).
"""

from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from pydantic import BaseModel, Field, computed_field
from .enums import (
    DataSource, BuildingMaterial, BuildingOccupancy, VulnerabilityClass,
    ConfidenceLevel
)
from .geometry import Location, BoundingBox


class BuildingFootprint(BaseModel):
    """
    Individual building polygon from Google Open Buildings V3 or Overture Maps.
    
    This is the fundamental unit of asset-level risk assessment.
    Each footprint maps to exactly one structure with its own HxE×V calculation.
    
    Resolution: ~50cm (Google) / varies (Overture conflated)
    Coverage: All 7 SEA target cities
    """
    # Identity
    building_id: str = Field(..., description="Unique building identifier (Plus Code or Overture GERS ID)")
    source: DataSource = Field(..., description="Footprint data source")
    
    # Geometry
    centroid: Location = Field(..., description="Building centroid (lat/lon)")
    footprint_wkt: Optional[str] = Field(None, description="WKT polygon of building outline")
    area_m2: float = Field(..., gt=0, description="Footprint area in square meters")
    
    # Google Open Buildings specific
    confidence: float = Field(
        default=0.0,
        ge=0.0, le=1.0,
        description="ML detection confidence (0.65-1.0 for Google, null for Microsoft/OSM)"
    )
    
    # Overture Maps specific (when available)
    overture_id: Optional[str] = Field(None, description="Overture GERS ID for cross-reference")
    osm_id: Optional[str] = Field(None, description="OpenStreetMap way/relation ID if from OSM")
    name: Optional[str] = Field(None, description="Building name (usually from OSM/Overture)")
    address: Optional[str] = Field(None, description="Building address")
    name_aliases: List[str] = Field(
        default_factory=list,
        description="Alternate names in other languages (from Overture names.common)"
    )

    model_config = {"arbitrary_types_allowed": True}


class BuildingHeight(BaseModel):
    """
    Building height from Google Open Buildings 2.5D Temporal dataset.
    
    Derived from Sentinel-2 imagery using teacher-student ML model.
    Resolution: 4m effective (raster at 0.5m).
    MAE: ~1.5m (less than one storey).
    Temporal: annual snapshots 2016-2023.
    """
    height_m: float = Field(..., ge=0, le=500, description="Estimated building height (meters above ground)")
    height_source: DataSource = Field(
        default=DataSource.GOOGLE_OPEN_BUILDINGS_2_5D,
        description="Height data source"
    )
    height_year: int = Field(
        default=2023,
        ge=2016, le=2030,
        description="Year of height observation (2016-2023)"
    )
    height_uncertainty_m: float = Field(
        default=1.5,
        ge=0,
        description="Height MAE (1.5m default from Google validation)"
    )
    # Gap 4.1 Fix: Expose confidence for uncertainty propagation
    height_confidence: float = Field(
        default=0.7,
        ge=0, le=1,
        description="Confidence in height estimation (derived from probability)"
    )
    building_presence: float = Field(
        default=1.0,
        ge=0, le=1,
        description="Building presence probability for this year"
    )
    num_floors: Optional[int] = Field(
        None, ge=1, le=200,
        description="Actual floor count from Overture/OSM (takes priority over height estimation)"
    )

    @computed_field
    @property
    def estimated_stories(self) -> int:
        """Number of stories: prefer actual num_floors, else estimate from height."""
        if self.num_floors:
            return self.num_floors
        return max(1, round(self.height_m / 3.0))


class StructuralCharacteristics(BaseModel):
    """
    Physical and structural properties of a building.
    
    Combines ML-derived data (footprint, height) with:
    - Inferred attributes (material from OSM tags or regional defaults)
    - User-provided data (for premium assessments)
    - Regional defaults (SEA-calibrated by city)
    
    These characteristics determine which vulnerability curve to apply.
    """
    # From building footprint + height data
    footprint: BuildingFootprint
    height: Optional[BuildingHeight] = None
    
    # Structural classification — drives vulnerability curve selection
    material: BuildingMaterial = Field(
        default=BuildingMaterial.UNKNOWN,
        description="Primary structural material"
    )
    occupancy: BuildingOccupancy = Field(
        default=BuildingOccupancy.UNKNOWN,
        description="Building occupancy type"
    )
    vulnerability_class: VulnerabilityClass = Field(
        default=VulnerabilityClass.CLASS_III_MASONRY,
        description="JRC vulnerability class (I-IV)"
    )
    
    # Elevation context (from GLO-30 at building centroid)
    ground_elevation_m: float = Field(
        default=0.0,
        description="Ground elevation at building centroid (m above MSL, from GLO-30)"
    )
    ground_floor_height_m: float = Field(
        default=0.0,
        ge=0,
        description="Floor elevation above ground grade (meters). Common: 0.3-1.2m in SEA"
    )
    
    # User-provided enrichment (optional — premium tier)
    construction_year: Optional[int] = Field(None, ge=1800, le=2100)
    has_basement: bool = Field(default=False, description="Rare in SEA, common in commercial")
    has_stilts: bool = Field(default=False, description="Raised on stilts/piles (common in flood-prone SEA)")
    roof_type: Optional[str] = Field(None, description="flat, pitched, metal, tile, thatch")
    wall_material: Optional[str] = Field(None, description="Specific wall material if known")
    
    # Derived / inferred flag
    material_inferred: bool = Field(
        default=True,
        description="True if material was inferred from region/area/height, not observed"
    )
    classification_source: str = Field(
        default="regional_default",
        description="How structural classification was determined: osm_tags, regional_default, user_provided, ml_classified"
    )
    
    # Replacement value
    replacement_value_usd: Optional[float] = Field(
        None, ge=0,
        description="Estimated replacement value (USD). From JRC max damage values if not user-provided."
    )
    replacement_value_source: str = Field(
        default="jrc_country_estimate",
        description="Value source: jrc_country_estimate, user_provided, market_data"
    )
    
    @computed_field
    @property
    def num_stories(self) -> int:
        """Number of stories from height or default."""
        if self.height:
            return self.height.estimated_stories
        return 1  # Default single-story for unknown

    @computed_field
    @property
    def effective_ground_floor_m(self) -> float:
        """Effective first-floor elevation above MSL."""
        base = self.ground_elevation_m + self.ground_floor_height_m
        if self.has_stilts:
            base += 1.5  # Typical stilt height in SEA
        return base


class BuildingCluster(BaseModel):
    """
    A spatial cluster of buildings within a hazard analysis tile.
    
    For portfolio-level assessment, buildings are grouped into
    analysis tiles (~100m x 100m). Each tile shares the same
    hazard intensity but buildings have individual vulnerability.
    """
    tile_id: str = Field(..., description="Analysis tile ID (S2 cell or grid ref)")
    bounds: BoundingBox
    buildings: List[StructuralCharacteristics] = Field(
        default_factory=list,
        description="Buildings in this tile"
    )
    
    # Tile-level aggregated stats
    building_count: int = Field(default=0, ge=0)
    total_footprint_area_m2: float = Field(default=0.0, ge=0)
    mean_building_height_m: Optional[float] = None
    dominant_material: BuildingMaterial = Field(default=BuildingMaterial.UNKNOWN)
    dominant_occupancy: BuildingOccupancy = Field(default=BuildingOccupancy.UNKNOWN)
    total_replacement_value_usd: Optional[float] = Field(None, ge=0)
    
    @computed_field
    @property
    def building_density_per_km2(self) -> float:
        """Buildings per square kilometer.
        
        FIX v3.2 (Gap O): Uses cosine-corrected area_km2 from BoundingBox.
        """
        return self.building_count / max(self.bounds.area_km2, 0.001)


# --- SEA Regional Defaults ---
# Used when structural characteristics cannot be determined from data sources

SEA_MATERIAL_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "ho_chi_minh_city": {
        "dominant_material": BuildingMaterial.MASONRY_UNREINFORCED,
        "material_distribution": {
            BuildingMaterial.CONCRETE_REINFORCED: 0.35,
            BuildingMaterial.MASONRY_UNREINFORCED: 0.40,
            BuildingMaterial.WOOD_FRAME: 0.15,
            BuildingMaterial.BAMBOO_THATCH: 0.05,
            BuildingMaterial.MUD_ADOBE: 0.05,
        },
        "mean_ground_floor_height_m": 0.3,
        "stilts_fraction": 0.05,
    },
    "hanoi": {
        "dominant_material": BuildingMaterial.MASONRY_UNREINFORCED,
        "material_distribution": {
            BuildingMaterial.CONCRETE_REINFORCED: 0.30,
            BuildingMaterial.MASONRY_UNREINFORCED: 0.45,
            BuildingMaterial.WOOD_FRAME: 0.15,
            BuildingMaterial.BAMBOO_THATCH: 0.05,
            BuildingMaterial.MUD_ADOBE: 0.05,
        },
        "mean_ground_floor_height_m": 0.3,
        "stilts_fraction": 0.03,
    },
    "jakarta": {
        "dominant_material": BuildingMaterial.MASONRY_UNREINFORCED,
        "material_distribution": {
            BuildingMaterial.CONCRETE_REINFORCED: 0.25,
            BuildingMaterial.MASONRY_UNREINFORCED: 0.35,
            BuildingMaterial.WOOD_FRAME: 0.20,
            BuildingMaterial.BAMBOO_THATCH: 0.10,
            BuildingMaterial.MUD_ADOBE: 0.10,
        },
        "mean_ground_floor_height_m": 0.2,
        "stilts_fraction": 0.08,
    },
    "manila": {
        "dominant_material": BuildingMaterial.CONCRETE_REINFORCED,
        "material_distribution": {
            BuildingMaterial.CONCRETE_REINFORCED: 0.40,
            BuildingMaterial.MASONRY_UNREINFORCED: 0.25,
            BuildingMaterial.WOOD_FRAME: 0.15,
            BuildingMaterial.BAMBOO_THATCH: 0.10,
            BuildingMaterial.MUD_ADOBE: 0.10,
        },
        "mean_ground_floor_height_m": 0.3,
        "stilts_fraction": 0.10,
    },
    "bangkok": {
        "dominant_material": BuildingMaterial.CONCRETE_REINFORCED,
        "material_distribution": {
            BuildingMaterial.CONCRETE_REINFORCED: 0.45,
            BuildingMaterial.MASONRY_UNREINFORCED: 0.30,
            BuildingMaterial.WOOD_FRAME: 0.15,
            BuildingMaterial.BAMBOO_THATCH: 0.05,
            BuildingMaterial.MUD_ADOBE: 0.05,
        },
        "mean_ground_floor_height_m": 0.3,
        "stilts_fraction": 0.12,
    },
    "singapore": {
        "dominant_material": BuildingMaterial.CONCRETE_REINFORCED,
        "material_distribution": {
            BuildingMaterial.CONCRETE_REINFORCED: 0.70,
            BuildingMaterial.MASONRY_UNREINFORCED: 0.20,
            BuildingMaterial.STEEL_FRAME: 0.08,
            BuildingMaterial.WOOD_FRAME: 0.02,
        },
        "mean_ground_floor_height_m": 0.5,
        "stilts_fraction": 0.02,
    },
}
