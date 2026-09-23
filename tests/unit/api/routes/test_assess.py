# tests/unit/api/routes/test_assess.py
"""Unit tests for assess route helpers and asset extraction."""

from __future__ import annotations

import pytest

from src.api.routes.assess import _extract_asset, _select_primary_rp
from src.core.models.response_models import Asset


def test_extract_asset_with_null_height() -> None:
    """Test asset extraction when height is None (e.g. no OBM footprint found)."""
    hazards_data = {
        "subsidence": {
            "exposure": {
                "elevation_m": 2.5,
                "elevation_source": "copernicus_glo30",
                "structure": {
                    "footprint": {
                        "building_id": "point_10.7957_106.6797",
                        "source": "copernicus_glo30",
                        "centroid": {"lat": 10.795655, "lon": 106.67966},
                        "footprint_wkt": "POLYGON((106.67 10.79, 106.68 10.79, 106.68 10.80, 106.67 10.80, 106.67 10.79))",
                        "area_m2": 1.0,
                    },
                    "height": None,  # Null height from point exposure
                    "material": "unknown",
                    "occupancy": "unknown",
                    "vulnerability_class": "class_iii",
                },
            }
        }
    }

    asset_dict = _extract_asset(hazards_data)
    assert asset_dict["height"]["height_m"] == 3.0
    assert asset_dict["footprint"]["building_id"] == "point_10.7957_106.6797"
    # Validate against strict Pydantic v2 Asset response model
    asset_model = Asset.model_validate(asset_dict)
    assert asset_model.height.height_m == 3.0


def test_extract_asset_with_null_footprint() -> None:
    """Test asset extraction when footprint is None."""
    hazards_data = {
        "subsidence": {
            "exposure": {
                "elevation_m": 1.0,
                "structure": {
                    "footprint": None,
                    "height": None,
                },
            }
        }
    }

    asset_dict = _extract_asset(hazards_data)
    assert asset_dict["footprint"]["building_id"] == "unknown"
    assert asset_dict["footprint"]["footprint_wkt"] == "POLYGON EMPTY"
    assert asset_dict["height"]["height_m"] == 3.0
    Asset.model_validate(asset_dict)


def test_extract_asset_empty_hazards_data() -> None:
    """Test fallback asset creation when hazards_data is empty."""
    asset_dict = _extract_asset({})
    assert asset_dict["footprint"]["building_id"] == "unknown"
    assert asset_dict["height"]["height_m"] == 3.0
    Asset.model_validate(asset_dict)


def test_select_primary_rp() -> None:
    """Test primary return period selection."""
    assert _select_primary_rp([10, 50, 100, 250]) == 100
    assert _select_primary_rp([10, 25, 50]) == 50
    assert _select_primary_rp([250]) == 250
