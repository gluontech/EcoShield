# tests/unit/data/test_obm_schema.py
"""
Unit tests for OpenBuildingMap schema auto-creation and missing table error handling.
"""

from unittest.mock import AsyncMock, patch
import asyncpg
import pytest

from src.core.models.geometry import BoundingBox
from src.data.open_building_map import OpenBuildingMapSource


@pytest.mark.asyncio
async def test_undefined_table_auto_creation_trigger() -> None:
    """Test that UndefinedTableError triggers ensure_schema auto-creation."""
    bbox = BoundingBox(min_lat=10.77, max_lat=10.78, min_lon=106.69, max_lon=106.71)
    source = OpenBuildingMapSource(db_url="postgresql+asyncpg://ecoshield:pass@localhost:5432/ecoshield")

    mock_conn = AsyncMock()
    # First fetch raises UndefinedTableError, second fetch returns empty list
    mock_conn.fetch.side_effect = [
        asyncpg.UndefinedTableError('relation "obm_buildings" does not exist'),
        []
    ]

    with patch("asyncpg.connect", return_value=mock_conn):
        with patch.object(source, "ensure_schema", new_callable=AsyncMock) as mock_ensure:
            results = await source._query_postgis(bbox, limit=10)
            assert results == []
            mock_ensure.assert_awaited_once_with(mock_conn)
            assert mock_conn.fetch.call_count == 2
