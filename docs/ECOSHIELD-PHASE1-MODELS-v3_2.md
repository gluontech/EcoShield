# EcoShield Phase 1: Core Models — v3.2

## Overview
This phase creates the complete Pydantic model layer for **asset-level (~100m) climate risk
intelligence**. Every function in the system must accept and return these validated models—no
plain dictionaries allowed. Models are structured around the **H×E×V framework**:

- **Hazard (H)**: Physical climate hazard intensity at a location
- **Exposure (E)**: What asset/structure exists there (footprint, height, elevation, value)
- **Vulnerability (V)**: How susceptible that specific structure is to damage (material, type, curves)

The product is **structure-level risk**: damage ratio, expected annual loss, and risk tier
for each individual building or asset.

### Files to Create

```
src/core/models/
├── __init__.py
├── enums.py              # Enumerations
├── geometry.py           # Location models
├── asset.py              # Building footprints + structural characteristics (NEW v3.1)
├── climate.py            # Climate data models
├── elevation.py          # Elevation/DEM models
├── events.py             # Event context
├── hazard.py             # Hazard intensity
├── exposure.py           # Structure-level exposure profile (ENHANCED v3.1)
├── vulnerability.py      # Vulnerability curves + damage assessment (ENHANCED v3.1)
├── surface.py            # Adjusted surface
├── results.py            # Assessment results + structure-level risk (ENHANCED v3.1)
└── composite.py          # Composite risk
```

---

## 1. Enumerations (enums.py)

```python
# src/core/models/enums.py
"""Enumerations for the EcoShield hazard system."""

from enum import Enum


class EventType(str, Enum):
    """Event classification for probabilistic coherence."""
    CHRONIC = "chronic"
    ACUTE = "acute"


class HazardType(str, Enum):
    """Supported hazard types — v3.2: 8 hazards (added PLUVIAL_FLOOD)."""
    RIVERINE_FLOOD = "riverine_flood"
    COASTAL_FLOOD = "coastal_flood"
    PLUVIAL_FLOOD = "pluvial_flood"          # NEW v3.2 (Gap M) — surface water from intense rainfall
    STORM_SURGE = "storm_surge"
    TROPICAL_CYCLONE = "tropical_cyclone"
    LANDSLIDE = "landslide"
    SUBSIDENCE = "subsidence"
    URBAN_HEAT = "urban_heat"


class ConfidenceLevel(str, Enum):
    """Assessment confidence level."""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class RiskTier(str, Enum):
    """Risk classification tier."""
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"
    CRITICAL = "Critical"


class SSPScenario(str, Enum):
    """SSP climate scenarios."""
    SSP126 = "ssp126"
    SSP245 = "ssp245"
    SSP370 = "ssp370"
    SSP585 = "ssp585"


class DataSource(str, Enum):
    """Data source identifiers — v3.1 API-first (all programmatic access)."""
    # --- Hazard data sources (v3.0) ---
    NEX_GDDP_CMIP6 = "nex_gddp_cmip6"       # NASA downscaled CMIP6 (AWS S3 / THREDDS)
    ERA5_LAND = "era5_land"                    # ECMWF reanalysis (CDS API)
    COPERNICUS_GLO30 = "copernicus_glo30"      # DEM 30m (AWS S3 OpenData)
    SENTINEL1_INSAR = "sentinel1_insar"        # InSAR deformation (ASF DAAC API)
    SENTINEL2_L2A = "sentinel2_l2a"            # NDVI vegetation (Planetary Computer STAC)
    LANDSAT_C2L2 = "landsat_c2l2"              # Surface temperature (PC STAC / GEE)
    IBTRACS_V04 = "ibtracs_v04"                # Cyclone best tracks (NCEI REST)
    IPCC_AR6 = "ipcc_ar6"                      # Sea level rise tables (static)
    GLOFAS_V4 = "glofas_v4"                    # River discharge (CDS API)
    SOILGRIDS_V2 = "soilgrids_v2"              # Soil clay/sand (ISRIC REST API)
    GEBCO_2024 = "gebco_2024"                  # Bathymetry (BODC WCS / NetCDF)
    
    # --- Asset / Exposure data sources (NEW v3.1) ---
    GOOGLE_OPEN_BUILDINGS_V3 = "google_open_buildings_v3"  # Building footprints (GEE / GCS)
    GOOGLE_OPEN_BUILDINGS_2_5D = "google_open_buildings_2_5d"  # Building heights (GEE / GCS)
    OVERTURE_MAPS_BUILDINGS = "overture_maps_buildings"    # Conflated footprints+attrs (S3/DuckDB)
    
    # --- Vulnerability data sources (NEW v3.1) ---
    JRC_FLOOD_DAMAGE = "jrc_flood_damage"      # Global depth-damage curves (JRC/World Bank)


class BuildingMaterial(str, Enum):
    """Primary structural material classification.
    
    Based on JRC 4-class vulnerability system aligned with SEA building stock.
    Maps to JRC depth-damage curves for flood vulnerability.
    """
    # JRC Class I — Non-structured / informal
    MUD_ADOBE = "mud_adobe"              # Mud, adobe, informal structures
    BAMBOO_THATCH = "bamboo_thatch"      # Bamboo, thatch, nipa (common SEA rural)
    
    # JRC Class II — Wood-frame
    WOOD_FRAME = "wood_frame"            # Timber/wood frame (common SEA residential)
    
    # JRC Class III — Unreinforced masonry/concrete
    MASONRY_UNREINFORCED = "masonry_unreinforced"  # Brick, block, unreinforced concrete
    
    # JRC Class IV — Reinforced concrete/steel
    CONCRETE_REINFORCED = "concrete_reinforced"    # Reinforced concrete frame
    STEEL_FRAME = "steel_frame"                    # Steel frame (commercial/industrial)
    
    UNKNOWN = "unknown"


class BuildingOccupancy(str, Enum):
    """Building occupancy classification (HAZUS-compatible)."""
    RESIDENTIAL_SINGLE = "res_single"       # Single-family house
    RESIDENTIAL_MULTI = "res_multi"         # Multi-family / apartment
    RESIDENTIAL_INFORMAL = "res_informal"   # Informal settlement / slum
    COMMERCIAL = "commercial"               # Office, retail, services
    INDUSTRIAL = "industrial"               # Factory, warehouse
    INSTITUTIONAL = "institutional"         # Hospital, school, government
    INFRASTRUCTURE = "infrastructure"       # Utilities, transport
    AGRICULTURAL = "agricultural"           # Farm structures
    MIXED_USE = "mixed_use"                 # Combined residential + commercial
    UNKNOWN = "unknown"


class VulnerabilityClass(str, Enum):
    """JRC vulnerability classification for flood damage curves.
    
    From Huizinga et al. (2017) + Jongman et al. (2012):
    4 classes based on construction material, each with distinct
    depth-damage curves. SEA-specific calibration needed.
    """
    CLASS_I_INFORMAL = "class_i"      # Mud/adobe/informal — highest vulnerability
    CLASS_II_WOOD = "class_ii"        # Wood/bamboo/timber — high vulnerability
    CLASS_III_MASONRY = "class_iii"   # Unreinforced masonry/concrete — moderate
    CLASS_IV_REINFORCED = "class_iv"  # Reinforced concrete/steel — lowest vulnerability
```

---

