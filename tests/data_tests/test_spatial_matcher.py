# tests/data_tests/test_spatial_matcher.py
"""
Unit tests for spatial_matcher.py, focusing on:
- Stage 6 QA zone leniency should only apply for non-converted commercial types
- Converted types, residential, and industrial types must NOT receive zone leniency
"""

import pytest
from unittest.mock import patch, MagicMock

from src.core.models.enums import (
    DataSource,
    StructureCategory,
    StructureType,
)
from src.core.models.geometry import Location
from src.core.models.asset import (
    BuildingFootprint,
    BuildingHeight,
    StructuralCharacteristics,
)
from src.data.spatial_matcher import (
    SpatialMatcher,
    SpatialMatchContext,
    SpatialMatchResult,
)
from src.data.structure_expectations import get_expectation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_structure(
    building_id: str = "bldg_001",
    lat: float = 21.034,
    lon: float = 105.852,
    area_m2: float = 40.0,
    height_m: float = 12.0,
    footprint_wkt: str = "POLYGON ((105.851 21.033, 105.853 21.033, 105.853 21.035, 105.851 21.035, 105.851 21.033))",
) -> StructuralCharacteristics:
    fp = BuildingFootprint(
        building_id=building_id,
        source=DataSource.GOOGLE_OPEN_BUILDINGS_V3,
        centroid=Location(lat=lat, lon=lon),
        area_m2=area_m2,
        footprint_wkt=footprint_wkt,
    )
    height = BuildingHeight(height_m=height_m) if height_m else None
    return StructuralCharacteristics(footprint=fp, height=height)


def _make_candidate(
    structure: StructuralCharacteristics,
    confidence: float = 0.85,
) -> SpatialMatchResult:
    return SpatialMatchResult(
        structure=structure,
        confidence=confidence,
        containment=True,
        match_method="containment",
    )


# Hanoi Old Quarter coordinates — inside an AdaptiveReuseZone (leniency 1.5)
_HANOI_OQ_LAT = 21.034
_HANOI_OQ_LON = 105.852


