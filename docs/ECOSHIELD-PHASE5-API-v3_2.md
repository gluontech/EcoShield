# EcoShield Phase 5: API Layer — v3.2

## Implementation Guide for Cursor AI

> **Phase 5 v3.2**: Expose hazard assessment capabilities as a RESTful API
> using FastAPI.  All **eight** hazard workflows from Phase 4 are accessible via
> standardised endpoints.
> **v3.1**: Structure-level building assessment endpoint (`POST /v1/buildings/assess`)
> returns per-building H×E×V damage ratios, expected annual loss, and portfolio summary.
> **v3.2 Changes**:
> - `multi_rp` and `return_periods` query parameters on all assessment endpoints
>   to enable multi-return-period EAL computation (Gap Q).
> - `portfolio_eal_usd` in portfolio and building response schemas — trapezoidal
>   EAL from structure-level multi-RP loss curves (Gap Q).
> - Pluvial flood (`pluvial`) added as 8th hazard type in all request/response
>   schemas and hazard module registry (Gap M).
> - Per-building `losses_by_return_period` in structure risk response — exposes
>   the full loss-exceedance curve for each building (Gap Q).
> - `occupancy_class` and `replacement_value_source` in building response (Gaps S/T).

---

## Overview

The API layer wraps the Phase 4 hazard workflow into production-ready HTTP
endpoints with authentication, rate limiting, input validation, and structured
error responses.

v3.2: All eight hazards (including pluvial flood) are now exposed via the API.
Multi-return-period EAL computation is enabled by default, with per-building
loss-exceedance curves available in the structure risk response.

### Files to Create

```
src/api/
├── __init__.py
├── main.py              # FastAPI app + lifespan
├── routes/
│   ├── __init__.py
│   ├── assess.py        # POST /v1/assess — single-site hazard assessment
│   ├── portfolio.py     # POST /v1/portfolio — batch portfolio analysis
│   ├── buildings.py     # POST /v1/buildings/assess — structure-level H×E×V (v3.1, updated v3.2)
│   └── hazards.py       # GET  /v1/hazards/{type} — hazard-specific lookup (v3.2: + pluvial)
├── schemas/
│   ├── __init__.py
│   ├── requests.py      # Pydantic request models (v3.2: + multi_rp, return_periods)
│   └── responses.py     # Pydantic response models (v3.2: + losses_by_return_period, portfolio_eal_usd)
├── middleware/
│   ├── __init__.py
│   ├── auth.py          # API key authentication
│   └── rate_limit.py    # Token-bucket rate limiting
└── errors.py            # Structured error responses
```

### Dependencies

```toml
[project]
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.29",
    "pydantic>=2.7",
    "python-multipart>=0.0.9",
]
```

---

## 1. Application Entry Point (main.py)

```python
# src/api/main.py
"""
EcoShield API — FastAPI application.

Run:
    uvicorn src.api.main:app --host 0.0.0.0 --port 8000

Docs:
    http://localhost:8000/docs   (Swagger)
    http://localhost:8000/redoc  (ReDoc)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import assess, portfolio, hazards
from src.api.routes import buildings  # NEW v3.1
from src.api.middleware.auth import APIKeyMiddleware
from src.api.middleware.rate_limit import RateLimitMiddleware
from src.api.errors import register_error_handlers
from src.config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    # ── Startup ──
    print("EcoShield API starting…")
    # Pre-warm caches, verify data availability
    yield
    # ── Shutdown ──
    print("EcoShield API shutting down…")


app = FastAPI(
    title="EcoShield Climate Risk API",
    description=(
        "Multi-hazard climate risk assessment for Southeast Asia. "
        "Covers flood, heat stress, cyclone, storm surge, subsidence, "
        "landslide, wind, and pluvial flood hazards. v3.2: Multi-RP "
        "EAL via trapezoidal integration, per-building loss curves, "
        "pluvial flood (8th hazard), occupancy-scaled replacement values."
    ),
    version="3.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Middleware ───────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if hasattr(settings, "CORS_ORIGINS") else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(APIKeyMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=60)

# ── Error handlers ──────────────────────────────────────
register_error_handlers(app)

# ── Routes ──────────────────────────────────────────────
app.include_router(assess.router, prefix="/v1", tags=["Assessment"])
app.include_router(portfolio.router, prefix="/v1", tags=["Portfolio"])
app.include_router(buildings.router, prefix="/v1", tags=["Buildings"])  # NEW v3.1
app.include_router(hazards.router, prefix="/v1", tags=["Hazards"])


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "3.2.0"}
```

---

## 2. Request Schemas (schemas/requests.py)