## 2. Geometry Models (geometry.py)

```python
# src/core/models/geometry.py
"""Location and geometry models."""

from typing import Optional
from pydantic import BaseModel, Field, field_validator, computed_field


class Location(BaseModel):
    """Geographic location with validation."""
    
    lat: float = Field(
        ..., 
        ge=-90, 
        le=90, 
        description="Latitude in decimal degrees"
    )
    lon: float = Field(
        ..., 
        ge=-180, 
        le=180, 
        description="Longitude in decimal degrees"
    )
    
    @field_validator('lat')
    @classmethod
    def validate_sea_bounds(cls, v: float) -> float:
        """Warn if outside typical SEA bounds."""
        if not (-15 <= v <= 30):
            # Log warning but allow - might be testing
            pass
        return v
    
    @field_validator('lon')
    @classmethod
    def validate_sea_lon_bounds(cls, v: float) -> float:
        """Warn if outside typical SEA bounds."""
        if not (90 <= v <= 150):
            pass
        return v
    
    def to_tuple(self) -> tuple[float, float]:
        """Return as (lat, lon) tuple."""
        return (self.lat, self.lon)
    
    model_config = {"frozen": True}


class BoundingBox(BaseModel):
    """Geographic bounding box — v3.2: added area_degrees, area_km2 (Gap O fix)."""
    
    min_lat: float = Field(..., ge=-90, le=90)
    max_lat: float = Field(..., ge=-90, le=90)
    min_lon: float = Field(..., ge=-180, le=180)
    max_lon: float = Field(..., ge=-180, le=180)
    
    @field_validator('max_lat')
    @classmethod
    def validate_lat_order(cls, v: float, info) -> float:
        """Ensure max_lat >= min_lat."""
        if 'min_lat' in info.data and v < info.data['min_lat']:
            raise ValueError("max_lat must be >= min_lat")
        return v
    
    def contains(self, location: Location) -> bool:
        """Check if location is within bounding box."""
        return (
            self.min_lat <= location.lat <= self.max_lat and
            self.min_lon <= location.lon <= self.max_lon
        )
    
    @computed_field
    @property
    def area_degrees(self) -> float:
        """Area in square degrees (for quick relative comparisons)."""
        return (self.max_lat - self.min_lat) * (self.max_lon - self.min_lon)
    
    @computed_field
    @property
    def area_km2(self) -> float:
        """Area in square kilometers with cosine-latitude correction.
        
        FIX v3.2 (Gap O): Previously used equatorial constant 12321 which
        introduces ~6% error at SEA latitudes (5-20°N). Now uses proper
        cosine(mid_lat) correction for longitude degree width.
        
        1° latitude ≈ 111.32 km (constant)
        1° longitude ≈ 111.32 × cos(lat) km (varies with latitude)
        """
        import math
        mid_lat_rad = math.radians((self.min_lat + self.max_lat) / 2)
        km_per_deg_lat = 111.32
        km_per_deg_lon = 111.32 * math.cos(mid_lat_rad)
        height_km = (self.max_lat - self.min_lat) * km_per_deg_lat
        width_km = (self.max_lon - self.min_lon) * km_per_deg_lon
        return height_km * width_km
```

---

## 3. Asset & Building Models (asset.py) — NEW v3.1

```python
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
structure-level damage estimation (H×E×V per building).
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, computed_field
from shapely.geometry import Polygon
from .enums import (
    DataSource, BuildingMaterial, BuildingOccupancy, VulnerabilityClass,
    ConfidenceLevel
)
from .geometry import Location, BoundingBox


class BuildingFootprint(BaseModel):
    """
    Individual building polygon from Google Open Buildings V3 or Overture Maps.
    
    This is the fundamental unit of asset-level risk assessment.
    Each footprint maps to exactly one structure with its own H×E×V calculation.
    
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
    building_presence: float = Field(
        default=1.0,
        ge=0, le=1,
        description="Building presence probability for this year"
    )
    
    @computed_field
    @property
    def estimated_stories(self) -> int:
        """Estimate number of stories (3.0m per story for SEA buildings)."""
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
    analysis tiles (~100m × 100m). Each tile shares the same
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
        
        FIX v3.2 (Gap O): Uses cosine-corrected area_km2 from BoundingBox
        instead of equatorial constant 12321. Previous calculation introduced
        ~6% area error at SEA latitudes (5-20°N).
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
```

---

## 4. Climate Data Models (climate.py)

```python
# src/core/models/climate.py
"""Climate data models for NEX-GDDP-CMIP6 and ERA5-Land outputs."""

from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from .enums import SSPScenario, ConfidenceLevel, DataSource


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
        ge=0,
        description="5th percentile (lower bound)"
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
    unit: str = Field(..., description="Unit (°C, mm/day, etc.)")
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
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MODERATE)
    
    model_config = {"use_enum_values": True}


class TemperatureBaselineResult(BaseModel):
    """
    Temperature baseline for urban heat analysis.
    """
    location_lat: float
    location_lon: float
    annual_mean_c: float = Field(..., description="Annual mean °C")
    monthly_means_c: Dict[int, float] = Field(
        default_factory=dict,
        description="Monthly means °C (1-12)"
    )
    p90_temperature_c: float = Field(..., description="90th percentile °C")
    p95_temperature_c: float = Field(..., description="95th percentile °C")
    heat_wave_threshold_c: float = Field(
        default=35.0,
        description="Heat wave threshold °C"
    )
    data_source: DataSource = Field(default=DataSource.NEX_GDDP_CMIP6)
    
    model_config = {"use_enum_values": True}
```

---

## 4. Elevation Models (elevation.py) — NEW

```python
# src/core/models/elevation.py
"""Elevation and terrain models."""

from typing import Optional, List
from pydantic import BaseModel, Field
from .enums import DataSource, ConfidenceLevel


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
        description="Upstream drainage area (km²)"
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
    curvature: Optional[float] = Field(
        None,
        description="Terrain curvature"
    )
    resolution_m: int = Field(default=30, ge=1)
    data_source: DataSource = Field(default=DataSource.COPERNICUS_GLO30)
    
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
        ge=1,
        description="Number of SAR acquisitions"
    )
    resolution_m: int = Field(default=100, ge=1)
    data_source: DataSource = Field(default=DataSource.SENTINEL1_INSAR)
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MODERATE)
    
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
        description="River discharge (m³/s)"
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
        description="Upstream catchment area (km²)"
    )
    estimated_water_level_m: Optional[float] = Field(
        None,
        ge=0,
        description="Estimated water level above bankfull (m)"
    )
    data_source: DataSource = Field(default=DataSource.GLOFAS_V4)
    
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
    
    model_config = {"use_enum_values": True}


class NDVIStatisticsResult(BaseModel):
    """
    Sentinel-2 NDVI statistics for a location.
    Used by: Landslide tool (vegetation stability factor).
    Source: Sentinel-2 L2A via Planetary Computer STAC.
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
    
    model_config = {"use_enum_values": True}


class LSTStatisticsResult(BaseModel):
    """
    Landsat Land Surface Temperature statistics.
    Used by: Urban heat tool (UHI effect quantification).
    Source: Landsat C02 L2 via Planetary Computer STAC or Google Earth Engine.
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
    
    model_config = {"use_enum_values": True}


class WBGTComponentsResult(BaseModel):
    """
    ERA5-Land meteorological components for WBGT calculation.
    Used by: Urban heat tool (wet-bulb globe temperature for heat stress).
    Source: ERA5-Land via CDS API.
    """
    t2m_c: float = Field(..., description="2m air temperature (°C)")
    dewpoint_c: float = Field(..., description="2m dewpoint temperature (°C)")
    wind_ms: float = Field(..., ge=0, description="10m wind speed (m/s)")
    solar_wm2: float = Field(..., ge=0, description="Surface solar radiation (W/m²)")
    relative_humidity_pct: Optional[float] = Field(
        None, ge=0, le=100,
        description="Relative humidity (%)"
    )
    period: str = Field(..., description="Averaging period (e.g. '2020-2023 JJA')")
    data_source: DataSource = Field(default=DataSource.ERA5_LAND)
    
    model_config = {"use_enum_values": True}
```