# ---------------------------------------------------------------------------
# Stage 6 zone leniency restriction
# ---------------------------------------------------------------------------
class TestStage6ZoneLeniency:
    """Zone leniency in _stage6_qa must only apply for non-converted commercial."""

    def _run_qa(
        self,
        structure_type: StructureType,
        structure_category: StructureCategory,
        lat: float = _HANOI_OQ_LAT,
        lon: float = _HANOI_OQ_LON,
    ):
        """Run Stage 6 QA and return the plausibility score used."""
        matcher = SpatialMatcher()
        structure = _make_structure(lat=lat, lon=lon, area_m2=40.0, height_m=12.0)
        candidate = _make_candidate(structure, confidence=0.85)

        ctx = SpatialMatchContext(
            structure_type=structure_type,
            structure_category=structure_category,
            expectation=get_expectation(structure_type, structure_category),
        )

        # Capture the plausibility score and leniency via the log message
        plausibility_data = {}

        original_stage6 = matcher._stage6_qa

        def spy_stage6(scored, lat, lon, all_candidates, context):
            # Intercept to capture pscore before/after leniency
            return original_stage6(scored, lat, lon, all_candidates, context)

        result = matcher._stage6_qa(
            scored=[candidate],
            lat=lat,
            lon=lon,
            all_candidates=[candidate],
            context=ctx,
        )
        return result

    def test_commercial_hotel_gets_leniency_inside_zone(self):
        """A pure HOTEL (commercial, non-converted) inside Hanoi OQ should get leniency."""
        # Use a small area that would fail plausibility for HOTEL without leniency
        matcher = SpatialMatcher()
        # HOTEL expects area 200-50000m², height 10-200m
        # 40m² is way too small — but leniency should boost the score
        structure = _make_structure(area_m2=40.0, height_m=12.0)
        candidate = _make_candidate(structure, confidence=0.85)

        ctx = SpatialMatchContext(
            structure_type=StructureType.HOTEL,
            structure_category=StructureCategory.COMMERCIAL,
            expectation=get_expectation(StructureType.HOTEL),
        )

        with patch("src.data.spatial_matcher.get_zone_leniency", return_value=1.5) as mock_leniency:
            matcher._stage6_qa(
                scored=[candidate],
                lat=_HANOI_OQ_LAT,
                lon=_HANOI_OQ_LON,
                all_candidates=[candidate],
                context=ctx,
            )
            mock_leniency.assert_called_once()

    def test_converted_tube_house_hotel_no_leniency(self):
        """CONVERTED_TUBE_HOUSE_HOTEL must NOT receive zone leniency in Stage 6."""
        matcher = SpatialMatcher()
        structure = _make_structure(area_m2=40.0, height_m=12.0)
        candidate = _make_candidate(structure, confidence=0.85)

        ctx = SpatialMatchContext(
            structure_type=StructureType.CONVERTED_TUBE_HOUSE_HOTEL,
            structure_category=StructureCategory.COMMERCIAL,
            expectation=get_expectation(StructureType.CONVERTED_TUBE_HOUSE_HOTEL),
        )

        with patch("src.data.spatial_matcher.get_zone_leniency", return_value=1.5) as mock_leniency:
            matcher._stage6_qa(
                scored=[candidate],
                lat=_HANOI_OQ_LAT,
                lon=_HANOI_OQ_LON,
                all_candidates=[candidate],
                context=ctx,
            )
            mock_leniency.assert_not_called()

    def test_residential_tube_house_no_leniency(self):
        """TUBE_HOUSE (residential) must NOT receive zone leniency in Stage 6."""
        matcher = SpatialMatcher()
        structure = _make_structure(area_m2=40.0, height_m=12.0)
        candidate = _make_candidate(structure, confidence=0.85)

        ctx = SpatialMatchContext(
            structure_type=StructureType.TUBE_HOUSE,
            structure_category=StructureCategory.RESIDENTIAL,
            expectation=get_expectation(StructureType.TUBE_HOUSE),
        )

        with patch("src.data.spatial_matcher.get_zone_leniency", return_value=1.5) as mock_leniency:
            matcher._stage6_qa(
                scored=[candidate],
                lat=_HANOI_OQ_LAT,
                lon=_HANOI_OQ_LON,
                all_candidates=[candidate],
                context=ctx,
            )
            mock_leniency.assert_not_called()

    def test_industrial_warehouse_no_leniency(self):
        """WAREHOUSE (industrial) must NOT receive zone leniency in Stage 6."""
        matcher = SpatialMatcher()
        structure = _make_structure(area_m2=300.0, height_m=8.0)
        candidate = _make_candidate(structure, confidence=0.85)

        ctx = SpatialMatchContext(
            structure_type=StructureType.WAREHOUSE,
            structure_category=StructureCategory.INDUSTRIAL,
            expectation=get_expectation(StructureType.WAREHOUSE),
        )

        with patch("src.data.spatial_matcher.get_zone_leniency", return_value=1.5) as mock_leniency:
            matcher._stage6_qa(
                scored=[candidate],
                lat=_HANOI_OQ_LAT,
                lon=_HANOI_OQ_LON,
                all_candidates=[candidate],
                context=ctx,
            )
            mock_leniency.assert_not_called()

    def test_no_structure_type_no_leniency(self):
        """When structure_type is None, leniency must NOT be applied."""
        matcher = SpatialMatcher()
        structure = _make_structure(area_m2=40.0, height_m=12.0)
        candidate = _make_candidate(structure, confidence=0.85)

        ctx = SpatialMatchContext(
            structure_type=None,
            structure_category=StructureCategory.COMMERCIAL,
            expectation=get_expectation(None, StructureCategory.COMMERCIAL),
        )

        with patch("src.data.spatial_matcher.get_zone_leniency", return_value=1.5) as mock_leniency:
            matcher._stage6_qa(
                scored=[candidate],
                lat=_HANOI_OQ_LAT,
                lon=_HANOI_OQ_LON,
                all_candidates=[candidate],
                context=ctx,
            )
            mock_leniency.assert_not_called()

    def test_commercial_outside_zone_leniency_is_one(self):
        """Commercial type outside any zone gets leniency=1.0 (no effect)."""
        matcher = SpatialMatcher()
        structure = _make_structure(
            lat=10.77, lon=106.70, area_m2=40.0, height_m=12.0,
        )
        candidate = _make_candidate(structure, confidence=0.85)

        ctx = SpatialMatchContext(
            structure_type=StructureType.HOTEL,
            structure_category=StructureCategory.COMMERCIAL,
            expectation=get_expectation(StructureType.HOTEL),
        )

        # Outside any zone, get_zone_leniency returns 1.0
        with patch("src.data.spatial_matcher.get_zone_leniency", return_value=1.0) as mock_leniency:
            matcher._stage6_qa(
                scored=[candidate],
                lat=10.77,
                lon=106.70,
                all_candidates=[candidate],
                context=ctx,
            )
            mock_leniency.assert_called_once()


# ---------------------------------------------------------------------------
# _footprint_plausibility consistency check
# ---------------------------------------------------------------------------
class TestFootprintPlausibilityLeniency:
    """_footprint_plausibility already guards leniency correctly — verify it."""

    def test_converted_type_no_leniency_in_plausibility(self):
        """Converted type must NOT receive zone leniency in _footprint_plausibility."""
        matcher = SpatialMatcher()
        structure = _make_structure(area_m2=40.0, height_m=12.0)

        ctx = SpatialMatchContext(
            structure_type=StructureType.CONVERTED_TUBE_HOUSE_HOTEL,
            structure_category=StructureCategory.COMMERCIAL,
            expectation=get_expectation(StructureType.CONVERTED_TUBE_HOUSE_HOTEL),
        )

        with patch("src.data.spatial_matcher.get_zone_leniency", return_value=1.5) as mock_leniency:
            matcher._footprint_plausibility(
                structure, ctx, _HANOI_OQ_LAT, _HANOI_OQ_LON,
            )
            mock_leniency.assert_not_called()

    def test_commercial_hotel_gets_leniency_in_plausibility(self):
        """Pure commercial HOTEL gets zone leniency in _footprint_plausibility."""
        matcher = SpatialMatcher()
        structure = _make_structure(area_m2=40.0, height_m=12.0)

        ctx = SpatialMatchContext(
            structure_type=StructureType.HOTEL,
            structure_category=StructureCategory.COMMERCIAL,
            expectation=get_expectation(StructureType.HOTEL),
        )

        with patch("src.data.spatial_matcher.get_zone_leniency", return_value=1.5) as mock_leniency:
            matcher._footprint_plausibility(
                structure, ctx, _HANOI_OQ_LAT, _HANOI_OQ_LON,
            )
            mock_leniency.assert_called_once()
