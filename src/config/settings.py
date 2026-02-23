# src/config/settings.py
"""
Application Configuration Settings.

Uses pydantic-settings to load environment variables from .env file.
"""

from pathlib import Path
from typing import List, Optional
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global application settings."""
    
    # --- Project Paths ---
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Path = PROJECT_ROOT / "data"

    @computed_field
    def CACHE_DIR(self) -> Path:
        return self.DATA_DIR / "cache"

    # --- Data Source Caches ---
    @computed_field
    def NEX_GDDP_LOCAL_CACHE(self) -> Path:
        return self.CACHE_DIR / "nex-gddp-cmip6"

    @computed_field
    def COPERNICUS_DEM_LOCAL_CACHE(self) -> Path:
        return self.CACHE_DIR / "copernicus-dem"

    @computed_field
    def INSAR_PATH(self) -> Path:
        return self.CACHE_DIR / "insar"

    @computed_field
    def IBTRACS_PATH(self) -> Path:
        return self.CACHE_DIR / "ibtracs"

    @computed_field
    def ERA5_PATH(self) -> Path:
        return self.CACHE_DIR / "era5"

    @computed_field
    def GLOFAS_PATH(self) -> Path:
        return self.CACHE_DIR / "glofas"

    @computed_field
    def BUILDINGS_PATH(self) -> Path:
        return self.CACHE_DIR / "buildings"

    # --- External API Keys ---
    CDS_API_KEY: Optional[str] = None
    CDS_API_URL: str = "https://cds.climate.copernicus.eu/api/v2"
    
    GEE_SERVICE_ACCOUNT: Optional[str] = None
    GEE_KEY_FILE: Optional[str] = None
    GEE_PROJECT: str = "earth-engine-487123"
    
    NASA_EARTHDATA_TOKEN: Optional[str] = None

    # --- Database (PostgreSQL) ---
    POSTGRES_USER: str = "ecoshield"
    POSTGRES_PASSWORD: str = "ecoshield"  # Override via POSTGRES_PASSWORD env var in production
    POSTGRES_DB: str = "ecoshield"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432

    @computed_field
    def DATABASE_URL(self) -> str:
        """Construct PostgreSQL connection string."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # --- API Security ---
    CORS_ORIGINS: List[str] = ["*"]  # Override in production with allowed origins

    # --- AWS S3 Buckets (Public) ---
    NEX_GDDP_S3_BUCKET: str = "nex-gddp-cmip6"
    COPERNICUS_DEM_S3_BUCKET: str = "copernicus-dem-30m"
    OVERTURE_S3_BUCKET: str = "overturemaps-us-west-2"

    # --- Model Configuration ---
    NEX_GDDP_MODELS: List[str] = [
        "ACCESS-CM2", 
        "CMCC-ESM2", 
        "EC-Earth3", 
        "MPI-ESM1-2-HR", 
        "MRI-ESM2-0"
    ]

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def create_dirs(self):
        """Ensure all cache directories exist."""
        for path in [
            self.CACHE_DIR,
            self.NEX_GDDP_LOCAL_CACHE,
            self.COPERNICUS_DEM_LOCAL_CACHE,
            self.INSAR_PATH,
            self.IBTRACS_PATH,
            self.ERA5_PATH,
            self.GLOFAS_PATH,
            self.BUILDINGS_PATH,
        ]:
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
# Create directories on import (or explicit call)
# settings.create_dirs()
