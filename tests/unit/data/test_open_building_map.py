# tests/unit/data/test_open_building_map.py
"""
Unit tests for OpenBuildingMap data layer (src/data/open_building_map.py).
"""

import pytest
from src.core.models.enums import BuildingOccupancy, BuildingMaterial, VulnerabilityClass
from src.core.models.geometry import BoundingBox
from src.data.open_building_map import (
    parse_gem_occupancy, parse_gem_height, parse_gem_material, OpenBuildingMapSource,
)


def test_parse_gem_occupancy():
    assert parse_gem_occupancy("COM1") == BuildingOccupancy.COMMERCIAL
    assert parse_gem_occupancy("RES1") == BuildingOccupancy.RESIDENTIAL_SINGLE
    assert parse_gem_occupancy("RES2") == BuildingOccupancy.RESIDENTIAL_MULTI
    assert parse_gem_occupancy("IND") == BuildingOccupancy.INDUSTRIAL
    assert parse_gem_occupancy("GOV") == BuildingOccupancy.INSTITUTIONAL
    assert parse_gem_occupancy("SHACK") == BuildingOccupancy.RESIDENTIAL_INFORMAL
    assert parse_gem_occupancy(None) == BuildingOccupancy.UNKNOWN


def test_parse_gem_height():
    h, floors = parse_gem_height("H:15m")
    assert h == 15.0
    assert floors == 5

    h, floors = parse_gem_height("HBET:1-3")
    assert h == 6.0
    assert floors == 2

    h, floors = parse_gem_height("4")
    assert h == 12.0
    assert floors == 4


def test_parse_gem_material():
    mat, vul = parse_gem_material("MAT:CR", BuildingOccupancy.COMMERCIAL)
    assert mat == BuildingMaterial.CONCRETE_REINFORCED
    assert vul == VulnerabilityClass.CLASS_IV_REINFORCED

    mat, vul = parse_gem_material("MAT:W", BuildingOccupancy.RESIDENTIAL_SINGLE)
    assert mat == BuildingMaterial.WOOD_FRAME
    assert vul == VulnerabilityClass.CLASS_II_WOOD


@pytest.mark.asyncio
async def test_get_buildings_in_bbox_local():
    # HCMC District 1 BoundingBox
    bbox = BoundingBox(min_lat=10.77, max_lat=10.78, min_lon=106.69, max_lon=106.71)
    source = OpenBuildingMapSource(use_postgis=False)
    structures = await source.get_buildings_in_bbox(bbox)
    assert isinstance(structures, list)
    assert len(structures) > 0
    first = structures[0]
    assert first.footprint is not None
    assert first.footprint.building_id.startswith("OBM_")
    assert first.height is not None
    assert first.height.num_floors >= 1