```python
# src/api/schemas/requests.py
"""Pydantic request models for the EcoShield API."""

from typing import Optional, List
from pydantic import BaseModel, Field, field_validator

from src.core.models import SSPScenario


class Location(BaseModel):
    """Geographic location."""
    lat: float = Field(..., ge=-60, le=60, description="Latitude")
    lon: float = Field(..., ge=-180, le=180, description="Longitude")
    name: Optional[str] = Field(None, description="Location label")


class AssessRequest(BaseModel):
    """Single-site hazard assessment request."""
    location: Location
    hazards: List[str] = Field(
        default=["flood", "heat", "cyclone", "surge", "subsidence",
                 "landslide", "wind", "pluvial"],  # v3.2: + pluvial (Gap M)
        description="Hazard types to assess",
    )
    scenario: SSPScenario = Field(
        default=SSPScenario.SSP245,
        description="Climate scenario",
    )
    time_horizon: str = Field(
        default="2041-2060",
        description="Future period (e.g. '2041-2060')",
    )
    return_period: int = Field(
        default=100,
        ge=2, le=1000,
        description="Primary return period in years (used for display/tier)",
    )
    multi_rp: bool = Field(
        default=True,
        description="Enable multi-RP assessment at standard return periods "
                    "[10, 25, 50, 100, 250] for EAL computation (v3.2 Gap Q)",
    )
    return_periods: Optional[List[int]] = Field(
        default=None,
        description="Custom return periods (overrides standard [10,25,50,100,250] "
                    "when multi_rp=True). Each must be 2-1000. (v3.2 Gap Q)",
    )
    include_details: bool = Field(
        default=False,
        description="Include detailed component results",
    )

    @field_validator("hazards")
    @classmethod
    def validate_hazards(cls, v):
        valid = {"flood", "heat", "cyclone", "surge", "subsidence",
                 "landslide", "wind", "pluvial"}  # v3.2: + pluvial
        invalid = set(v) - valid
        if invalid:
            raise ValueError(f"Unknown hazard types: {invalid}. Valid: {valid}")
        return v

    @field_validator("return_periods")
    @classmethod
    def validate_return_periods(cls, v):
        """Validate custom return periods are within bounds."""
        if v is not None:
            for rp in v:
                if rp < 2 or rp > 1000:
                    raise ValueError(f"Return period {rp} out of range [2, 1000]")
            if len(v) < 1:
                raise ValueError("return_periods must contain at least 1 value")
            if len(v) > 10:
                raise ValueError("return_periods max 10 values")
        return v


class PortfolioSite(BaseModel):
    """Single site in a portfolio."""
    location: Location
    asset_value_usd: Optional[float] = Field(None, ge=0)
    asset_type: Optional[str] = None


class PortfolioRequest(BaseModel):
    """Batch portfolio analysis request."""
    sites: List[PortfolioSite] = Field(..., min_length=1, max_length=100)
    hazards: List[str] = Field(
        default=["flood", "heat", "cyclone", "surge", "subsidence",
                 "landslide", "wind", "pluvial"],  # v3.2: + pluvial
    )
    scenario: SSPScenario = Field(default=SSPScenario.SSP245)
    time_horizon: str = Field(default="2041-2060")
    return_period: int = Field(default=100, ge=2, le=1000)
    multi_rp: bool = Field(
        default=True,
        description="Enable multi-RP EAL computation (v3.2 Gap Q)",
    )
    return_periods: Optional[List[int]] = Field(
        default=None,
        description="Custom return periods when multi_rp=True (v3.2 Gap Q)",
    )


class HazardQueryParams(BaseModel):
    """Query parameters for hazard-specific lookups."""
    lat: float = Field(..., ge=-60, le=60)
    lon: float = Field(..., ge=-180, le=180)
    return_period: int = Field(default=100, ge=2, le=1000)
    scenario: SSPScenario = Field(default=SSPScenario.SSP245)
    multi_rp: bool = Field(
        default=False,
        description="Enable multi-RP assessment for this hazard (v3.2 Gap Q)",
    )


# ── Structure-level request (v3.2: + multi_rp, return_periods) ──

class BuildingAssessRequest(BaseModel):
    """Structure-level risk assessment request (v3.1, updated v3.2)."""
    lat: float = Field(..., ge=-60, le=60, description="Center latitude")
    lon: float = Field(..., ge=-60, le=180, description="Center longitude")
    radius_m: int = Field(
        default=500, ge=50, le=5000,
        description="Search radius in meters",
    )
    city: str = Field(
        default="hcmc",
        description="City key (hcmc, hanoi, danang, jakarta, manila, bangkok, singapore)",
    )
    return_period: int = Field(
        default=100, ge=2, le=1000,
        description="Primary return period for display/tier",
    )
    multi_rp: bool = Field(
        default=True,
        description="Enable multi-RP loop [10,25,50,100,250] for trapezoidal "
                    "EAL computation (v3.2 Gap Q)",
    )
    return_periods: Optional[List[int]] = Field(
        default=None,
        description="Custom return periods when multi_rp=True (v3.2 Gap Q)",
    )
    scenario: SSPScenario = Field(default=SSPScenario.SSP245)
    time_horizon: str = Field(default="2041-2060")
    max_buildings: int = Field(
        default=1000, ge=1, le=10000,
        description="Max buildings to assess (performance limit)",
    )
```

---

## 3. Response Schemas (schemas/responses.py)

