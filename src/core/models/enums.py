# src/core/models/enums.py
"""Enumerations for the EcoShield hazard system."""

from enum import Enum


class EventType(str, Enum):
    """Event classification for probabilistic coherence."""
    CHRONIC = "chronic"
    ACUTE = "acute"


class HazardType(str, Enum):
    """Supported hazard types."""
    RIVERINE_FLOOD = "riverine_flood"
    COASTAL_FLOOD = "coastal_flood"
    STORM_SURGE = "storm_surge"
    TROPICAL_CYCLONE = "tropical_cyclone"
    LANDSLIDE = "landslide"
    SUBSIDENCE = "subsidence"
    URBAN_HEAT = "urban_heat"
    PLUVIAL_FLOOD = "pluvial_flood"  # NEW v3.2 (Gap M)


class ConfidenceLevel(str, Enum):
    """Assessment confidence level."""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class ValidationStatus(str, Enum):
    """Validation status for model outputs (Gap 2.1)."""
    UNVALIDATED = "unvalidated"
    VALIDATED = "validated"
    CALIBRATED = "calibrated"
    FAILED = "failed"


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
    """Data source identifiers — v3.0 API-first (all programmatic access)."""
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
    GOOGLE_OPEN_BUILDINGS_V3 = "google_open_buildings_v3"  # Building footprints
    GOOGLE_OPEN_BUILDINGS_2_5D = "google_open_buildings_2_5d"  # Building heights
    OVERTURE_MAPS_BUILDINGS = "overture_maps_buildings"    # Conflated attributes

    # --- Vulnerability data sources (NEW v3.1) ---
    JRC_FLOOD_DAMAGE = "jrc_flood_damage"      # Global depth-damage curves


class BuildingMaterial(str, Enum):
    """Primary structural material classification (JRC aligned)."""
    MUD_ADOBE = "mud_adobe"              # JRC Class I
    BAMBOO_THATCH = "bamboo_thatch"      # JRC Class I / II
    WOOD_FRAME = "wood_frame"            # JRC Class II
    MASONRY_UNREINFORCED = "masonry_unreinforced"  # JRC Class III
    CONCRETE_REINFORCED = "concrete_reinforced"    # JRC Class IV
    STEEL_FRAME = "steel_frame"                    # JRC Class IV
    UNKNOWN = "unknown"


class BuildingOccupancy(str, Enum):
    """Building occupancy classification (HAZUS-compatible)."""
    RESIDENTIAL_SINGLE = "res_single"
    RESIDENTIAL_MULTI = "res_multi"
    RESIDENTIAL_INFORMAL = "res_informal"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"
    INSTITUTIONAL = "institutional"
    INFRASTRUCTURE = "infrastructure"
    AGRICULTURAL = "agricultural"
    MIXED_USE = "mixed_use"
    UNKNOWN = "unknown"


class VulnerabilityClass(str, Enum):
    """JRC vulnerability classification for flood damage curves."""
    CLASS_I_INFORMAL = "class_i"      # Mud/adobe/informal
    CLASS_II_WOOD = "class_ii"        # Wood/bamboo/timber
    CLASS_III_MASONRY = "class_iii"   # Unreinforced masonry
    CLASS_IV_REINFORCED = "class_iv"  # Reinforced concrete/steel


class StructureCategory(str, Enum):
    """Top-level building category for spatial matching QA."""
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"


class StructureType(str, Enum):
    """Specific structure type within a category.

    Each type has expected physical characteristics (area, height, floors)
    used by the spatial matcher QA step to reject implausible matches.

    Includes CONVERTED_* composite types for SEA adaptive reuse where
    function diverges from physical form (e.g. tube house operating as
    boutique hotel in Hanoi Old Quarter). These use the physical envelope
    for spatial matching but the commercial function for vulnerability/value.
    """
    # Residential
    TUBE_HOUSE = "tube_house"                    # Vietnamese nhà ống, narrow 3-4m wide
    SINGLE_DWELLING = "single_dwelling"          # Detached / semi-detached house
    MULTISTORY_DWELLING = "multistory_dwelling"  # Row houses, townhouses
    APARTMENT_BUILDING = "apartment_building"    # Condos, HDB-style blocks
    INFORMAL_SETTLEMENT = "informal_settlement"  # Slums, temporary structures

    # Commercial
    HOTEL = "hotel"
    SHOPPING_MALL = "shopping_mall"
    BANK = "bank"
    GYM = "gym"
    OFFICE_BUILDING = "office_building"
    RETAIL_SHOP = "retail_shop"
    RESTAURANT = "restaurant"

    # Industrial
    FACTORY = "factory"
    WAREHOUSE = "warehouse"

    # Adaptive reuse — commercial function in residential/industrial envelope.
    # Common in Hanoi Old Quarter, HCMC District 1, Hội An ancient town,
    # Bangkok Chinatown, Manila Intramuros, Jakarta Kota Tua.
    # Spatial QA uses the PHYSICAL form; vulnerability/value uses the FUNCTION.
    CONVERTED_TUBE_HOUSE_HOTEL = "converted_tube_house_hotel"
    CONVERTED_TUBE_HOUSE_SHOP = "converted_tube_house_shop"
    CONVERTED_TUBE_HOUSE_RESTAURANT = "converted_tube_house_restaurant"
    CONVERTED_VILLA_HOTEL = "converted_villa_hotel"
    CONVERTED_VILLA_RESTAURANT = "converted_villa_restaurant"
    CONVERTED_SHOPHOUSE_HOTEL = "converted_shophouse_hotel"
    CONVERTED_WAREHOUSE_COMMERCIAL = "converted_warehouse_commercial"
