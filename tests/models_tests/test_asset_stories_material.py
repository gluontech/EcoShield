# tests/models_tests/test_asset_stories_material.py
"""Tests for occupancy-aware story estimation and improved material inference.

Covers:
- BuildingHeight.estimated_stories is synced by StructuralCharacteristics
- StructuralCharacteristics.num_stories uses occupancy-aware floor heights
- StructuralCharacteristics.num_stories prefers actual num_floors
- estimated_stories == num_stories in all cases
- Overture material inference considers footprint area
"""

import pytest

from src.core.models.asset import (
    BuildingFootprint,
    BuildingHeight,
    StructuralCharacteristics,
    _FLOOR_HEIGHT_BY_OCCUPANCY,
)
from src.core.models.enums import (
    BuildingMaterial,
    BuildingOccupancy,
    DataSource,
    VulnerabilityClass,
)
from src.core.models.geometry import Location
from src.data.overture_buildings import OvertureBuildingsSource


# ---------------------------------------------------------------------------
# BuildingHeight.estimated_stories (standalone, before StructuralCharacteristics)
# ---------------------------------------------------------------------------


class TestBuildingHeightEstimatedStories:
    """estimated_stories is a plain field on BuildingHeight.

    Before being wrapped in StructuralCharacteristics it is None
    unless num_floors was provided by the data source.
    """

    def test_no_num_floors_defaults_none(self) -> None:
        h = BuildingHeight(height_m=46.0, height_year=2023)
        assert h.estimated_stories is None

    def test_with_num_floors(self) -> None:
        h = BuildingHeight(height_m=46.0, height_year=2023, num_floors=5,
                           estimated_stories=5)
        assert h.estimated_stories == 5


# ---------------------------------------------------------------------------
# StructuralCharacteristics — num_stories + estimated_stories sync
# ---------------------------------------------------------------------------


class TestStructuralCharacteristicsNumStories:
    """Validate occupancy-aware floor estimation and sync to estimated_stories."""

    @staticmethod
    def _make_footprint(area_m2: float = 100.0) -> BuildingFootprint:
        return BuildingFootprint(
            building_id="test",
            source=DataSource.GOOGLE_OPEN_BUILDINGS_V3,
            centroid=Location(lat=10.7, lon=106.7),
            area_m2=area_m2,
        )

    def test_no_height_returns_none(self) -> None:
        """No height data at all → both num_stories and estimated_stories are None."""
        sc = StructuralCharacteristics(footprint=self._make_footprint())
        assert sc.num_stories is None

    def test_actual_num_floors_takes_priority(self) -> None:
        """When num_floors exists, it's used and synced to estimated_stories."""
        h = BuildingHeight(height_m=46.0, height_year=2023, num_floors=5)
        sc = StructuralCharacteristics(
            footprint=self._make_footprint(),
            height=h,
        )
        assert sc.num_stories == 5
        assert sc.height.estimated_stories == 5

    def test_commercial_46m_uses_4_5m_floor(self) -> None:
        """A 46m commercial building: round(46/4.5) = 10 stories."""
        h = BuildingHeight(height_m=46.0, height_year=2023)
        sc = StructuralCharacteristics(
            footprint=self._make_footprint(area_m2=8800.0),
            height=h,
            occupancy=BuildingOccupancy.COMMERCIAL,
        )
        assert sc.num_stories == 10  # round(46.0 / 4.5)
        assert sc.height.estimated_stories == 10

    def test_residential_single_3m_floor(self) -> None:
        """Residential single: 3m/floor → 12m = 4 stories."""
        h = BuildingHeight(height_m=12.0, height_year=2023)
        sc = StructuralCharacteristics(
            footprint=self._make_footprint(),
            height=h,
            occupancy=BuildingOccupancy.RESIDENTIAL_SINGLE,
        )
        assert sc.num_stories == 4
        assert sc.height.estimated_stories == 4

    def test_residential_multi_3m_floor(self) -> None:
        """Residential multi: 3m/floor → 30m = 10 stories."""
        h = BuildingHeight(height_m=30.0, height_year=2023)
        sc = StructuralCharacteristics(
            footprint=self._make_footprint(area_m2=500.0),
            height=h,
            occupancy=BuildingOccupancy.RESIDENTIAL_MULTI,
        )
        assert sc.num_stories == 10
        assert sc.height.estimated_stories == 10

    def test_industrial_6m_floor(self) -> None:
        """Industrial: 6m/floor → 12m = 2 stories."""
        h = BuildingHeight(height_m=12.0, height_year=2023)
        sc = StructuralCharacteristics(
            footprint=self._make_footprint(area_m2=2000.0),
            height=h,
            occupancy=BuildingOccupancy.INDUSTRIAL,
        )
        assert sc.num_stories == 2
        assert sc.height.estimated_stories == 2

    def test_institutional_4m_floor(self) -> None:
        """Institutional: 4m/floor → 16m = 4 stories."""
        h = BuildingHeight(height_m=16.0, height_year=2023)
        sc = StructuralCharacteristics(
            footprint=self._make_footprint(area_m2=5000.0),
            height=h,
            occupancy=BuildingOccupancy.INSTITUTIONAL,
        )
        assert sc.num_stories == 4
        assert sc.height.estimated_stories == 4

    def test_unknown_occupancy_uses_default(self) -> None:
        """Unknown occupancy: 3.5m/floor → 14m = 4 stories."""
        h = BuildingHeight(height_m=14.0, height_year=2023)
        sc = StructuralCharacteristics(
            footprint=self._make_footprint(),
            height=h,
            occupancy=BuildingOccupancy.UNKNOWN,
        )
        assert sc.num_stories == 4
        assert sc.height.estimated_stories == 4

    def test_minimum_one_story(self) -> None:
        """Even a very short building estimates at least 1 story."""
        h = BuildingHeight(height_m=1.5, height_year=2023)
        sc = StructuralCharacteristics(
            footprint=self._make_footprint(),
            height=h,
        )
        assert sc.num_stories >= 1
        assert sc.height.estimated_stories >= 1

    def test_estimated_stories_always_equals_num_stories(self) -> None:
        """When height exists, estimated_stories must equal num_stories."""
        for occ in BuildingOccupancy:
            h = BuildingHeight(height_m=20.0, height_year=2023)
            sc = StructuralCharacteristics(
                footprint=self._make_footprint(),
                height=h,
                occupancy=occ,
            )
            assert sc.height.estimated_stories == sc.num_stories, (
                f"Mismatch for {occ.value}: estimated_stories="
                f"{sc.height.estimated_stories}, num_stories={sc.num_stories}"
            )

    def test_all_occupancies_have_floor_height(self) -> None:
        """Every BuildingOccupancy value must have a floor height entry."""
        for occ in BuildingOccupancy:
            assert occ in _FLOOR_HEIGHT_BY_OCCUPANCY, (
                f"Missing floor height for {occ.value}"
            )