```python
# src/api/schemas/responses.py
"""
Pydantic response models for the EcoShield API.

v3.2 Changes:
  - HazardScore: pluvial flood now valid hazard_type (Gap M)
  - PortfolioSiteResult: portfolio_eal_usd from multi-RP trapezoidal EAL (Gap Q)
  - PortfolioResponse: portfolio_eal_usd aggregate (Gap Q)
  - BuildingRiskItem: losses_by_return_period, pluvial_damage_ratio,
    occupancy_class, replacement_value_source (Gaps M/Q/S/T)
  - BuildingPortfolioSummary: portfolio_eal_usd (Gap Q)
  - BuildingAssessResponse: multi_rp, return_periods fields (Gap Q)
"""

from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field


class HazardScore(BaseModel):
    """Individual hazard score (v3.2: pluvial flood now valid type)."""
    hazard_type: str  # v3.2: "pluvial" now a valid value (Gap M)
    risk_score: float = Field(..., ge=0, le=1, description="0-1 normalised risk")
    risk_category: str = Field(..., description="Low / Moderate / High / Very High / Extreme")
    confidence: str
    key_drivers: List[str] = Field(default_factory=list)
    details: Optional[Dict[str, Any]] = None


class AssessResponse(BaseModel):
    """Single-site assessment response."""
    location: Dict[str, Any]
    scenario: str
    time_horizon: str
    return_period: int
    multi_rp: bool = Field(False, description="Whether multi-RP was used (v3.2)")
    return_periods_assessed: Optional[List[int]] = Field(
        None, description="Actual RPs assessed when multi_rp=True (v3.2)"
    )
    overall_risk_score: float = Field(..., ge=0, le=1)
    overall_risk_category: str
    hazards: List[HazardScore]
    portfolio_eal_usd: Optional[float] = Field(
        None, description="Multi-RP trapezoidal EAL in USD (v3.2 Gap Q). "
                          "Only present when multi_rp=True and buildings assessed."
    )
    data_sources: List[str]
    processing_time_ms: int


class PortfolioSiteResult(BaseModel):
    """Result for one site in a portfolio."""
    location: Dict[str, Any]
    overall_risk_score: float
    overall_risk_category: str
    hazard_scores: Dict[str, float]
    asset_value_usd: Optional[float] = None
    expected_annual_loss_usd: Optional[float] = None
    portfolio_eal_usd: Optional[float] = Field(
        None, description="Multi-RP trapezoidal EAL for this site (v3.2 Gap Q)"
    )


class PortfolioResponse(BaseModel):
    """Batch portfolio response."""
    n_sites: int
    scenario: str
    time_horizon: str
    multi_rp: bool = Field(False, description="Whether multi-RP was used (v3.2)")
    return_periods_assessed: Optional[List[int]] = None
    sites: List[PortfolioSiteResult]
    portfolio_summary: Dict[str, Any]
    processing_time_ms: int


class ErrorResponse(BaseModel):
    """Structured error response."""
    error: str
    detail: str
    status_code: int
    retry_after: Optional[int] = None


# ── Structure-level responses (v3.2: + losses_by_return_period, pluvial, occupancy) ──

class ReturnPeriodLossItem(BaseModel):
    """Loss at a single return period for one building (NEW v3.2 Gap Q)."""
    return_period: int
    annual_exceedance_probability: float = Field(
        ..., description="1/return_period"
    )
    flood_damage_ratio: float = Field(..., ge=0, le=1)
    wind_damage_ratio: Optional[float] = None
    pluvial_damage_ratio: Optional[float] = Field(
        None, ge=0, le=1, description="Pluvial flood damage ratio (v3.2 Gap M)"
    )
    max_damage_ratio: float = Field(..., ge=0, le=1)
    estimated_loss_usd: Optional[float] = None


class BuildingRiskItem(BaseModel):
    """Per-building risk result (v3.2: + multi-RP loss curve, pluvial, occupancy)."""
    building_id: str
    latitude: float
    longitude: float
    footprint_area_m2: float
    vulnerability_class: str
    occupancy_class: Optional[str] = Field(
        None, description="Building occupancy (residential, commercial, industrial, "
                          "public_service) — v3.2 Gap T"
    )
    flood_damage_ratio: float = Field(
        ..., ge=0, le=1,
        description="Combined riverine+coastal+surge flood damage at primary RP"
    )
    flood_depth_at_building_m: float
    pluvial_damage_ratio: Optional[float] = Field(
        None, ge=0, le=1,
        description="Pluvial flood damage ratio at primary RP (v3.2 Gap M)"
    )
    wind_damage_ratio: Optional[float] = None
    max_damage_ratio: float = Field(..., ge=0, le=1)
    risk_score: float = Field(..., ge=0, le=100)
    risk_tier: str
    replacement_value_usd: Optional[float] = None
    replacement_value_source: Optional[str] = Field(
        None, description="Source: 'jrc_country_occupancy' or 'jrc_country' (v3.2 Gap T)"
    )
    expected_annual_loss_usd: Optional[float] = Field(
        None, description="Trapezoidal EAL from multi-RP loss curve (v3.2 Gap Q). "
                          "Falls back to single-RP estimate if multi_rp=False."
    )
    losses_by_return_period: Optional[List[ReturnPeriodLossItem]] = Field(
        None, description="Full loss-exceedance curve per building (v3.2 Gap Q). "
                          "One entry per assessed return period."
    )


class BuildingPortfolioSummary(BaseModel):
    """Aggregated building portfolio statistics (v3.2: + portfolio_eal_usd)."""
    total_buildings: int
    buildings_by_tier: Dict[str, int]
    total_replacement_value_usd: float
    total_expected_annual_loss_usd: float = Field(
        ..., description="Sum of per-building trapezoidal EAL (v3.2 Gap Q)"
    )
    portfolio_eal_usd: Optional[float] = Field(
        None, description="Alias for total_expected_annual_loss_usd — "
                          "multi-RP trapezoidal integration (v3.2 Gap Q)"
    )
    mean_damage_ratio: float
    pml_250yr_usd: Optional[float] = Field(
        None, description="Probable Maximum Loss at 250-year RP (v3.2)"
    )


class BuildingAssessResponse(BaseModel):
    """Structure-level assessment response (v3.2: + multi-RP, pluvial)."""
    center: Dict[str, float]
    radius_m: int
    city: str
    scenario: str
    return_period: int = Field(..., description="Primary RP for display/tier")
    multi_rp: bool = Field(False, description="Whether multi-RP was used (v3.2)")
    return_periods_assessed: Optional[List[int]] = Field(
        None, description="Actual RPs assessed [10,25,50,100,250] (v3.2 Gap Q)"
    )
    n_buildings: int
    buildings: List[BuildingRiskItem]
    portfolio_summary: BuildingPortfolioSummary
    data_sources: List[str]
    processing_time_ms: int
```

---

## 4. Assessment Route (routes/assess.py)