---

## 5. Event Context (events.py)

```python
# src/core/models/events.py
"""Event framework for probabilistic coherence."""

from typing import Optional
from pydantic import BaseModel, Field, model_validator
from .enums import EventType, SSPScenario


class EventContext(BaseModel):
    """
    Event context ensuring probabilistic coherence.
    Acute events use return periods, chronic use time horizons.
    """
    event_type: EventType = Field(..., description="Event classification")
    return_period: Optional[int] = Field(
        None, 
        ge=10, 
        le=500, 
        description="For acute events (years)"
    )
    time_horizon: Optional[int] = Field(
        None, 
        ge=2024, 
        le=2100, 
        description="For chronic events (year)"
    )
    slr_scenario: SSPScenario = Field(
        default=SSPScenario.SSP245, 
        description="SSP scenario"
    )
    percentile: Optional[int] = Field(
        None, 
        ge=1, 
        le=99, 
        description="Percentile for chronic hazards"
    )

    @model_validator(mode='after')
    def validate_event_requirements(self):
        if self.event_type == EventType.ACUTE and self.return_period is None:
            raise ValueError("Acute events require return_period")
        if self.event_type == EventType.CHRONIC and self.time_horizon is None:
            raise ValueError("Chronic events require time_horizon")
        return self
    
    model_config = {"use_enum_values": True}
```

---

## 6. Hazard Intensity (hazard.py)

```python
# src/core/models/hazard.py
"""Hazard intensity models - pure hazard output (H in H×E×V)."""

from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from .enums import ConfidenceLevel, HazardType


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
    NO building/asset information - separation of H×E×V.
    
    v3.2 (Gap H): Added climate_forcing_resolution_m to make resolution
    gap transparent. NEX-GDDP at 0.25° (~25 km) vs buildings at sub-meter.
    """
    hazard_type: HazardType = Field(..., description="Type of hazard")
    event_context: HazardEventContext = Field(..., description="Event framing")
    
    # Primary intensity
    intensity_value: float = Field(..., description="Primary intensity value")
    intensity_unit: str = Field(..., description="Unit (m, m/s, °C, mm)")
    
    # Uncertainty bounds
    intensity_p5: Optional[float] = Field(None, description="5th percentile")
    intensity_p95: Optional[float] = Field(None, description="95th percentile")
    uncertainty_type: str = Field(
        default="unspecified", 
        description="Uncertainty source: ensemble_spread, bootstrap, parametric, fabricated"
    )
    
    # Resolution transparency — FIX v3.2 (Gap H)
    climate_forcing_resolution_m: int = Field(
        default=25000,
        ge=1,
        description="Resolution of climate forcing input (NEX-GDDP ~25000m). "
                    "All buildings in a ~625 km² grid cell share the same climate projection. "
                    "Building-level differentiation comes from terrain layers (DEM 30m, HAND 30m, LST 30m)."
    )
    native_resolution_m: int = Field(..., ge=1, description="Native data resolution of primary hazard layer")
    effective_resolution_m: int = Field(..., ge=1, description="Effective output resolution after all overlays")
    
    # Metadata
    data_sources: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.LOW)

    model_config = {"use_enum_values": True}


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


class CycloneAssessmentResponse(BaseModel):
    """
    Combined response for cyclone assessment.
    Wraps tuple return for Pydantic compliance.
    """
    hazard_result: "HazardAssessmentResult"  # Forward reference
    cyclone_params: CycloneEventParams
    
    model_config = {"arbitrary_types_allowed": True}
```

---

## 7. Exposure Profile (exposure.py) — ENHANCED v3.1

```python
# src/core/models/exposure.py
"""
Structure-level exposure models (E in H×E×V).

v3.1: Exposure is now building-centric. Each ExposureProfile maps to a
specific StructuralCharacteristics instance from asset.py. The profile
enriches the building with site-level context (terrain, urban morphology,
proximity to coast/river) needed for hazard-exposure intersection.
"""

from typing import Optional, List
from pydantic import BaseModel, Field, computed_field
from .geometry import Location
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
        description="Building count per km² from Open Buildings"
    )


class ExposureProfile(BaseModel):
    """
    Structure-level exposure: what is at risk and where.
    
    v3.1: Now anchored to a specific building from the asset layer.
    Every field needed to intersect the building with hazard intensity
    is captured here. The H×E calculation produces structure-specific
    hazard exposure (e.g., flood depth at THIS building's ground floor).
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
        description="Vertical uncertainty from DEM"
    )
    
    # Site context — enriches hazard intersection
    slope_degrees: Optional[float] = Field(
        None, 
        ge=0, 
        le=90, 
        description="Terrain slope at building location"
    )
    coastal_distance_m: Optional[float] = Field(
        None,
        ge=0,
        description="Distance to coastline (m)"
    )
    river_distance_m: Optional[float] = Field(
        None,
        ge=0,
        description="Distance to nearest river channel (m)"
    )
    coastal_type: Optional[str] = None
    
    # Urban context
    urban_context: Optional[UrbanContext] = None
    
    # Legacy compat (v3.0) — now derived from structure
    asset_type: Optional[str] = Field(None, description="Deprecated: use structure.occupancy")
    asset_value_usd: Optional[float] = Field(None, ge=0, description="Deprecated: use structure.replacement_value_usd")
    
    # Tracking
    adjustments_applied: List[str] = Field(
        default_factory=list, 
        description="Adjustments applied"
    )
    data_sources: List[str] = Field(
        default_factory=list,
        description="Data sources used to build this profile"
    )
    
    @computed_field
    @property
    def effective_flood_elevation_m(self) -> float:
        """First-floor elevation above MSL — the critical number for flood damage."""
        return self.structure.effective_ground_floor_m

    @computed_field
    @property
    def replacement_value_usd_resolved(self) -> Optional[float]:
        """Resolve replacement value from structure or legacy field."""
        return self.structure.replacement_value_usd or self.asset_value_usd
```

---

## 8. Vulnerability & Damage Curves (vulnerability.py) — ENHANCED v3.1

