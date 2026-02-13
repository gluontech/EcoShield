# tests/unit/test_data_phase2.py
import pytest
import numpy as np
import pytest_asyncio
from unittest.mock import MagicMock, patch

from src.data.validation import validate_array, validate_no_nan, DataQualityError
from src.data.rating_curve import discharge_to_depth, depth_to_flood_level, RatingCurveParams
from src.data.pluvial_flood import compute_pluvial_susceptibility
from src.data.holland_wind import holland_wind_profile, holland_b_parameter
from src.data.ipcc_slr import get_slr_projection
from src.data.nex_gddp import get_extreme_precipitation
from src.core.models import DataSource, ConfidenceLevel


# --- 1. Validation Logic ---
def test_validate_array():
    # Test valid array
    arr = np.array([1.0, 2.0, 3.0])
    valid = validate_array(arr, valid_range=(0, 5))
    assert np.array_equal(arr, valid)

    # Test NaN fraction error
    arr_nan = np.array([1.0, np.nan, np.nan])
    with pytest.raises(DataQualityError):
        validate_array(arr_nan, max_nan_fraction=0.5)  # 2/3 is > 0.5

    # Test range clamping
    arr_oor = np.array([-1.0, 6.0])
    # Should log warning but clamp
    clamped = validate_array(arr_oor, valid_range=(0, 5))
    assert clamped[0] == 0.0
    assert clamped[1] == 5.0
    
    # Test Fill Value
    arr_fill = np.array([1.0, -9999.0])
    cleaned = validate_array(arr_fill, fill_values=[-9999.0])
    assert np.isnan(cleaned[1])


@pytest.mark.asyncio
async def test_validate_decorator():
    from pydantic import BaseModel
    
    class TestModel(BaseModel):
        val: float
        
    @validate_no_nan
    async def get_bad_data():
        return TestModel(val=float('nan'))
        
    # Should log warning but not crash (decorator catches it and warns)
    res = await get_bad_data()
    assert np.isnan(res.val)


# --- 2. Rating Curve (Gap J) ---
def test_rating_curve():
    # Manning Check
    # Q=100, W=100, S=0.0005, n=0.035
    # Depth should be positive
    depth = discharge_to_depth(100.0, 100.0, 0.035, 0.0005)
    assert depth > 0
    assert 1.0 < depth < 2.0 # Rough check
    
    # Flood Level
    # Bankfull 3m, depth 4m -> 1m overbank? No, function returns MSL
    # Bed 0m, depth 4m -> 4m MSL
    lvl = depth_to_flood_level(4.0, bankfull_depth_m=3.0, channel_bed_elevation_m=10.0)
    assert lvl == 14.0
    
    # No flood
    lvl_none = depth_to_flood_level(2.0, bankfull_depth_m=3.0)
    assert lvl_none is None


# --- 3. Pluvial Flood (Gap M) ---
def test_pluvial_susceptibility():
    # High risk: Low HAND, Flat Slope, High Impervious
    res_high = compute_pluvial_susceptibility(
        hand_m=0.5, slope_degrees=1.0, impervious_fraction=0.9, design_rainfall_mm=100
    )
    assert res_high.susceptibility_index > 0.6
    assert res_high.estimated_depth_m > 0
    
    # Low risk: High HAND, Steep Slope
    res_low = compute_pluvial_susceptibility(
        hand_m=20.0, slope_degrees=15.0, impervious_fraction=0.1
    )
    assert res_low.susceptibility_index < 0.2


# --- 4. Holland Wind (Gap P) ---
def test_holland_wind():
    # Test B parameter limits
    b = holland_b_parameter(vmax_ms=80.0, central_pressure_hpa=900.0)
    assert 1.0 <= b <= 2.5
    
    # Test profile decay
    rmw = 50.0
    res_rmw = holland_wind_profile(50.0, 60.0, rmw, 950.0)
    res_far = holland_wind_profile(200.0, 60.0, rmw, 950.0)
    
    assert res_rmw.wind_speed_ms > res_far.wind_speed_ms
    assert res_rmw.is_within_rmw
    assert not res_far.is_within_rmw


# --- 5. IPCC SLR (Gap K) ---
def test_ipcc_slr():
    # Existing city
    slr = get_slr_projection("ho_chi_minh_city", "ssp585", 2050)
    assert slr.slr_median_m == 0.24
    
    # Interpolation
    slr_interp = get_slr_projection("ho_chi_minh_city", "ssp585", 2075) # Midpoint 2050-2100
    # 2050=0.24, 2100=0.83. Mid ~ 0.535
    assert 0.50 < slr_interp.slr_median_m < 0.60
    
    # Missing city
    with pytest.raises(ValueError):
        get_slr_projection("atlantis")


# --- 6. NEX-GDDP Ensemble (Gap I) ---
@pytest.mark.asyncio
async def test_nex_gddp_ensemble():
    # Mock the _load_ensemble_data function to return fake data
    with patch("src.data.nex_gddp._load_ensemble_data") as mock_load:
        # Return 5 arrays of 30 years * 365 days
        # Just random data
        fake_series = [np.random.rand(365 * 30) * 100 for _ in range(5)]
        mock_load.return_value = fake_series
        
        res = await get_extreme_precipitation(10.0, 106.0)
        
        assert res.return_period_years == 100
        assert res.precip_mm_per_day > 0
        assert res.confidence == ConfidenceLevel.HIGH # 5 models valid