```python
# src/api/routes/assess.py
"""POST /v1/assess — single-site hazard assessment."""

import time

from fastapi import APIRouter, HTTPException

from src.api.schemas.requests import AssessRequest
from src.api.schemas.responses import AssessResponse, HazardScore
from src.hazards.workflow import run_hazard_assessment

router = APIRouter()


def _score_to_category(score: float) -> str:
    """Convert 0-1 score to risk category."""
    if score < 0.2:
        return "Low"
    elif score < 0.4:
        return "Moderate"
    elif score < 0.6:
        return "High"
    elif score < 0.8:
        return "Very High"
    return "Extreme"


@router.post("/assess", response_model=AssessResponse)
async def assess_site(request: AssessRequest):
    """
    Perform multi-hazard climate risk assessment for a single location.

    Runs requested hazard modules in parallel and returns normalised
    risk scores with confidence levels and key drivers.

    v3.2: When multi_rp=True, runs assessment at multiple return periods
    [10, 25, 50, 100, 250] (or custom return_periods) and computes
    trapezoidal EAL. Pluvial flood is now a valid hazard type.
    """
    start = time.monotonic()

    try:
        result = await run_hazard_assessment(
            lat=request.location.lat,
            lon=request.location.lon,
            hazards=request.hazards,
            scenario=request.scenario,
            time_horizon=request.time_horizon,
            return_period=request.return_period,
            multi_rp=request.multi_rp,                  # NEW v3.2 (Gap Q)
            return_periods=request.return_periods,       # NEW v3.2 (Gap Q)
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Data not available: {e}. Run ingestion first.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Build hazard scores
    hazard_scores = []
    scores = []
    data_sources = set()

    for hazard_type, hazard_result in result.items():
        score = hazard_result.get("risk_score", 0.0)
        scores.append(score)
        data_sources.update(hazard_result.get("data_sources", []))

        hazard_scores.append(HazardScore(
            hazard_type=hazard_type,
            risk_score=score,
            risk_category=_score_to_category(score),
            confidence=hazard_result.get("confidence", "moderate"),
            key_drivers=hazard_result.get("key_drivers", []),
            details=hazard_result if request.include_details else None,
        ))

    overall = sum(scores) / len(scores) if scores else 0.0

    # v3.2 (Gap Q): Extract portfolio EAL if available
    portfolio_eal = result.get("portfolio_eal_usd") if isinstance(result, dict) else None

    # v3.2: Determine actual return periods assessed
    rps_assessed = None
    if request.multi_rp:
        from src.core.models import STANDARD_RETURN_PERIODS
        rps_assessed = request.return_periods or STANDARD_RETURN_PERIODS

    return AssessResponse(
        location={
            "lat": request.location.lat,
            "lon": request.location.lon,
            "name": request.location.name,
        },
        scenario=request.scenario.value,
        time_horizon=request.time_horizon,
        return_period=request.return_period,
        multi_rp=request.multi_rp,                      # NEW v3.2
        return_periods_assessed=rps_assessed,            # NEW v3.2
        overall_risk_score=round(overall, 3),
        overall_risk_category=_score_to_category(overall),
        hazards=hazard_scores,
        portfolio_eal_usd=portfolio_eal,                 # NEW v3.2 (Gap Q)
        data_sources=sorted(data_sources),
        processing_time_ms=elapsed_ms,
    )
```

---

## 5. Portfolio Route (routes/portfolio.py)

```python
# src/api/routes/portfolio.py
"""POST /v1/portfolio — batch portfolio analysis."""

import asyncio
import time

from fastapi import APIRouter, HTTPException

from src.api.schemas.requests import PortfolioRequest
from src.api.schemas.responses import PortfolioResponse, PortfolioSiteResult
from src.hazards.workflow import run_hazard_assessment

router = APIRouter()


def _score_to_category(score: float) -> str:
    if score < 0.2:
        return "Low"
    elif score < 0.4:
        return "Moderate"
    elif score < 0.6:
        return "High"
    elif score < 0.8:
        return "Very High"
    return "Extreme"


@router.post("/portfolio", response_model=PortfolioResponse)
async def assess_portfolio(request: PortfolioRequest):
    """
    Run hazard assessment across a portfolio of sites.

    Sites are assessed in parallel (up to 10 concurrently).

    v3.2: When multi_rp=True, each site runs multi-RP assessment and
    returns trapezoidal EAL (portfolio_eal_usd) instead of simplified
    risk_score × asset_value estimate.
    """
    start = time.monotonic()
    semaphore = asyncio.Semaphore(10)

    async def _assess_one(site):
        async with semaphore:
            try:
                result = await run_hazard_assessment(
                    lat=site.location.lat,
                    lon=site.location.lon,
                    hazards=request.hazards,
                    scenario=request.scenario,
                    time_horizon=request.time_horizon,
                    return_period=request.return_period,
                    multi_rp=request.multi_rp,                  # NEW v3.2
                    return_periods=request.return_periods,       # NEW v3.2
                )
            except Exception as e:
                return PortfolioSiteResult(
                    location={
                        "lat": site.location.lat,
                        "lon": site.location.lon,
                        "name": site.location.name,
                    },
                    overall_risk_score=0.0,
                    overall_risk_category="Error",
                    hazard_scores={},
                    asset_value_usd=site.asset_value_usd,
                    expected_annual_loss_usd=None,
                    portfolio_eal_usd=None,
                )

            hazard_scores = {
                h: r.get("risk_score", 0.0) for h, r in result.items()
            }
            overall = sum(hazard_scores.values()) / max(len(hazard_scores), 1)

            # v3.2 (Gap Q): Use multi-RP trapezoidal EAL from workflow
            # if available; fall back to simplified estimate
            workflow_eal = result.get("portfolio_eal_usd") if isinstance(result, dict) else None
            if workflow_eal is not None:
                eal = round(workflow_eal, 2)
            elif site.asset_value_usd:
                # Fallback: simplified EAL = overall_risk × asset_value × 0.01
                eal = round(overall * site.asset_value_usd * 0.01, 2)
            else:
                eal = None

            return PortfolioSiteResult(
                location={
                    "lat": site.location.lat,
                    "lon": site.location.lon,
                    "name": site.location.name,
                },
                overall_risk_score=round(overall, 3),
                overall_risk_category=_score_to_category(overall),
                hazard_scores={k: round(v, 3) for k, v in hazard_scores.items()},
                asset_value_usd=site.asset_value_usd,
                expected_annual_loss_usd=eal,
                portfolio_eal_usd=workflow_eal,          # NEW v3.2 (Gap Q)
            )

    results = await asyncio.gather(*[_assess_one(s) for s in request.sites])
    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Portfolio summary
    all_scores = [r.overall_risk_score for r in results if r.overall_risk_category != "Error"]
    total_value = sum(s.asset_value_usd or 0 for s in request.sites)
    total_eal = sum(r.expected_annual_loss_usd or 0 for r in results)
    total_portfolio_eal = sum(r.portfolio_eal_usd or 0 for r in results)

    # v3.2: Determine actual return periods assessed
    rps_assessed = None
    if request.multi_rp:
        from src.core.models import STANDARD_RETURN_PERIODS
        rps_assessed = request.return_periods or STANDARD_RETURN_PERIODS

    return PortfolioResponse(
        n_sites=len(results),
        scenario=request.scenario.value,
        time_horizon=request.time_horizon,
        multi_rp=request.multi_rp,                       # NEW v3.2
        return_periods_assessed=rps_assessed,             # NEW v3.2
        sites=results,
        portfolio_summary={
            "mean_risk_score": round(sum(all_scores) / max(len(all_scores), 1), 3),
            "max_risk_score": round(max(all_scores, default=0), 3),
            "total_asset_value_usd": total_value,
            "total_expected_annual_loss_usd": round(total_eal, 2),
            "portfolio_eal_usd": round(total_portfolio_eal, 2),  # NEW v3.2 (Gap Q)
            "high_risk_sites": sum(1 for s in all_scores if s >= 0.6),
        },
        processing_time_ms=elapsed_ms,
    )
```

