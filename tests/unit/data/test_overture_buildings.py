# tests/unit/data/test_overture_buildings.py
"""
Unit tests for OvertureBuildingsSource thread isolation and per-query DuckDB connection handling.
"""

import asyncio
from unittest.mock import patch, MagicMock
import pytest

from src.core.models.geometry import BoundingBox
from src.data.overture_buildings import OvertureBuildingsSource


@pytest.fixture
def mock_bbox() -> BoundingBox:
    return BoundingBox(
        min_lat=10.77,
        max_lat=10.78,
        min_lon=106.69,
        max_lon=106.70,
    )


def test_overture_buildings_source_init():
    """Verify OvertureBuildingsSource instantiates without creating shared connection."""
    source = OvertureBuildingsSource()
    assert not hasattr(source, "conn")


def test_per_query_connection_context_manager():
    """Verify _get_connection creates and closes a dedicated DuckDB connection."""
    source = OvertureBuildingsSource()
    with source._get_connection() as conn:
        res = conn.execute("SELECT 1").fetchone()
        assert res == (1,)


@pytest.mark.asyncio
async def test_concurrent_queries_do_not_deadlock(mock_bbox):
    """Verify concurrent query executions instantiate separate connections without deadlocks."""
    source = OvertureBuildingsSource()

    with patch("overturemaps.record_batch_reader") as mock_reader:
        mock_table = MagicMock()
        mock_table.num_rows = 0
        mock_reader.return_value.read_all.return_value = mock_table

        async def _run_query(query_type: str):
            if query_type == "buildings":
                return await asyncio.to_thread(source.query_buildings, mock_bbox)
            elif query_type == "parts":
                return await asyncio.to_thread(source.query_building_parts, mock_bbox)
            elif query_type == "places":
                return await asyncio.to_thread(source.query_places, mock_bbox)

        # Run all three query types concurrently across threads
        results = await asyncio.gather(
            _run_query("buildings"),
            _run_query("parts"),
            _run_query("places"),
        )

        assert results == [[], [], []]
