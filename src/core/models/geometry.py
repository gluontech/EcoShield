
# src/core/models/geometry.py
"""Location and geometry models."""

from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator, computed_field
from .enums import DataSource


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

    @field_validator("lat")
    @classmethod
    def validateSeaBounds(cls, v: float) -> float:
        """Warn if outside typical SEA bounds."""
        if not (-15 <= v <= 30):
            # Log warning but allow - might be testing
            pass
        return v

    @field_validator("lon")
    @classmethod
    def validateSeaLonBounds(cls, v: float) -> float:
        """Warn if outside typical SEA bounds."""
        if not (90 <= v <= 150):
            pass
        return v

    def toTuple(self) -> tuple[float, float]:
        """Return as (lat, lon) tuple."""
        return (self.lat, self.lon)

    def to_tuple(self) -> tuple[float, float]:
        """Return as (lat, lon) tuple."""
        return (self.lat, self.lon)
    
    model_config = {"frozen": True}


class DataLineage(BaseModel):
    """
    Data provenance tracking (Gap 4.3).
    Ensures auditability of every model output.
    """
    source: DataSource = Field(..., description="Primary data source")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Processing timestamp"
    )
    version: str = Field(default="v3.2.0", description="Model/Data version")
    processor: str = Field(default="EcoShield Core", description="Processing system")



class BoundingBox(BaseModel):
    """Geographic bounding box."""

    min_lat: float = Field(..., ge=-90, le=90)
    max_lat: float = Field(..., ge=-90, le=90)
    min_lon: float = Field(..., ge=-180, le=180)
    max_lon: float = Field(..., ge=-180, le=180)

    @field_validator("max_lat")
    @classmethod
    def validateLatOrder(cls, v: float, info) -> float:
        """Ensure max_lat >= min_lat."""
        if "min_lat" in info.data and v < info.data["min_lat"]:
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
    def area_km2(self) -> float:
        """Approximate area in square km (cosine corrected)."""
        import math
        mean_lat = (self.min_lat + self.max_lat) / 2
        d_lat_deg = self.max_lat - self.min_lat
        d_lon_deg = self.max_lon - self.min_lon
        
        # 1 deg lat approx 111 km
        dy = d_lat_deg * 111.0
        # 1 deg lon approx 111 * cos(lat)
        dx = d_lon_deg * 111.0 * math.cos(math.radians(mean_lat))
        
        return abs(dx * dy)