```python
# src/core/models/vulnerability.py
"""
Vulnerability assessment models (V in H×E×V).

v3.1: Structure-level vulnerability using JRC Global Flood Depth-Damage
Functions (Huizinga et al., 2017). Damage curves map flood depth → damage
ratio for each of 4 material-based vulnerability classes.

Curves are also defined for wind (cyclone) and heat (urban heat) hazards,
with appropriate structural modifiers.
"""

from typing import Optional, List, Dict, Tuple
from pydantic import BaseModel, Field, computed_field
from .enums import (
    HazardType, VulnerabilityClass, BuildingMaterial, BuildingOccupancy,
    ConfidenceLevel, DataSource
)


class DepthDamagePoint(BaseModel):
    """Single point on a depth-damage curve."""
    depth_m: float = Field(..., description="Flood depth (meters)")
    damage_ratio: float = Field(..., ge=0, le=1, description="Damage as fraction of replacement value")


class DepthDamageCurve(BaseModel):
    """
    Flood depth-damage function for a vulnerability class.
    
    From JRC (Huizinga et al., 2017): global depth-damage curves with
    continent-level calibration. Asia curves used for SEA.
    
    Interpolation: linear between points.
    Extrapolation: clamp to nearest endpoint.
    """
    vulnerability_class: VulnerabilityClass
    continent: str = Field(default="asia", description="Continent calibration")
    hazard_type: HazardType = Field(default=HazardType.RIVERINE_FLOOD)
    source: DataSource = Field(default=DataSource.JRC_FLOOD_DAMAGE)
    
    # Curve data: sorted by depth_m ascending
    points: List[DepthDamagePoint] = Field(
        ...,
        min_length=2,
        description="Depth-damage pairs (must be sorted by depth ascending)"
    )
    
    # Max damage values (USD/m² from JRC country estimates)
    max_damage_usd_per_m2: Optional[float] = Field(
        None, ge=0,
        description="Maximum damage per unit area (country-specific from JRC)"
    )
    
    def interpolate_damage(self, depth_m: float) -> float:
        """Interpolate damage ratio for a given flood depth."""
        if depth_m <= self.points[0].depth_m:
            return self.points[0].damage_ratio
        if depth_m >= self.points[-1].depth_m:
            return self.points[-1].damage_ratio
        
        for i in range(len(self.points) - 1):
            p1, p2 = self.points[i], self.points[i + 1]
            if p1.depth_m <= depth_m <= p2.depth_m:
                t = (depth_m - p1.depth_m) / (p2.depth_m - p1.depth_m)
                return p1.damage_ratio + t * (p2.damage_ratio - p1.damage_ratio)
        
        return self.points[-1].damage_ratio


# --- JRC Asia Flood Depth-Damage Curves (Huizinga et al., 2017) ---
# Adapted for SEA 4-class vulnerability system

JRC_ASIA_FLOOD_CURVES: Dict[VulnerabilityClass, List[Tuple[float, float]]] = {
    # Class I: Informal/mud/adobe — highest vulnerability, max ~1.0
    VulnerabilityClass.CLASS_I_INFORMAL: [
        (0.0, 0.05), (0.5, 0.35), (1.0, 0.55), (1.5, 0.70),
        (2.0, 0.80), (3.0, 0.90), (4.0, 0.95), (6.0, 1.00),
    ],
    # Class II: Wood/bamboo — high vulnerability, max ~0.85
    VulnerabilityClass.CLASS_II_WOOD: [
        (0.0, 0.03), (0.5, 0.20), (1.0, 0.38), (1.5, 0.50),
        (2.0, 0.60), (3.0, 0.72), (4.0, 0.80), (6.0, 0.85),
    ],
    # Class III: Unreinforced masonry/concrete — moderate, max ~0.65
    VulnerabilityClass.CLASS_III_MASONRY: [
        (0.0, 0.00), (0.5, 0.12), (1.0, 0.25), (1.5, 0.36),
        (2.0, 0.45), (3.0, 0.55), (4.0, 0.60), (6.0, 0.65),
    ],
    # Class IV: Reinforced concrete/steel — lowest, max ~0.45
    VulnerabilityClass.CLASS_IV_REINFORCED: [
        (0.0, 0.00), (0.5, 0.05), (1.0, 0.12), (1.5, 0.20),
        (2.0, 0.28), (3.0, 0.35), (4.0, 0.40), (6.0, 0.45),
    ],
}

# JRC Max Damage Values (USD/m² residential, 2017 prices adjusted for SEA)
JRC_MAX_DAMAGE_USD_M2: Dict[str, float] = {
    "vietnam": 227.0,
    "indonesia": 182.0,
    "philippines": 195.0,
    "thailand": 310.0,
    "singapore": 1250.0,
}


# --- Occupancy-Based Replacement Value Multipliers (NEW v3.2 — Gap T) ---
# JRC max damage values are residential-only. These multipliers adjust
# replacement value by occupancy type based on catastrophe modeling literature.
# Without this, a warehouse and a hospital get the same $/m² — incorrect.

OCCUPANCY_VALUE_MULTIPLIER: Dict[BuildingOccupancy, float] = {
    BuildingOccupancy.RESIDENTIAL_SINGLE: 1.0,     # Baseline (JRC residential)
    BuildingOccupancy.RESIDENTIAL_MULTI: 1.2,       # Slightly higher (elevators, shared infra)
    BuildingOccupancy.RESIDENTIAL_INFORMAL: 0.3,    # Much lower replacement cost
    BuildingOccupancy.COMMERCIAL: 2.5,              # Office/retail: higher fit-out cost
    BuildingOccupancy.INDUSTRIAL: 1.8,              # Factory/warehouse equipment
    BuildingOccupancy.INSTITUTIONAL: 3.0,           # Hospital/school: specialized equipment
    BuildingOccupancy.INFRASTRUCTURE: 4.0,          # Utilities: high-value systems
    BuildingOccupancy.AGRICULTURAL: 0.5,            # Farm structures: low replacement
    BuildingOccupancy.MIXED_USE: 1.5,               # Blended residential + commercial
    BuildingOccupancy.UNKNOWN: 1.0,                 # Default to residential
}


class WindVulnerabilityParams(BaseModel):
    """Wind vulnerability parameters for tropical cyclone damage."""
    wind_threshold_ms: float = Field(
        default=33.0, ge=0,
        description="Wind speed (m/s) below which no structural damage occurs"
    )
    max_wind_damage_ratio: float = Field(
        default=0.0, ge=0, le=1,
        description="Maximum damage ratio at extreme wind speeds"
    )
    
    # Material-dependent thresholds
    roof_loss_wind_ms: Optional[float] = Field(
        None, ge=0,
        description="Wind speed at which roof failure begins"
    )
    wall_failure_wind_ms: Optional[float] = Field(
        None, ge=0,
        description="Wind speed at which wall failure begins"
    )

# Wind damage thresholds by material
WIND_DAMAGE_THRESHOLDS: Dict[VulnerabilityClass, Dict[str, float]] = {
    VulnerabilityClass.CLASS_I_INFORMAL: {
        "wind_threshold_ms": 20.0, "max_damage": 1.0,
        "roof_loss_ms": 25.0, "wall_failure_ms": 35.0
    },
    VulnerabilityClass.CLASS_II_WOOD: {
        "wind_threshold_ms": 25.0, "max_damage": 0.85,
        "roof_loss_ms": 35.0, "wall_failure_ms": 50.0
    },
    VulnerabilityClass.CLASS_III_MASONRY: {
        "wind_threshold_ms": 33.0, "max_damage": 0.50,
        "roof_loss_ms": 45.0, "wall_failure_ms": 65.0
    },
    VulnerabilityClass.CLASS_IV_REINFORCED: {
        "wind_threshold_ms": 45.0, "max_damage": 0.25,
        "roof_loss_ms": 55.0, "wall_failure_ms": 80.0
    },
}


class VulnerabilityAssessment(BaseModel):
    """
    Structure-level vulnerability computed separately from hazard.
    
    v3.1: Now driven by JRC depth-damage curves + building structural
    classification. Vulnerability is determined by the building's material,
    occupancy, and physical characteristics — independent of hazard intensity.
    
    The final damage_ratio is computed when vulnerability meets hazard intensity.
    """
    # Building classification (from asset.py StructuralCharacteristics)
    building_id: str = Field(..., description="Building ID from asset layer")
    vulnerability_class: VulnerabilityClass = Field(
        ..., description="JRC class (I-IV)"
    )
    building_material: BuildingMaterial = Field(
        default=BuildingMaterial.UNKNOWN,
        description="Structural material"
    )
    building_occupancy: BuildingOccupancy = Field(
        default=BuildingOccupancy.UNKNOWN,
        description="Occupancy type"
    )
    
    # Vulnerability curve references
    flood_curve_id: str = Field(
        default="jrc_asia",
        description="Flood depth-damage curve ID"
    )
    wind_curve_id: str = Field(
        default="sea_wind_empirical",
        description="Wind vulnerability curve ID"
    )
    vulnerability_source: str = Field(
        default="jrc_2017",
        description="Source: jrc_2017, hazus_mh, user_provided"
    )
    
    # Structural modifiers
    ground_floor_elevation_m: float = Field(
        default=0.0, 
        ge=0, 
        description="First-floor elevation above ground grade"
    )
    has_basement: bool = Field(default=False)
    has_stilts: bool = Field(default=False, description="Raised on stilts (reduces flood damage)")
    num_stories: Optional[int] = Field(None, ge=1, le=200)
    has_air_conditioning: bool = Field(default=False, description="Relevant for heat vulnerability")
    mitigation_measures: List[str] = Field(default_factory=list)
    
    # Computed damage (set after H×E×V intersection)
    flood_damage_ratio: float = Field(
        default=0.0, ge=0, le=1,
        description="Flood damage ratio from depth-damage curve"
    )
    wind_damage_ratio: float = Field(
        default=0.0, ge=0, le=1,
        description="Wind damage ratio from wind speed"
    )
    heat_impact_score: float = Field(
        default=0.0, ge=0, le=1,
        description="Heat stress impact score (function of WBGT + AC + occupancy)"
    )
    
    # Aggregate damage
    combined_damage_ratio: float = Field(
        default=0.0, ge=0, le=1,
        description="Combined damage ratio across all hazards (max of individual, not sum)"
    )
    damage_uncertainty: float = Field(default=0.0, ge=0)
    expected_annual_loss_usd: Optional[float] = Field(
        None, ge=0,
        description="EAL = damage_ratio × replacement_value × annual_probability"
    )
    
    modifiers_applied: List[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MODERATE)
```

