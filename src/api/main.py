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

from src.api.routes import assess, portfolio, hazards, buildings
# from src.api.middleware.auth import APIKeyMiddleware # Deferred
# from src.api.middleware.rate_limit import RateLimitMiddleware # Deferred
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
    title="EcoShield Climate Intelligence API",
    description=(
        "Multi-hazard climate risk assessment for Southeast Asia. "
        "Covers flood, heat stress, cyclone, storm surge, subsidence, "
        "landslide, wind, and pluvial flood hazards. Features Multi-RP "
        "EAL via trapezoidal integration, per-building loss curves, "
        "pluvial flood (8th hazard), and occupancy-scaled replacement values."
    ),
    version="1.0",
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
# app.add_middleware(APIKeyMiddleware) # Deferred
# app.add_middleware(RateLimitMiddleware, requests_per_minute=60) # Deferred

# ── Error handlers ──────────────────────────────────────
register_error_handlers(app)

# ── Routes ──────────────────────────────────────────────
app.include_router(assess.router, prefix="/v1", tags=["Assessment"])
app.include_router(portfolio.router, prefix="/v1", tags=["Portfolio"])
app.include_router(buildings.router, prefix="/v1", tags=["Buildings"])
app.include_router(hazards.router, prefix="/v1", tags=["Hazards"])


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "1.0.0"}