---

## 6. Buildings Route (v3.2: + multi-RP EAL, pluvial, occupancy)

```python
# src/api/routes/buildings.py
"""
POST /v1/buildings/assess — structure-level risk assessment.

v3.1: Per-building H×E×V at single return period.
v3.2 Changes:
  - multi_rp + return_periods params → multi-RP loop in workflow (Gap Q)
  - Per-building losses_by_return_period exposes full loss-exceedance curve
  - expected_annual_loss_usd now computed via trapezoidal integration (Gap Q)
  - pluvial_damage_ratio from pluvial flood tool (Gap M)
  - occupancy_class + replacement_value_source from Phase 3 tools (Gaps S/T)
"""

import time
from typing import List, Optional

from fastapi import APIRouter, HTTPException

from src.api.schemas.requests import BuildingAssessRequest
from src.api.schemas.responses import (
    BuildingAssessResponse, BuildingRiskItem, BuildingPortfolioSummary,
    ReturnPeriodLossItem,
)
from src.workflows.hazard_workflow import run_hazard_assessment

router = APIRouter()


@router.post("/buildings/assess", response_model=BuildingAssessResponse)
async def assess_buildings(request: BuildingAssessRequest):
    """
    Assess structure-level risk for all buildings within a radius.

    Runs the full 6-step workflow (v3.2):
      Step 0: Fetch buildings + create BuildingAdjustedSurface (Gap S)
      Steps 1-3: Hazard assessment (chronic → cyclone → acute × multi-RP)
      Step 4: Multi-RP H×E×V per building → trapezoidal EAL (Gap Q)
      Step 5: Composite aggregation + portfolio EAL

    v3.2: Returns per-building loss curves at each assessed return period,
    pluvial flood damage, occupancy class, and trapezoidal EAL.
    """
    start = time.monotonic()

    try:
        result = await run_hazard_assessment(
            lat=request.lat,
            lon=request.lon,
            city=request.city,
            return_period=request.return_period,
            time_horizon=int(request.time_horizon.split("-")[0]),
            slr_scenario=request.scenario.value,
            include_buildings=True,
            building_radius_m=request.radius_m,
            multi_rp=request.multi_rp,                  # NEW v3.2 (Gap Q)
            return_periods=request.return_periods,       # NEW v3.2 (Gap Q)
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Building data not available for this area: {e}. "
                   f"Run buildings_ingest.py --city {request.city} first.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Extract structure results from workflow output
    structure_results = getattr(result, "structure_results", [])
    portfolio_summary = getattr(result, "portfolio_summary", None)

    # v3.2: Determine actual return periods assessed
    rps_assessed = None
    if request.multi_rp:
        from src.core.models import STANDARD_RETURN_PERIODS
        rps_assessed = request.return_periods or STANDARD_RETURN_PERIODS

    # Build response items (cap at max_buildings)
    building_items = []
    for sr in structure_results[:request.max_buildings]:
        # ── v3.2 (Gap Q): Build per-building loss-exceedance curve ──
        rp_losses: Optional[List[ReturnPeriodLossItem]] = None
        raw_losses = getattr(sr, "losses_by_return_period", None)
        if raw_losses:
            rp_losses = [
                ReturnPeriodLossItem(
                    return_period=rpl.return_period,
                    annual_exceedance_probability=round(1.0 / rpl.return_period, 6),
                    flood_damage_ratio=rpl.flood_damage_ratio,
                    wind_damage_ratio=getattr(rpl, "wind_damage_ratio", None),
                    pluvial_damage_ratio=getattr(rpl, "pluvial_damage_ratio", None),
                    max_damage_ratio=rpl.max_damage_ratio,
                    estimated_loss_usd=getattr(rpl, "estimated_loss_usd", None),
                )
                for rpl in raw_losses
            ]

        building_items.append(BuildingRiskItem(
            building_id=sr.building_id,
            latitude=sr.latitude,
            longitude=sr.longitude,
            footprint_area_m2=sr.footprint_area_m2,
            vulnerability_class=sr.vulnerability_class.value,
            occupancy_class=getattr(sr, "occupancy_class", None),       # v3.2 (Gap T)
            flood_damage_ratio=sr.flood_damage_ratio,
            flood_depth_at_building_m=sr.flood_depth_at_building_m,
            pluvial_damage_ratio=getattr(sr, "pluvial_damage_ratio", None),  # v3.2 (Gap M)
            wind_damage_ratio=getattr(sr, "wind_damage_ratio", None),
            max_damage_ratio=sr.max_damage_ratio,
            risk_score=sr.combined_risk_score,
            risk_tier=sr.risk_tier.value,
            replacement_value_usd=sr.replacement_value_usd,
            replacement_value_source=getattr(
                sr, "replacement_value_source", None                    # v3.2 (Gap T)
            ),
            expected_annual_loss_usd=sr.expected_annual_loss_usd,
            losses_by_return_period=rp_losses,                          # v3.2 (Gap Q)
        ))

    # Build portfolio summary
    ps = BuildingPortfolioSummary(
        total_buildings=portfolio_summary.total_buildings if portfolio_summary else 0,
        buildings_by_tier={
            "critical": portfolio_summary.buildings_critical if portfolio_summary else 0,
            "high": portfolio_summary.buildings_high if portfolio_summary else 0,
            "moderate": portfolio_summary.buildings_moderate if portfolio_summary else 0,
            "low": portfolio_summary.buildings_low if portfolio_summary else 0,
        },
        total_replacement_value_usd=getattr(
            portfolio_summary, "total_replacement_value_usd", 0
        ),
        total_expected_annual_loss_usd=getattr(
            portfolio_summary, "total_expected_annual_loss_usd", 0
        ),
        portfolio_eal_usd=getattr(
            portfolio_summary, "total_expected_annual_loss_usd", None  # v3.2 alias
        ),
        mean_damage_ratio=getattr(portfolio_summary, "mean_damage_ratio", 0),
        pml_250yr_usd=getattr(portfolio_summary, "pml_250yr_usd", None),  # v3.2
    )

    return BuildingAssessResponse(
        center={"lat": request.lat, "lon": request.lon},
        radius_m=request.radius_m,
        city=request.city,
        scenario=request.scenario.value,
        return_period=request.return_period,
        multi_rp=request.multi_rp,                       # NEW v3.2
        return_periods_assessed=rps_assessed,             # NEW v3.2
        n_buildings=len(building_items),
        buildings=building_items,
        portfolio_summary=ps,
        data_sources=[
            "Google Open Buildings V3", "Google Open Buildings 2.5D Temporal",
            "Overture Maps Buildings", "JRC Global Flood Depth-Damage Functions",
            "Copernicus GLO-30 DEM", "GloFAS v4", "NEX-GDDP-CMIP6",
            "IPCC AR6 SLR Projections",                  # v3.2 (Gap K)
            "IBTrACS v04r01 + Holland (2008)",            # v3.2 (Gap P)
        ],
        processing_time_ms=elapsed_ms,
    )
```