---

## 9. Adjusted Surface (surface.py)

```python
# src/core/models/surface.py
"""Adjusted surface for dependency tracking (prevents double-counting)."""

from typing import List
from pydantic import BaseModel, Field, PrivateAttr, computed_field


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
    def adjusted_elevation_m(self) -> float:
        """Ground elevation after subsidence."""
        return self.original_elevation_m - self.subsidence_adjustment_m

    def apply_subsidence(self, cumulative_m: float) -> None:
        """Apply subsidence adjustment (once only)."""
        if self._subsidence_applied:
            raise ValueError("Subsidence already applied - would double-count")
        self.subsidence_adjustment_m = cumulative_m
        self._subsidence_applied = True

    def apply_slr(self, slr_m: float) -> None:
        """Apply SLR adjustment (once only)."""
        if self._slr_applied:
            raise ValueError("SLR already applied - would double-count")
        self.slr_adjustment_m = slr_m
        self._slr_applied = True

    def get_effective_flood_depth(self, water_level_m: float) -> float:
        """Calculate flood depth with all adjustments."""
        adjusted_water = water_level_m + self.slr_adjustment_m
        return max(0, adjusted_water - self.adjusted_elevation_m)
    
    @property
    def subsidence_applied(self) -> bool:
        """Check if subsidence has been applied."""
        return self._subsidence_applied
    
    @property
    def slr_applied(self) -> bool:
        """Check if SLR has been applied."""
        return self._slr_applied

    model_config = {"arbitrary_types_allowed": True}


class BuildingAdjustedSurface(BaseModel):
    """
    Per-building surface adjustment (NEW v3.2 — Gap S).
    
    Replaces tile-level AdjustedSurface for structure-level workflow.
    
    Problem: v3.1 AdjustedSurface tracks a single elevation with once-only
    subsidence/SLR flags. But the v3.1 per-building workflow has each building
    at a different ground_elevation_m (from GLO-30 at centroid), and subsidence
    varies spatially. One AdjustedSurface per tile loses this differentiation.
    
    Fix: Each building gets its own adjusted surface context with:
    - Its centroid elevation from GLO-30
    - Spatially interpolated subsidence at its location
    - SLR contribution (uniform for coastal buildings, zero inland)
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
        
        Args:
            water_level_msl: Flood water surface elevation (m MSL)
            ground_floor_offset_m: Building floor height above grade (m)
        
        Returns:
            Positive flood depth (m) or 0 if building is above water.
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
        self._slr_applied = True

    model_config = {"arbitrary_types_allowed": True}
```

---

## 10. Assessment Results (results.py) — ENHANCED v3.2

