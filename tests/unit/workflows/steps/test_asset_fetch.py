# tests/unit/workflows/steps/test_asset_fetch.py
"""
Unit test for fetch_buildings_step using OpenBuildingMapSource and Overture timeout handling.
"""

import time
from unittest.mock import patch
import pytest

from src.workflows.steps.asset_fetch import fetch_buildings_step


@pytest.mark.asyncio
async def test_fetch_buildings_step_hcmc():
    data = {
        "lat": 10.7769,
        "lon": 106.7009,
        "building_radius_m": 500,
        "include_buildings": True,
    }
    result = await fetch_buildings_step(data)

    assert "building_cluster" in result
    assert "building_surfaces" in result
    cluster = result["building_cluster"]
    surfaces = result["building_surfaces"]
    assert cluster is not None
    assert len(cluster.buildings) > 0
    assert len(surfaces) > 0

    # Verify building surface attributes
    first_key = list(surfaces.keys())[0]
    b_surf = surfaces[first_key]
    assert b_surf.building_id is not None
    assert b_surf.original_elevation_m >= 0.0

    # Verify structure attributes in cluster
    first_struct = cluster.buildings[0]
    assert first_struct.occupancy is not None
    assert first_struct.footprint.building_id.startswith("OBM_")


@pytest.mark.asyncio
async def test_fetch_buildings_step_overture_timeout_fallback():
    """Verify that if fetch_overture times out, fetch_buildings_step falls back gracefully and does not hang."""
    data = {
        "lat": 10.7769,
        "lon": 106.7009,
        "name": "Bitexco Tower",
        "building_radius_m": 500,
        "include_buildings": True,
    }

    def _mock_slow_fetch(*args, **kwargs):
        time.sleep(10.0)
        return []

    with patch("src.data.overture_buildings.OvertureBuildingsSource.query_buildings", side_effect=_mock_slow_fetch):
        result = await fetch_buildings_step(data)
        assert "building_cluster" in result
        assert result["building_cluster"] is not None
