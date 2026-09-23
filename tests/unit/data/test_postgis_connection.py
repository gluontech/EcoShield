# tests/unit/data/test_postgis_connection.py
"""
Unit tests for PostGIS error handling and fallback behavior in OpenBuildingMapSource.
"""

from unittest.mock import AsyncMock, patch
import asyncpg
import pytest

from src.core.models.geometry import BoundingBox
from src.data.open_building_map import OpenBuildingMapSource


@pytest.mark.asyncio
async def test_query_postgis_authentication_error_fallback() -> None:
    """Test that PostGIS authentication failure logs an error and falls back gracefully."""
    bbox = BoundingBox(min_lat=10.77, max_lat=10.78, min_lon=106.69, max_lon=106.71)
    bad_db_url = "postgresql+asyncpg://ecoshield:wrongpassword@localhost:5432/ecoshield"

    source = OpenBuildingMapSource(db_url=bad_db_url, use_postgis=True)

    with patch("asyncpg.connect", side_effect=asyncpg.InvalidPasswordError("password authentication failed for user 'ecoshield'")):
        results = await source.get_buildings_in_bbox(bbox)
        # Should fallback to GeoPackage/local cache without crashing
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_query_postgis_raises_auth_error_internal() -> None:
    """Test that internal _query_postgis raises RuntimeError on InvalidPasswordError."""
    bbox = BoundingBox(min_lat=10.77, max_lat=10.78, min_lon=106.69, max_lon=106.71)
    bad_db_url = "postgresql+asyncpg://ecoshield:wrongpassword@localhost:5432/ecoshield"

    source = OpenBuildingMapSource(db_url=bad_db_url, use_postgis=True)

    with patch("asyncpg.connect", side_effect=asyncpg.InvalidPasswordError("password authentication failed for user 'ecoshield'")):
        with pytest.raises(RuntimeError, match="PostGIS authentication failed"):
            await source._query_postgis(bbox, limit=10)