---

## 7. Hazard-Specific Route (routes/hazards.py)

```python
# src/api/routes/hazards.py
"""GET /v1/hazards/{type} — hazard-specific lookups."""

from fastapi import APIRouter, Query, HTTPException

from src.core.models import SSPScenario

router = APIRouter()

HAZARD_MODULES = {
    "flood": "src.hazards.flood",
    "heat": "src.hazards.heat",
    "cyclone": "src.hazards.cyclone",
    "surge": "src.hazards.surge",
    "subsidence": "src.hazards.subsidence",
    "landslide": "src.hazards.landslide",
    "wind": "src.hazards.wind",
    "pluvial": "src.hazards.pluvial",  # NEW v3.2 (Gap M)
}


@router.get("/hazards/{hazard_type}")
async def get_hazard(
    hazard_type: str,
    lat: float = Query(..., ge=-60, le=60),
    lon: float = Query(..., ge=-180, le=180),
    return_period: int = Query(100, ge=2, le=1000),
    scenario: SSPScenario = Query(SSPScenario.SSP245),
):
    """
    Query a single hazard type for a location.

    Returns detailed hazard result including component data sources
    and intermediate values.
    """
    if hazard_type not in HAZARD_MODULES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown hazard type: {hazard_type}. "
                   f"Available: {list(HAZARD_MODULES.keys())}",
        )

    try:
        import importlib
        module = importlib.import_module(HAZARD_MODULES[hazard_type])
        assess_fn = getattr(module, f"assess_{hazard_type}")
        result = await assess_fn(
            lat=lat, lon=lon,
            return_period=return_period,
            scenario=scenario,
        )
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"Data unavailable: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hazards")
async def list_hazards():
    """List all available hazard types."""
    return {
        "hazards": [
            {
                "type": "flood",
                "description": "Riverine and coastal flood risk",
                "data_sources": ["NEX-GDDP-CMIP6", "GloFAS", "Copernicus GLO-30"],
            },
            {
                "type": "heat",
                "description": "Heat stress and urban heat island",
                "data_sources": ["NEX-GDDP-CMIP6", "ERA5-Land", "Landsat C02"],
            },
            {
                "type": "cyclone",
                "description": "Tropical cyclone wind and rainfall (Holland 2008)",
                "data_sources": ["IBTrACS v04r01", "NEX-GDDP-CMIP6"],
            },
            {
                "type": "surge",
                "description": "Coastal storm surge inundation",
                "data_sources": ["IBTrACS", "GEBCO", "Copernicus GLO-30"],
            },
            {
                "type": "subsidence",
                "description": "Land subsidence from groundwater extraction",
                "data_sources": ["Sentinel-1 InSAR"],
            },
            {
                "type": "landslide",
                "description": "Rainfall-triggered landslide susceptibility",
                "data_sources": ["NEX-GDDP-CMIP6", "Copernicus GLO-30", "SoilGrids", "Sentinel-2"],
            },
            {
                "type": "wind",
                "description": "Extreme wind speed hazard",
                "data_sources": ["ERA5-Land", "IBTrACS"],
            },
            {   # NEW v3.2 (Gap M)
                "type": "pluvial",
                "description": "Pluvial (surface water) flood from intense rainfall "
                               "exceeding drainage capacity",
                "data_sources": ["NEX-GDDP-CMIP6", "Copernicus GLO-30", "ERA5-Land"],
            },
        ]
    }
```