```python
# src/core/models/results.py
"""Hazard assessment result models — enhanced with structure-level risk + multi-RP EAL."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, computed_field
from .enums import RiskTier, HazardType, VulnerabilityClass, ConfidenceLevel
from .hazard import HazardIntensity
from .exposure import ExposureProfile
from .vulnerability import VulnerabilityAssessment


class HazardAssessmentResult(BaseModel):
    """
    Complete hazard assessment with clean H×E×V separation.
    This is the standard return type for all hazard tools.
    """
    # Core components
    hazard: HazardIntensity = Field(..., description="Hazard intensity (H)")
    exposure: ExposureProfile = Field(..., description="Exposure profile (E)")
    vulnerability: Optional[VulnerabilityAssessment] = Field(
        None, 
        description="Vulnerability (V)"
    )
    
    # Computed impact
    impact_score: float = Field(
        default=0.0, 
        ge=0, 
        le=100, 
        description="Impact score (0-100)"
    )
    impact_tier: RiskTier = Field(default=RiskTier.LOW, description="Risk tier")
    
    # Intermediate values (for transparency)
    intermediate: Dict[str, Any] = Field(default_factory=dict)
    
    # Aggregation metadata
    can_aggregate_with: List[HazardType] = Field(
        default_factory=list, 
        description="Compatible hazards"
    )
    dependency_order: int = Field(
        default=99, 
        description="Execution order in dependency graph"
    )

    model_config = {"use_enum_values": True}


class StructureRiskResult(BaseModel):
    """
    Asset-level risk output for a single building (v3.1, enhanced v3.2).
    
    v3.2 (Gap Q): EAL is now computed via trapezoidal integration over the
    full loss-exceedance curve at standard return periods [10, 25, 50, 100, 250].
    The v3.1 single-RP approach computed scenario loss mislabeled as EAL.
    
    True EAL formula: EAL = ∫₀¹ L(p) dp
    where L(p) is loss at exceedance probability p = 1/RP.
    Discretized: EAL ≈ Σᵢ ½(Lᵢ + Lᵢ₊₁)(pᵢ - pᵢ₊₁) (trapezoidal rule)
    
    Consumers: SaaS dashboard, portfolio reports, insurance underwriting.
    """
    # Building identity
    building_id: str = Field(..., description="Unique building ID")
    latitude: float
    longitude: float

    @model_validator(mode='before')
    @classmethod
    def map_structure_id(cls, data: Any) -> Any:
        """Alias structure_id to building_id (backward compatibility)."""
        if isinstance(data, dict):
            if 'structure_id' in data and 'building_id' not in data:
                data['building_id'] = data.pop('structure_id')
        return data

    footprint_area_m2: float = Field(..., gt=0)
    
    # Building characteristics (from asset layer)
    height_m: Optional[float] = Field(None, ge=0)
    num_stories: int = Field(default=1, ge=1)
    vulnerability_class: VulnerabilityClass
    ground_floor_elevation_m: float = Field(default=0.0)
    replacement_value_usd: Optional[float] = Field(None, ge=0)
    replacement_value_source: str = Field(
        default="jrc_country_estimate",
        description="Value source: jrc_country_estimate (×occupancy_multiplier v3.2), user_provided"
    )
    
    # --- Per-hazard damage ratios (at primary return period) ---
    flood_damage_ratio: float = Field(default=0.0, ge=0, le=1, description="From JRC depth-damage curve at building floor level")
    flood_depth_at_building_m: float = Field(default=0.0, ge=0, description="Water depth at building ground floor")
    
    surge_damage_ratio: float = Field(default=0.0, ge=0, le=1)
    surge_depth_at_building_m: float = Field(default=0.0, ge=0)
    
    pluvial_flood_damage_ratio: float = Field(default=0.0, ge=0, le=1, description="From pluvial flood proxy (NEW v3.2)")
    pluvial_depth_at_building_m: float = Field(default=0.0, ge=0, description="Pluvial water depth at building")
    
    wind_damage_ratio: float = Field(default=0.0, ge=0, le=1, description="From wind vulnerability curve")
    max_wind_speed_ms: float = Field(default=0.0, ge=0)
    
    subsidence_mm_per_year: float = Field(default=0.0, ge=0, description="Annual subsidence rate at building")
    subsidence_cumulative_m: float = Field(default=0.0, ge=0, description="Projected total subsidence over horizon")
    subsidence_source: str = Field(default="none", description="insar_measured, published_literature, none")
    
    landslide_susceptibility: float = Field(default=0.0, ge=0, le=1)
    
    heat_wbgt_current: Optional[float] = Field(None, description="Current peak WBGT at building")
    heat_wbgt_projected: Optional[float] = Field(None, description="Projected peak WBGT")
    heat_impact_score: float = Field(default=0.0, ge=0, le=1)
    
    # --- Multi-RP loss-exceedance curve (NEW v3.2 — Gap Q) ---
    losses_by_return_period: List["ReturnPeriodLoss"] = Field(
        default_factory=list,
        description="Loss at each standard return period. Must be populated for valid EAL."
    )
    
    # --- Composite risk ---
    max_damage_ratio: float = Field(
        default=0.0, ge=0, le=1,
        description="Maximum single-hazard damage ratio (conservative estimate)"
    )
    combined_risk_score: float = Field(
        default=0.0, ge=0, le=100,
        description="Weighted composite risk score (0-100)"
    )
    risk_tier: RiskTier = Field(default=RiskTier.LOW)
    dominant_hazard: Optional[HazardType] = None
    
    # --- Financial impact (v3.2: multi-RP EAL) ---
    expected_annual_loss_usd: Optional[float] = Field(
        None, ge=0,
        description="EAL from trapezoidal integration of loss-exceedance curve (v3.2). "
                    "EAL = ∫₀¹ L(p) dp ≈ Σᵢ ½(Lᵢ + Lᵢ₊₁)(pᵢ - pᵢ₊₁)"
    )
    probable_maximum_loss_usd: Optional[float] = Field(
        None, ge=0,
        description="PML at 250-year return period (v3.2: was 100-year)"
    )
    
    # Metadata
    scenario: str = Field(default="ssp245", description="SSP scenario used")
    time_horizon_years: int = Field(default=30, description="Projection horizon")
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MODERATE)
    data_sources: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    
    @computed_field
    @property
    def loss_ratio_percent(self) -> float:
        """Damage as percentage for dashboard display."""
        return round(self.max_damage_ratio * 100, 1)
    
    @computed_field
    @property
    def eal_valid(self) -> bool:
        """Whether EAL was computed from multi-RP curve (v3.2) vs single-RP estimate."""
        return len(self.losses_by_return_period) >= 3


class ReturnPeriodLoss(BaseModel):
    """
    Loss at a specific return period (NEW v3.2 — Gap Q).
    
    Used to build the loss-exceedance curve for EAL integration.
    Standard RPs: [10, 25, 50, 100, 250] years.
    """
    return_period_years: int = Field(..., ge=2, le=1000)
    exceedance_probability: float = Field(
        ..., gt=0, le=1,
        description="Annual exceedance probability = 1/RP"
    )
    damage_ratio: float = Field(..., ge=0, le=1, description="Damage ratio at this RP")
    loss_usd: Optional[float] = Field(None, ge=0, description="Absolute loss (USD)")
    hazard_intensity: Optional[float] = Field(
        None, description="Primary hazard intensity at this RP"
    )
    hazard_intensity_unit: Optional[str] = Field(None, description="Unit of intensity")


# Standard return periods for EAL computation (v3.2)
STANDARD_RETURN_PERIODS = [2, 5, 10, 25, 50, 100, 250, 500, 1000]


def compute_eal_trapezoidal(
    losses: List[ReturnPeriodLoss]
) -> float:
    """
    Compute Expected Annual Loss via trapezoidal integration (Gap Q fix).
    
    EAL = ∫₀¹ L(p) dp ≈ Σᵢ ½(Lᵢ + Lᵢ₊₁)(pᵢ - pᵢ₊₁)
    
    where L(p) is loss at exceedance probability p, and losses are
    sorted by decreasing exceedance probability (increasing RP).
    
    Args:
        losses: List of ReturnPeriodLoss sorted by RP ascending
    
    Returns:
        EAL in USD/year
    """
    if len(losses) < 2:
        return 0.0
    
    # Sort by exceedance probability descending (RP ascending gives p descending)
    sorted_losses = sorted(losses, key=lambda x: -x.exceedance_probability)
    
    eal = 0.0
    for i in range(len(sorted_losses) - 1):
        p_high = sorted_losses[i].exceedance_probability
        p_low = sorted_losses[i + 1].exceedance_probability
        l_high = sorted_losses[i].loss_usd or 0.0
        l_low = sorted_losses[i + 1].loss_usd or 0.0
        eal += 0.5 * (l_high + l_low) * (p_high - p_low)
    
    # Add tail: loss from p=0 to smallest p (assume constant at max RP loss)
    # and from largest p to p=1 (assume zero loss beyond most frequent RP)
    smallest_p = sorted_losses[-1].exceedance_probability
    largest_p = sorted_losses[0].exceedance_probability
    max_rp_loss = sorted_losses[-1].loss_usd or 0.0
    min_rp_loss = sorted_losses[0].loss_usd or 0.0
    
    # Upper tail (rare events): constant loss from smallest_p to p=0
    eal += max_rp_loss * smallest_p
    # Lower tail (frequent events): linear from largest_p to p=1, loss→0
    eal += 0.5 * min_rp_loss * (1.0 - largest_p)
    
    return eal


class PortfolioRiskSummary(BaseModel):
    """
    Aggregated risk summary across a portfolio of buildings (NEW v3.1).
    
    For city-level or client portfolio risk reporting.
    Aggregates individual StructureRiskResult instances.
    """
    portfolio_id: str
    city: str
    scenario: str = Field(default="ssp245")
    time_horizon_years: int = Field(default=30)
    
    # Portfolio stats
    total_buildings: int = Field(default=0, ge=0)
    total_footprint_area_m2: float = Field(default=0.0, ge=0)
    total_replacement_value_usd: Optional[float] = Field(None, ge=0)
    
    # Risk distribution
    buildings_critical: int = Field(default=0, ge=0, description="RiskTier.CRITICAL count")
    buildings_high: int = Field(default=0, ge=0)
    buildings_moderate: int = Field(default=0, ge=0)
    buildings_low: int = Field(default=0, ge=0)
    
    # Aggregate financials
    portfolio_eal_usd: Optional[float] = Field(None, ge=0, description="Sum of EAL across portfolio")
    portfolio_pml_usd: Optional[float] = Field(None, ge=0, description="Portfolio PML (correlated)")
    
    # Dominant hazard breakdown
    hazard_exposure_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of buildings where each hazard is dominant"
    )
    
    # Vulnerability class distribution
    vulnerability_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description="Building count by vulnerability class"
    )
    
    # Per-building results
    building_results: List[StructureRiskResult] = Field(
        default_factory=list,
        description="Individual building risk results"
    )
    
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MODERATE)
    data_sources: List[str] = Field(default_factory=list)
```

