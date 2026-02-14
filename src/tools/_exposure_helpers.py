# src/tools/_exposure_helpers.py
"""Shared helpers for building ExposureProfile in hazard tools."""

from src.core.models import (
    Location, ExposureProfile, StructuralCharacteristics,
    BuildingFootprint, DataSource,
)


def build_point_exposure(
    lat: float,
    lon: float,
    elevation_m: float,
    elevation_source: str = "copernicus_glo30",
    **extra_fields,
) -> ExposureProfile:
    """
    Build an ExposureProfile for a point assessment (no specific building).

    Creates a placeholder StructuralCharacteristics anchored at the point.
    """
    footprint = BuildingFootprint(
        building_id=f"point_{lat:.4f}_{lon:.4f}",
        source=DataSource.COPERNICUS_GLO30,
        centroid=Location(lat=lat, lon=lon),
        area_m2=1.0,
    )
    structure = StructuralCharacteristics(
        footprint=footprint,
        ground_elevation_m=elevation_m,
    )
    return ExposureProfile(
        location=Location(lat=lat, lon=lon),
        structure=structure,
        elevation_m=elevation_m,
        elevation_source=elevation_source,
        **extra_fields,
    )
