# tests/data_tests/test_elevation.py
"""
Unit tests for elevation module, focusing on:
- _centroid_from_wkt helper (WKT → centroid without shapely)
- _read_elevation_footprint_sync ImportError fallback (should use centroid
  sampling rather than returning 0.0)
"""

import builtins
import importlib
from unittest.mock import patch, MagicMock

import pytest

from src.data.elevation import _centroid_from_wkt


# ---------------------------------------------------------------------------
# _centroid_from_wkt
# ---------------------------------------------------------------------------
class TestCentroidFromWkt:
    """Test lightweight WKT centroid extraction."""

    def test_simple_polygon(self):
        wkt = "POLYGON ((106.69 10.76, 106.70 10.76, 106.70 10.77, 106.69 10.77, 106.69 10.76))"
        result = _centroid_from_wkt(wkt)
        assert result is not None
        lat, lon = result
        assert pytest.approx(lat, abs=0.01) == 10.764
        assert pytest.approx(lon, abs=0.01) == 106.694

    def test_negative_coordinates(self):
        wkt = "POLYGON ((-73.99 -33.45, -73.98 -33.45, -73.98 -33.44, -73.99 -33.44, -73.99 -33.45))"
        result = _centroid_from_wkt(wkt)
        assert result is not None
        lat, lon = result
        assert lat < 0
        assert lon < 0

    def test_empty_string_returns_none(self):
        assert _centroid_from_wkt("") is None

    def test_invalid_wkt_returns_none(self):
        assert _centroid_from_wkt("NOT A POLYGON") is None

    def test_single_point(self):
        wkt = "POLYGON ((106.70 10.77))"
        result = _centroid_from_wkt(wkt)
        assert result is not None
        lat, lon = result
        assert pytest.approx(lat, abs=0.001) == 10.77
        assert pytest.approx(lon, abs=0.001) == 106.70


# ---------------------------------------------------------------------------
# _read_elevation_footprint_sync — ImportError fallback
# ---------------------------------------------------------------------------
class TestFootprintElevationImportFallback:
    """When shapely/rasterio.mask is unavailable the function must fall back to
    centroid-based elevation sampling, NOT return 0.0."""

    @patch("src.data.elevation._read_elevation_sync")
    def test_import_error_falls_back_to_centroid(self, mock_read_sync):
        """Simulate missing shapely and verify centroid sampling is used."""
        mock_read_sync.return_value = 12.5

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name in ("shapely.wkt", "rasterio.mask"):
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        wkt = "POLYGON ((106.69 10.76, 106.70 10.76, 106.70 10.77, 106.69 10.77, 106.69 10.76))"

        # Reload the function scope to trigger the ImportError
        from src.data import elevation as elev_mod

        with patch("builtins.__import__", side_effect=fake_import):
            result = elev_mod._read_elevation_footprint_sync(wkt)

        # Must NOT be 0.0 — should call _read_elevation_sync with centroid
        assert result == 12.5
        mock_read_sync.assert_called_once()
        called_lat, called_lon = mock_read_sync.call_args[0]
        assert pytest.approx(called_lat, abs=0.01) == 10.764
        assert pytest.approx(called_lon, abs=0.01) == 106.694

    @patch("src.data.elevation._read_elevation_sync")
    def test_import_error_with_unparseable_wkt_returns_zero(self, mock_read_sync):
        """If shapely is missing AND the WKT can't be parsed, 0.0 is acceptable."""
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name in ("shapely.wkt", "rasterio.mask"):
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        from src.data import elevation as elev_mod

        with patch("builtins.__import__", side_effect=fake_import):
            result = elev_mod._read_elevation_footprint_sync("NOT A POLYGON")

        assert result == 0.0
        mock_read_sync.assert_not_called()