---

## 11. Composite Risk (composite.py)

```python
# src/core/models/composite.py
"""Composite risk models."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field, computed_field
from .enums import RiskTier, ConfidenceLevel, HazardType
from .geometry import Location
from .results import HazardAssessmentResult


class CompositeRiskResult(BaseModel):
    """Composite risk with full transparency."""
    event_type: str = Field(..., description="Event class (acute/chronic)")
    composite_score: float = Field(..., ge=0, le=100, description="Composite score")
    composite_tier: RiskTier = Field(..., description="Risk tier")
    confidence: ConfidenceLevel = Field(..., description="Overall confidence")
    
    # Components (full transparency)
    hazard_scores: Dict[str, float] = Field(..., description="Individual scores")
    weights_used: Dict[str, float] = Field(..., description="Weights applied")
    
    # Uncertainty
    composite_p5: float = Field(..., ge=0, le=100)
    composite_p95: float = Field(..., ge=0, le=100)
    
    # Metadata
    city: str
    aggregation_valid: bool = Field(
        ..., 
        description="All hazards in same event class"
    )
    warnings: List[str] = Field(default_factory=list)
    excluded_hazards: List[str] = Field(default_factory=list)

    model_config = {"use_enum_values": True}


class SurfaceAdjustments(BaseModel):
    """Summary of surface adjustments applied."""
    original_elevation_m: float
    subsidence_applied_m: float
    slr_applied_m: float
    adjusted_elevation_m: float


class FullRiskProfile(BaseModel):
    """Complete risk profile with acute and chronic components."""
    location: Location
    city: str
    assessment_id: Optional[str] = Field(None, description="Unique assessment ID")
    
    # Separate composites (NEVER combined)
    acute_risk: CompositeRiskResult = Field(
        ..., 
        description="Acute hazards composite"
    )
    chronic_risk: CompositeRiskResult = Field(
        ..., 
        description="Chronic hazards composite"
    )
    
    # Individual hazard details
    acute_hazard_details: Dict[str, HazardAssessmentResult]
    chronic_hazard_details: Dict[str, HazardAssessmentResult]
    
    # Surface tracking
    surface_adjustments: SurfaceAdjustments
    
    # Methodology
    methodology: Dict[str, str] = Field(default_factory=lambda: {
        "acute_aggregation": "Weighted sum within same return period",
        "chronic_aggregation": "Weighted sum within same time horizon",
        "no_cross_aggregation": "Acute and chronic scores kept separate",
        "dependency_handling": "Subsidence → SLR → Flood/Surge (sequential, no double-count)"
    })

    @computed_field
    @property
    def overall_concern_level(self) -> str:
        """Qualitative overall concern (NOT a combined score)."""
        acute = self.acute_risk.composite_score
        chronic = self.chronic_risk.composite_score
        
        if acute >= 75 or chronic >= 75:
            return "Critical - Immediate attention required"
        elif acute >= 50 or chronic >= 50:
            primary = "Acute" if acute > chronic else "Chronic"
            return f"High - {primary} hazards are primary concern"
        elif acute >= 25 or chronic >= 25:
            return "Moderate - Monitor and plan mitigation"
        return "Low - Standard precautions sufficient"
```

---

## 12. Module Init (\_\_init\_\_.py)

```python
# src/core/models/__init__.py
"""Core Pydantic models for EcoShield — v3.1 with structure-level asset models."""

from .enums import (
    EventType,
    HazardType,
    ConfidenceLevel,
    RiskTier,
    SSPScenario,
    DataSource,
    # NEW v3.1 — asset enums
    BuildingMaterial,
    BuildingOccupancy,
    VulnerabilityClass,
)
from .geometry import Location, BoundingBox
from .asset import (  # NEW v3.1
    BuildingFootprint,
    BuildingHeight,
    StructuralCharacteristics,
    BuildingCluster,
)
from .climate import (
    ExtremePrecipitationResult,
    HistoricalClimateResult,
    ClimateProjectionResult,
    TemperatureBaselineResult,
)
from .elevation import (
    ElevationResult,
    HANDResult,
    SlopeResult,
    InSARVelocityResult,
    FloodReturnPeriodResult,
    SoilPropertiesResult,
    BathymetryResult,
)
from .events import EventContext
from .hazard import (
    HazardEventContext,
    HazardIntensity,
    CycloneEventParams,
    CycloneAssessmentResponse,
)
from .exposure import UrbanContext, ExposureProfile
from .vulnerability import (
    VulnerabilityAssessment,
    DepthDamageCurve,       # NEW v3.1
    DepthDamagePoint,       # NEW v3.1
)
from .surface import AdjustedSurface
from .surface import BuildingAdjustedSurface  # NEW v3.2 (Gap S)
from .results import (
    HazardAssessmentResult,
    StructureRiskResult,     # NEW v3.1, multi-RP EAL v3.2
    ReturnPeriodLoss,        # NEW v3.2 (Gap Q)
    PortfolioRiskSummary,    # NEW v3.1
    compute_eal_trapezoidal, # NEW v3.2 (Gap Q)
    STANDARD_RETURN_PERIODS, # NEW v3.2 (Gap Q)
)
from .composite import (
    CompositeRiskResult,
    SurfaceAdjustments,
    FullRiskProfile,
)

__all__ = [
    # Enums
    "EventType",
    "HazardType",
    "ConfidenceLevel",
    "RiskTier",
    "SSPScenario",
    "DataSource",
    "BuildingMaterial",       # NEW v3.1
    "BuildingOccupancy",      # NEW v3.1
    "VulnerabilityClass",     # NEW v3.1
    # Geometry
    "Location",
    "BoundingBox",
    # Asset (NEW v3.1)
    "BuildingFootprint",
    "BuildingHeight",
    "StructuralCharacteristics",
    "BuildingCluster",
    # Climate
    "ExtremePrecipitationResult",
    "HistoricalClimateResult",
    "ClimateProjectionResult",
    "TemperatureBaselineResult",
    # Elevation
    "ElevationResult",
    "HANDResult",
    "SlopeResult",
    "InSARVelocityResult",
    "FloodReturnPeriodResult",
    "SoilPropertiesResult",
    "BathymetryResult",
    # Events
    "EventContext",
    # Hazard
    "HazardEventContext",
    "HazardIntensity",
    "CycloneEventParams",
    "CycloneAssessmentResponse",
    # Exposure
    "UrbanContext",
    "ExposureProfile",
    # Vulnerability
    "VulnerabilityAssessment",
    "DepthDamageCurve",       # NEW v3.1
    "DepthDamagePoint",       # NEW v3.1
    # Surface
    "AdjustedSurface",
    "BuildingAdjustedSurface",    # NEW v3.2 (Gap S)
    # Results
    "HazardAssessmentResult",
    "StructureRiskResult",    # NEW v3.1, multi-RP v3.2
    "ReturnPeriodLoss",       # NEW v3.2 (Gap Q)
    "PortfolioRiskSummary",   # NEW v3.1
    "compute_eal_trapezoidal",# NEW v3.2 (Gap Q)
    "STANDARD_RETURN_PERIODS",# NEW v3.2 (Gap Q)
    # Composite
    "CompositeRiskResult",
    "SurfaceAdjustments",
    "FullRiskProfile",
]
```