# ---------------------------------------------------------------------------
# Overture material inference
# ---------------------------------------------------------------------------


class TestOvertureMaterialInference:
    """Validate improved material inference considers area + height."""

    @staticmethod
    def _convert(buildings: list[dict], city: str = "unknown"):
        src = OvertureBuildingsSource()
        enriched = src.enrich_with_osm_tags(buildings)
        return src.to_structural_characteristics(enriched, city=city)

    @staticmethod
    def _make_building(
        area_m2: float,
        height: float | None = None,
        num_floors: int | None = None,
    ) -> dict:
        return {
            "id": "test-id",
            "geometry_wkt": "POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))",
            "area_m2": area_m2,
            "centroid_lat": 10.728,
            "centroid_lon": 106.718,
            "height": height,
            "num_floors": num_floors,
            "class": None,
            "subtype": None,
            "sources": [],
            "names": None,
        }

    def test_large_area_no_height_is_reinforced(self) -> None:
        """A large-footprint building (>1000 m²) → reinforced concrete."""
        buildings = [self._make_building(area_m2=8800.0)]
        results = self._convert(buildings)
        assert len(results) == 1
        assert results[0].material == BuildingMaterial.CONCRETE_REINFORCED
        assert results[0].vulnerability_class == VulnerabilityClass.CLASS_IV_REINFORCED

    def test_tall_building_is_reinforced(self) -> None:
        """Height > 15m → reinforced concrete (unchanged behavior)."""
        buildings = [self._make_building(area_m2=200.0, height=20.0)]
        results = self._convert(buildings)
        assert results[0].material == BuildingMaterial.CONCRETE_REINFORCED

    def test_small_area_is_bamboo(self) -> None:
        """Area < 30 m² → bamboo/thatch (unchanged behavior)."""
        buildings = [self._make_building(area_m2=20.0)]
        results = self._convert(buildings)
        assert results[0].material == BuildingMaterial.BAMBOO_THATCH

    def test_medium_area_no_height_is_masonry(self) -> None:
        """Area 30–1000 m², no height → default masonry (unchanged behavior)."""
        buildings = [self._make_building(area_m2=500.0)]
        results = self._convert(buildings)
        assert results[0].material == BuildingMaterial.MASONRY_UNREINFORCED

    def test_crescent_mall_scenario(self) -> None:
        """Crescent Mall: 8822 m², 46m height, no num_floors.

        Must be concrete_reinforced, and num_stories + estimated_stories
        must be populated with a reasonable value.
        """
        buildings = [self._make_building(area_m2=8822.0, height=46.19)]
        results = self._convert(buildings)
        sc = results[0]

        # Material should be reinforced
        assert sc.material == BuildingMaterial.CONCRETE_REINFORCED
        assert sc.vulnerability_class == VulnerabilityClass.CLASS_IV_REINFORCED

        # Height data should be present
        assert sc.height is not None
        assert sc.height.height_m == pytest.approx(46.19)

        # num_stories must not be None
        assert sc.num_stories is not None
        assert sc.num_stories > 0

        # estimated_stories must equal num_stories
        assert sc.height.estimated_stories == sc.num_stories
