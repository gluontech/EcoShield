# src/core/models/__init__.py
"""Core Pydantic models for EcoShield — v3.1 with structure-level asset models."""

from .enums import (
    EventType,
    HazardType,
    ConfidenceLevel,
    RiskTier,
    SSPScenario,
    DataSource,
    ValidationStatus,         # NEW Gap 2.1
    # NEW v3.1 — asset enums
    BuildingMaterial,
    BuildingOccupancy,
    VulnerabilityClass,
)
from .geometry import (
    Location, 
    BoundingBox,
    DataLineage,              # NEW Gap 4.3
)
from .asset import (  # NEW v3.1
    BuildingFootprint,
    BuildingHeight,
    StructuralCharacteristics,
    BuildingCluster,
    SEA_MATERIAL_DEFAULTS,
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
    SlopeResult,              # NEW
    InSARVelocityResult,      # NEW
    FloodReturnPeriodResult,  # NEW
    SoilPropertiesResult,     # NEW
    BathymetryResult,         # NEW
    NDVIStatisticsResult,     # NEW
    LSTStatisticsResult,      # NEW
    WBGTComponentsResult,     # NEW
)
from .events import EventContext
from .hazard import (
    HazardEventContext,
    HazardIntensity,
    CycloneEventParams,       # NEW
    CycloneAssessmentResponse,# NEW
)
from .exposure import UrbanContext, ExposureProfile
from .vulnerability import (
    VulnerabilityAssessment,
    DepthDamageCurve,       # NEW v3.1
    DepthDamagePoint,       # NEW v3.1
    WindVulnerabilityParams,# NEW
    JRC_ASIA_FLOOD_CURVES,  # NEW
    APP_OCCUPANCY_VALUE_MULTIPLIER, # NEW
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
    ValidationMetrics,       # NEW Gap 2.1
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
    "ValidationStatus",
    "BuildingMaterial",       # NEW v3.1
    "BuildingOccupancy",      # NEW v3.1
    "VulnerabilityClass",     # NEW v3.1
    # Geometry
    "Location",
    "BoundingBox",
    "DataLineage",            # NEW Gap 4.3
    # Asset (NEW v3.1)
    "BuildingFootprint",
    "BuildingHeight",
    "StructuralCharacteristics",
    "BuildingCluster",
    "SEA_MATERIAL_DEFAULTS",
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
    "NDVIStatisticsResult",
    "LSTStatisticsResult",
    "WBGTComponentsResult",
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
    "WindVulnerabilityParams",
    "JRC_ASIA_FLOOD_CURVES",
    "APP_OCCUPANCY_VALUE_MULTIPLIER",
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
    "ValidationMetrics",      # NEW Gap 2.1
    # Composite
    "CompositeRiskResult",
    "SurfaceAdjustments",
    "FullRiskProfile",
]
