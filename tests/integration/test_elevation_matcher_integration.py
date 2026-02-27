# tests/integration/test_elevation_matcher_integration.py
"""
Integration tests verifying the elevation fallback and spatial matcher
zone leniency fixes work correctly in a realistic pipeline context.

These tests simulate the fetch_buildings_step flow:
1. elevation.get_elevation_footprint is called per building
2. SpatialMatcher.match selects the best footprint match
3. The resulting ground_elevation_m feeds downstream flood-depth calculations
"""

import builtins
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

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
)
from src.data.structure_expectations import get_expectation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_building(
    building_id: str,
    lat: float,
    lon: float,
    area_m2: float,
    height_m: float = 12.0,
    footprint_wkt: str = None,
) -> StructuralCharacteristics:
    if footprint_wkt is None:
        # Small polygon centred at lat/lon
        d = 0.0005
        footprint_wkt = (
            f"POLYGON (({lon - d} {lat - d}, {lon + d} {lat - d}, "
            f"{lon + d} {lat + d}, {lon - d} {lat + d}, {lon - d} {lat - d}))"
        )
    fp = BuildingFootprint(
        building_id=building_id,
        source=DataSource.GOOGLE_OPEN_BUILDINGS_V3,
        centroid=Location(lat=lat, lon=lon),
        area_m2=area_m2,
        footprint_wkt=footprint_wkt,
    )
    height = BuildingHeight(height_m=height_m)
    return StructuralCharacteristics(footprint=fp, height=height)


# ---------------------------------------------------------------------------
# Integration: elevation fallback feeds correct elevation to buildings
# ---------------------------------------------------------------------------
class TestElevationFallbackIntegration:
    """Verify the elevation fallback produces usable values, not 0.0,
    when shapely is unavailable — simulating a deployment scenario."""

    @patch("src.data.elevation._read_elevation_sync")
    def test_footprint_elevation_uses_centroid_when_shapely_missing(self, mock_sync):
        """Simulate asset_fetch._fetch_elev flow with missing shapely."""
        mock_sync.return_value = 5.2  # Realistic Hanoi elevation

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name in ("shapely.wkt", "rasterio.mask"):
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        building = _make_building("bldg_A", lat=21.034, lon=105.852, area_m2=45.0)
        wkt = building.footprint.footprint_wkt

        from src.data.elevation import _read_elevation_footprint_sync

        with patch("builtins.__import__", side_effect=fake_import):
            elev = _read_elevation_footprint_sync(wkt)

        # Must be the centroid sampled value, not 0.0
        assert elev == 5.2

        # The elevation would be assigned to the building
        building_with_elev = building.model_copy(
            update={"ground_elevation_m": elev}
        )
        assert building_with_elev.ground_elevation_m == 5.2
        # effective_ground_floor_m should be based on real elevation
        assert building_with_elev.effective_ground_floor_m > 0

    @patch("src.data.elevation._read_elevation_sync")
    def test_multiple_buildings_get_nonzero_elevation(self, mock_sync):
        """Multiple buildings should all get proper centroid elevation fallback."""
        # Return different elevations for different coordinates
        def elevation_by_coords(lat, lon):
            if lat > 21.035:
                return 6.1
            return 4.8

        mock_sync.side_effect = elevation_by_coords

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name in ("shapely.wkt", "rasterio.mask"):
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        buildings = [
            _make_building("bldg_1", lat=21.034, lon=105.852, area_m2=35.0),
            _make_building("bldg_2", lat=21.036, lon=105.853, area_m2=50.0),
        ]

        from src.data.elevation import _read_elevation_footprint_sync

        elevations = []
        with patch("builtins.__import__", side_effect=fake_import):
            for b in buildings:
                elev = _read_elevation_footprint_sync(b.footprint.footprint_wkt)
                elevations.append(elev)

        # No building should get 0.0
        assert all(e > 0 for e in elevations)
        assert elevations[0] == 4.8
        assert elevations[1] == 6.1


# ---------------------------------------------------------------------------
# Integration: spatial matcher pipeline with zone leniency guard
# ---------------------------------------------------------------------------
class TestSpatialMatcherLeniencyIntegration:
    """End-to-end test: SpatialMatcher.match should only apply zone leniency
    for non-converted commercial types."""

    def test_converted_hotel_not_inflated_in_adaptive_zone(self):
        """A CONVERTED_TUBE_HOUSE_HOTEL inside Hanoi Old Quarter must NOT
        have its QA plausibility inflated by zone leniency."""
        lat, lon = 21.034, 105.852  # Inside Hanoi Old Quarter zone

        # Building with tube-house dimensions (plausible for converted type)
        building = _make_building("bldg_conv", lat=lat, lon=lon, area_m2=40.0, height_m=12.0)

        ctx = SpatialMatchContext(
            structure_type=StructureType.CONVERTED_TUBE_HOUSE_HOTEL,
            structure_category=StructureCategory.COMMERCIAL,
        )

        matcher = SpatialMatcher()

        with patch("src.data.spatial_matcher.get_zone_leniency", return_value=1.5) as mock_leniency:
            results = matcher.match(lat, lon, [building], context=ctx)

        # get_zone_leniency should only be called from _footprint_plausibility
        # for non-converted commercial, NOT from _stage6_qa for converted.
        # Since CONVERTED_TUBE_HOUSE_HOTEL is a converted type, zone leniency
        # should NOT be called at all (neither in stage 3 nor stage 6).
        mock_leniency.assert_not_called()

    def test_pure_hotel_receives_leniency_in_adaptive_zone(self):
        """A pure HOTEL inside Hanoi Old Quarter should get zone leniency."""
        lat, lon = 21.034, 105.852

        # Building with small area — would normally fail hotel plausibility
        building = _make_building("bldg_hotel", lat=lat, lon=lon, area_m2=40.0, height_m=12.0)

        ctx = SpatialMatchContext(
            structure_type=StructureType.HOTEL,
            structure_category=StructureCategory.COMMERCIAL,
        )

        matcher = SpatialMatcher()

        with patch("src.data.spatial_matcher.get_zone_leniency", return_value=1.5) as mock_leniency:
            results = matcher.match(lat, lon, [building], context=ctx)

        # get_zone_leniency should be called (from both stage 3 plausibility
        # and stage 6 QA for pure commercial types)
        assert mock_leniency.call_count >= 1

    def test_residential_not_inflated_in_adaptive_zone(self):
        """Residential TUBE_HOUSE inside a zone should NOT get leniency."""
        lat, lon = 21.034, 105.852

        building = _make_building("bldg_res", lat=lat, lon=lon, area_m2=40.0, height_m=12.0)

        ctx = SpatialMatchContext(
            structure_type=StructureType.TUBE_HOUSE,
            structure_category=StructureCategory.RESIDENTIAL,
        )

        matcher = SpatialMatcher()

        with patch("src.data.spatial_matcher.get_zone_leniency", return_value=1.5) as mock_leniency:
            results = matcher.match(lat, lon, [building], context=ctx)

        mock_leniency.assert_not_called()
