# tests/unit/data/test_spatial_matcher.py
"""
Unit tests for SpatialMatcher match_method handling and schema compatibility.
"""

from __future__ import annotations

import pytest

from src.core.models.enums import DataSource, MatchMethod
from src.core.models.geometry import Location
from src.core.models.asset import (
    BuildingFootprint,
    BuildingHeight,
    StructuralCharacteristics,
)
from src.core.models.response_models import BuildingFootprint as ResponseBuildingFootprint
from src.data.spatial_matcher import (
    SpatialMatcher,
    SpatialMatchContext,
    SpatialMatchResult,
)


def _make_structure(
    building_id: str = "bldg_test_001",
    lat: float = 10.7726,
    lon: float = 106.6980,
    area_m2: float = 150.0,
    height_m: float = 8.0,
) -> StructuralCharacteristics:
    fp = BuildingFootprint(
        building_id=building_id,
        source=DataSource.GOOGLE_OPEN_BUILDINGS_V3,
        centroid=Location(lat=lat, lon=lon),
        area_m2=area_m2,
        footprint_wkt="POLYGON ((106.697 10.772, 106.699 10.772, 106.699 10.773, 106.697 10.773, 106.697 10.772))",
    )
    height = BuildingHeight(height_m=height_m)
    return StructuralCharacteristics(footprint=fp, height=height)


def test_spatial_matcher_low_confidence_match_method_valid_enum() -> None:
    """Ensure low-confidence match_method emitted by SpatialMatcher is a valid MatchMethod enum value."""
    matcher = SpatialMatcher()
    
    # Candidate far away with low confidence (will fail confidence threshold QA)
    struct = _make_structure(lat=10.8000, lon=106.8000)
    
    # Artificially score candidate with buffer_overlap and low confidence
    candidate = SpatialMatchResult(
        structure=struct,
        confidence=0.10,  # Below CONFIDENCE_REJECT threshold (0.40)
        match_method="buffer_overlap",
        containment=False,
    )
    
    context = SpatialMatchContext(name="Test Low Confidence", city="hcmc")
    
    # Stage 6 QA filter fallback
    results = matcher._stage6_qa([candidate], lat=10.7726, lon=106.6980, all_candidates=[candidate], context=context)
    
    assert len(results) == 1
    assert results[0].match_method == "buffer_overlap_low_confidence"
    # Verify it can be successfully converted to MatchMethod enum
    enum_val = MatchMethod(results[0].match_method)
    assert enum_val == MatchMethod.BUFFER_OVERLAP_LOW_CONFIDENCE


def test_response_building_footprint_accepts_low_confidence_match_methods() -> None:
    """Verify response model BuildingFootprint validates buffer_overlap_low_confidence without 422 error."""
    raw_footprint = {
        "building_id": "bldg_123",
        "source": "google_open_buildings_v3",
        "centroid": {"lat": 10.7726, "lon": 106.6980},
        "footprint_wkt": "POLYGON ((106.697 10.772, 106.699 10.772, 106.699 10.773, 106.697 10.773, 106.697 10.772))",
        "area_m2": 120.0,
        "confidence": 0.35,
        "match_method": "buffer_overlap_low_confidence",
        "footprint_match_confidence": 0.35,
    }
    
    validated = ResponseBuildingFootprint.model_validate(raw_footprint)
    assert validated.match_method == MatchMethod.BUFFER_OVERLAP_LOW_CONFIDENCE