---

## 8. Authentication Middleware (middleware/auth.py)

```python
# src/api/middleware/auth.py
"""API key authentication middleware."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.config.settings import settings


# Paths that don't require authentication
PUBLIC_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Validate API key from X-API-Key header or ?api_key query param.

    Keys are stored in settings.API_KEYS (list of valid keys).
    Set ECOSHIELD_API_KEYS env var as comma-separated values.
    """

    async def dispatch(self, request: Request, call_next):
        # Skip auth for public paths
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # Check for API key
        api_key = (
            request.headers.get("X-API-Key")
            or request.query_params.get("api_key")
        )

        valid_keys = getattr(settings, "API_KEYS", [])

        # If no keys configured, allow all (dev mode)
        if not valid_keys:
            return await call_next(request)

        if not api_key or api_key not in valid_keys:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "detail": "Invalid or missing API key. "
                              "Pass via X-API-Key header or ?api_key param.",
                    "status_code": 401,
                },
            )

        return await call_next(request)
```

---

## 9. Rate Limiting Middleware (middleware/rate_limit.py)

```python
# src/api/middleware/rate_limit.py
"""Token-bucket rate limiting middleware."""

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-IP token-bucket rate limiter.

    Args:
        requests_per_minute: Maximum requests per minute per IP
    """

    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.rpm = requests_per_minute
        self.buckets: dict[str, dict] = defaultdict(
            lambda: {"tokens": requests_per_minute, "last_refill": time.monotonic()}
        )

    def _refill(self, bucket: dict) -> None:
        now = time.monotonic()
        elapsed = now - bucket["last_refill"]
        refill = elapsed * (self.rpm / 60.0)
        bucket["tokens"] = min(self.rpm, bucket["tokens"] + refill)
        bucket["last_refill"] = now

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path == "/health":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        bucket = self.buckets[client_ip]
        self._refill(bucket)

        if bucket["tokens"] < 1:
            retry_after = int(60 / self.rpm) + 1
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "detail": f"Max {self.rpm} requests/minute. Retry after {retry_after}s.",
                    "status_code": 429,
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        bucket["tokens"] -= 1
        return await call_next(request)
```

---

## 10. Error Handling (errors.py)

```python
# src/api/errors.py
"""Structured error handlers for the EcoShield API."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError


def register_error_handlers(app: FastAPI):
    """Register custom exception handlers."""

    @app.exception_handler(ValidationError)
    async def validation_error(request: Request, exc: ValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": "Validation Error",
                "detail": exc.errors(),
                "status_code": 422,
            },
        )

    @app.exception_handler(FileNotFoundError)
    async def data_not_found(request: Request, exc: FileNotFoundError):
        return JSONResponse(
            status_code=503,
            content={
                "error": "Data Unavailable",
                "detail": str(exc),
                "status_code": 503,
            },
        )

    @app.exception_handler(Exception)
    async def general_error(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "detail": str(exc),
                "status_code": 500,
            },
        )
```

---

## API Usage Examples

### Single-site assessment (v3.2: multi-RP + pluvial)

```bash
curl -X POST http://localhost:8000/v1/assess \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "location": {"lat": 10.8, "lon": 106.6, "name": "HCMC"},
    "hazards": ["flood", "heat", "subsidence", "pluvial"],
    "scenario": "ssp245",
    "time_horizon": "2041-2060",
    "return_period": 100,
    "multi_rp": true,
    "include_details": true
  }'
```

### Portfolio assessment (v3.2: multi-RP EAL)

```bash
curl -X POST http://localhost:8000/v1/portfolio \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "sites": [
      {"location": {"lat": 10.8, "lon": 106.6, "name": "HCMC"}, "asset_value_usd": 5000000},
      {"location": {"lat": -6.2, "lon": 106.8, "name": "Jakarta"}, "asset_value_usd": 8000000},
      {"location": {"lat": 14.6, "lon": 121.0, "name": "Manila"}, "asset_value_usd": 3000000}
    ],
    "scenario": "ssp585",
    "return_period": 100,
    "multi_rp": true
  }'
```

### Hazard-specific query (v3.2: pluvial flood)

```bash
# Pluvial flood — NEW v3.2
curl "http://localhost:8000/v1/hazards/pluvial?lat=10.8&lon=106.6&return_period=50&scenario=ssp245" \
  -H "X-API-Key: your-key"

# Riverine flood
curl "http://localhost:8000/v1/hazards/flood?lat=10.8&lon=106.6&return_period=100&scenario=ssp245" \
  -H "X-API-Key: your-key"
```

### Structure-level building assessment (v3.2: multi-RP loss curves)

```bash
curl -X POST http://localhost:8000/v1/buildings/assess \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "lat": 10.78,
    "lon": 106.70,
    "radius_m": 500,
    "city": "hcmc",
    "return_period": 100,
    "multi_rp": true,
    "scenario": "ssp245",
    "time_horizon": "2041-2060",
    "max_buildings": 500
  }'
```

### Custom return periods

```bash
# Override standard [10,25,50,100,250] with custom RPs
curl -X POST http://localhost:8000/v1/buildings/assess \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "lat": -6.21,
    "lon": 106.85,
    "city": "jakarta",
    "multi_rp": true,
    "return_periods": [20, 50, 100, 200, 500],
    "scenario": "ssp585"
  }'
```

### Backward-compatible single-RP mode