---

## Cursor AI Instructions

### Setup

1. Create the directory structure: `mkdir -p src/core/models`
2. Create each file in order (enums.py first, then geometry.py, etc.)
3. Run validation after each file:

```bash
python -c "from src.core.models import *; print('Models loaded successfully')"
```

### Validation Checklist

- [ ] All models use Pydantic v2 syntax
- [ ] Field validators use `@field_validator` decorator
- [ ] Model validators use `@model_validator` decorator
- [ ] Enums inherit from `str, Enum` for JSON serialization
- [ ] Optional fields have explicit `Optional[T]` type hints
- [ ] All fields have descriptions
- [ ] `model_config` uses dict syntax (not `class Config`)

### Testing

Create `tests/unit/test_models.py`:

```python
import pytest
from src.core.models import *

def test_location_validation():
    loc = Location(lat=10.7, lon=106.7)
    assert loc.lat == 10.7
    
def test_location_invalid():
    with pytest.raises(ValueError):
        Location(lat=100, lon=106.7)  # lat > 90

def test_event_context_acute():
    ctx = EventContext(
        event_type=EventType.ACUTE,
        return_period=100
    )
    assert ctx.return_period == 100

def test_event_context_chronic_requires_horizon():
    with pytest.raises(ValueError):
        EventContext(event_type=EventType.CHRONIC)  # Missing time_horizon

def test_adjusted_surface_double_count_prevention():
    surface = AdjustedSurface(original_elevation_m=5.0)
    surface.apply_subsidence(0.5)
    with pytest.raises(ValueError):
        surface.apply_subsidence(0.3)  # Already applied

# --- Structure-level tests (NEW v3.1) ---

def test_building_footprint():
    fp = BuildingFootprint(
        building_id="8Q7X+M2",
        source=DataSource.GOOGLE_OPEN_BUILDINGS_V3,
        centroid=Location(lat=10.77, lon=106.70),
        area_m2=120.5,
        confidence=0.85,
    )
    assert fp.area_m2 == 120.5
    assert fp.confidence >= 0.65

def test_building_height_stories():
    h = BuildingHeight(height_m=12.5, height_year=2023)
    assert h.estimated_stories == 4  # 12.5 / 3.0 → round → 4

def test_structural_characteristics_effective_floor():
    fp = BuildingFootprint(
        building_id="test_001",
        source=DataSource.GOOGLE_OPEN_BUILDINGS_V3,
        centroid=Location(lat=10.77, lon=106.70),
        area_m2=100.0,
    )
    sc = StructuralCharacteristics(
        footprint=fp,
        ground_elevation_m=3.5,
        ground_floor_height_m=0.5,
        has_stilts=True,
    )
    # 3.5 + 0.5 + 1.5 (stilts) = 5.5m above MSL
    assert sc.effective_ground_floor_m == 5.5

def test_vulnerability_class_mapping():
    assert VulnerabilityClass.CLASS_I_INFORMAL.value == "class_i"
    assert VulnerabilityClass.CLASS_IV_REINFORCED.value == "class_iv"

def test_structure_risk_result():
    result = StructureRiskResult(
        building_id="test_bldg_1",
        latitude=10.77,
        longitude=106.70,
        footprint_area_m2=150.0,
        vulnerability_class=VulnerabilityClass.CLASS_III_MASONRY,
        flood_damage_ratio=0.35,
        flood_depth_at_building_m=1.2,
        max_damage_ratio=0.35,
        combined_risk_score=68.0,
        risk_tier=RiskTier.HIGH,
        replacement_value_usd=45000.0,
        expected_annual_loss_usd=1575.0,
    )
    assert result.loss_ratio_percent == 35.0
    assert result.risk_tier == RiskTier.HIGH

def test_depth_damage_curve_interpolation():
    from src.core.models.vulnerability import DepthDamageCurve, DepthDamagePoint
    curve = DepthDamageCurve(
        vulnerability_class=VulnerabilityClass.CLASS_III_MASONRY,
        points=[
            DepthDamagePoint(depth_m=0.0, damage_ratio=0.0),
            DepthDamagePoint(depth_m=1.0, damage_ratio=0.25),
            DepthDamagePoint(depth_m=3.0, damage_ratio=0.60),
            DepthDamagePoint(depth_m=6.0, damage_ratio=0.85),
        ]
    )
    assert curve.interpolate_damage(0.5) == pytest.approx(0.125, abs=0.01)
    assert curve.interpolate_damage(2.0) == pytest.approx(0.425, abs=0.01)
    assert curve.interpolate_damage(6.0) == 0.85  # Max clamp

def test_portfolio_summary():
    summary = PortfolioRiskSummary(
        portfolio_id="hcmc_district_1",
        city="ho_chi_minh_city",
        total_buildings=1500,
        buildings_critical=45,
        buildings_high=230,
        buildings_moderate=680,
        buildings_low=545,
    )
    assert summary.total_buildings == sum([
        summary.buildings_critical,
        summary.buildings_high,
        summary.buildings_moderate,
        summary.buildings_low,
    ])
```

---

## Next Phase

After completing Phase 1, proceed to **Phase 2: Data Access Layer** (ECOSHIELD-PHASE2-DATA-v3.md).

---

*EcoShield Phase 1 v3.2 | Core Pydantic Models — Structure-Level Asset Risk (H×E×V) + Gap Fixes*