```bash
# Disable multi-RP to match v3.1 behavior
curl -X POST http://localhost:8000/v1/buildings/assess \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "lat": 10.78,
    "lon": 106.70,
    "city": "hcmc",
    "return_period": 100,
    "multi_rp": false
  }'
```

Example response (v3.2 — truncated):

```json
{
  "center": {"lat": 10.78, "lon": 106.70},
  "radius_m": 500,
  "city": "hcmc",
  "scenario": "ssp245",
  "return_period": 100,
  "multi_rp": true,
  "return_periods_assessed": [10, 25, 50, 100, 250],
  "n_buildings": 342,
  "buildings": [
    {
      "building_id": "8Q7X+M2_001",
      "latitude": 10.7812,
      "longitude": 106.7003,
      "footprint_area_m2": 85.3,
      "vulnerability_class": "class_iii",
      "occupancy_class": "residential",
      "flood_damage_ratio": 0.32,
      "flood_depth_at_building_m": 0.95,
      "pluvial_damage_ratio": 0.18,
      "wind_damage_ratio": null,
      "max_damage_ratio": 0.32,
      "risk_score": 32.0,
      "risk_tier": "moderate",
      "replacement_value_usd": 38000,
      "replacement_value_source": "jrc_country_occupancy",
      "expected_annual_loss_usd": 247.3,
      "losses_by_return_period": [
        {
          "return_period": 10,
          "annual_exceedance_probability": 0.1,
          "flood_damage_ratio": 0.08,
          "pluvial_damage_ratio": 0.05,
          "wind_damage_ratio": null,
          "max_damage_ratio": 0.08,
          "estimated_loss_usd": 3040
        },
        {
          "return_period": 25,
          "annual_exceedance_probability": 0.04,
          "flood_damage_ratio": 0.18,
          "pluvial_damage_ratio": 0.12,
          "wind_damage_ratio": null,
          "max_damage_ratio": 0.18,
          "estimated_loss_usd": 6840
        },
        {
          "return_period": 50,
          "annual_exceedance_probability": 0.02,
          "flood_damage_ratio": 0.25,
          "pluvial_damage_ratio": 0.15,
          "wind_damage_ratio": null,
          "max_damage_ratio": 0.25,
          "estimated_loss_usd": 9500
        },
        {
          "return_period": 100,
          "annual_exceedance_probability": 0.01,
          "flood_damage_ratio": 0.32,
          "pluvial_damage_ratio": 0.18,
          "wind_damage_ratio": null,
          "max_damage_ratio": 0.32,
          "estimated_loss_usd": 12160
        },
        {
          "return_period": 250,
          "annual_exceedance_probability": 0.004,
          "flood_damage_ratio": 0.41,
          "pluvial_damage_ratio": 0.22,
          "wind_damage_ratio": null,
          "max_damage_ratio": 0.41,
          "estimated_loss_usd": 15580
        }
      ]
    }
  ],
  "portfolio_summary": {
    "total_buildings": 342,
    "buildings_by_tier": {"critical": 12, "high": 67, "moderate": 148, "low": 115},
    "total_replacement_value_usd": 15840000,
    "total_expected_annual_loss_usd": 84568,
    "portfolio_eal_usd": 84568,
    "mean_damage_ratio": 0.18,
    "pml_250yr_usd": 4231200
  },
  "data_sources": [
    "Google Open Buildings V3", "Google Open Buildings 2.5D Temporal",
    "Overture Maps Buildings", "JRC Global Flood Depth-Damage Functions",
    "Copernicus GLO-30 DEM", "GloFAS v4", "NEX-GDDP-CMIP6",
    "IPCC AR6 SLR Projections", "IBTrACS v04r01 + Holland (2008)"
  ],
  "processing_time_ms": 8247
}
```

---

## Deployment

```bash
# Development
uvicorn src.api.main:app --reload --port 8000

# Production (with gunicorn)
gunicorn src.api.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 4 \
  --bind 0.0.0.0:8000 \
  --timeout 120
```

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e ".[api]"
EXPOSE 8000
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Previous Phase

← **Phase 4: Hazard Workflow** (`ECOSHIELD-PHASE4-WORKFLOW-v3_2.md`)
   Orchestrates all eight hazard modules + structure risk into a unified 6-step
   assessment pipeline with multi-RP loop and per-building trapezoidal EAL.

---

## v3.2 API Change Summary

| Change | Endpoints Affected | Gap |
|--------|-------------------|-----|
| `multi_rp` request param (default `true`) | `/assess`, `/portfolio`, `/buildings/assess` | Q |
| `return_periods` request param (custom RPs) | `/assess`, `/portfolio`, `/buildings/assess` | Q |
| `pluvial` hazard type in request + registry | All assessment endpoints + `/hazards/pluvial` | M |
| `return_periods_assessed` response field | `/assess`, `/portfolio`, `/buildings/assess` | Q |
| `portfolio_eal_usd` response field | `/portfolio`, `/buildings/assess` | Q |
| `losses_by_return_period` per-building array | `/buildings/assess` | Q |
| `pluvial_damage_ratio` per-building field | `/buildings/assess` | M |
| `occupancy_class` per-building field | `/buildings/assess` | T |
| `replacement_value_source` per-building field | `/buildings/assess` | T |
| `pml_250yr_usd` portfolio summary field | `/buildings/assess` | Q |
| `ReturnPeriodLossItem` new schema | `/buildings/assess` | Q |

### Backward Compatibility

All v3.2 additions are additive — no breaking changes:
- `multi_rp` defaults to `true` for new behavior; set `false` for v3.1 compatibility
- `return_periods` defaults to `null` (uses standard `[10,25,50,100,250]`)
- New response fields are `Optional` — `null` when `multi_rp=false`
- `pluvial` in default hazards list — clients sending explicit hazard lists unchanged

---

*EcoShield Phase 5 v3.2 | API Layer — Multi-RP EAL, Pluvial Flood, Per-Building Loss Curves*
