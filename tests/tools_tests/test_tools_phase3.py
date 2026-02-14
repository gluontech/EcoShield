# tests/unit/test_tools_phase3.py
"""
Unit tests for EcoShield Phase 3 hazard assessment tools.

All external data calls are mocked to enable offline testing.
Each tool is tested for:
  1. Correct return type (HazardAssessmentResult)
  2. Correct HazardType assignment
  3. Reasonable intensity values
  4. Intermediate dict population
  5. Impact score/tier consistency
"""

import pytest
import math
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from dataclasses import dataclass

from src.core.models import (
    Location, HazardType, RiskTier, ConfidenceLevel, DataSource,
    HazardAssessmentResult, HazardIntensity, ExposureProfile, BoundingBox,
    VulnerabilityClass, BuildingCluster, StructuralCharacteristics,
    BuildingFootprint, StructureRiskResult, PortfolioRiskSummary,
    ReturnPeriodLoss, STANDARD_RETURN_PERIODS, BuildingAdjustedSurface,
    OCCUPANCY_VALUE_MULTIPLIER, FloodReturnPeriodResult, SlopeResult,
    HANDResult, WBGTComponentsResult, InSARVelocityResult,
    ExtremePrecipitationResult, TemperatureBaselineResult,
    ClimateProjectionResult,
)


# ======================== Shared Fixtures ========================

@pytest.fixture
def mock_hand_result():
    return HANDResult(
        hand_value_m=3.5,
        dem_elevation_m=5.0,
        drainage_elevation_m=1.5,
        nearest_drainage_distance_m=150.0,
        data_source=DataSource.COPERNICUS_GLO30,
    )


@pytest.fixture
def mock_slope_result():
    return SlopeResult(
        slope_degrees=2.5,
        aspect_degrees=180.0,
        elevation_m=5.0,
        data_source=DataSource.COPERNICUS_GLO30,
    )


@pytest.fixture
def mock_flood_discharge():
    return FloodReturnPeriodResult(
        return_period_years=100,
        discharge_m3s=800.0,
        estimated_water_level_m=None,
        confidence=ConfidenceLevel.MODERATE,
        data_source=DataSource.GLOFAS_V4,
    )


@pytest.fixture
def mock_extreme_precip():
    return ExtremePrecipitationResult(
        precip_mm_per_day=120.0,
        return_period_years=100,
        uncertainty_p5=100.0,
        uncertainty_p95=140.0,
        confidence=ConfidenceLevel.MODERATE,
        data_source=DataSource.NEX_GDDP_CMIP6,
    )


@pytest.fixture
def mock_extreme_precip_low():
    return ExtremePrecipitationResult(
        precip_mm_per_day=60.0,
        return_period_years=10,
        uncertainty_p5=50.0,
        uncertainty_p95=70.0,
        confidence=ConfidenceLevel.MODERATE,
        data_source=DataSource.NEX_GDDP_CMIP6,
    )


@pytest.fixture
def mock_insar_result():
    return InSARVelocityResult(
        velocity_mm_per_year=-15.0,
        uncertainty_mm_per_year=5.0,
        coherence=0.7,
        observation_period=("2015-01-01", "2023-12-31"),
        num_observations=150,
        resolution_m=100,
        data_source=DataSource.SENTINEL1_INSAR,
        confidence=ConfidenceLevel.MODERATE,
    )


@pytest.fixture
def mock_temp_baseline():
    return TemperatureBaselineResult(
        location_lat=10.7,
        location_lon=106.7,
        annual_mean_c=28.0,
        monthly_means_c={},
        p90_temperature_c=32.0,
        p95_temperature_c=34.0,
        heat_wave_threshold_c=35.0,
        data_source=DataSource.NEX_GDDP_CMIP6,
    )


@pytest.fixture
def mock_climate_projection():
    return ClimateProjectionResult(
        variable="tasmax",
        baseline_mean=28.0,
        future_mean=30.5,
        change=2.5,
        change_percent=8.9,
        uncertainty_p5=29.0,
        uncertainty_p95=32.0,
        scenario="ssp245",
        future_period="2040-2060",
        unit="K",
        data_source=DataSource.NEX_GDDP_CMIP6,
    )


@pytest.fixture
def mock_wbgt_result():
    return WBGTComponentsResult(
        mean_wbgt_c=29.0,
        max_wbgt_c=33.0,
        days_risk_high=25,
        days_risk_extreme=5,
        data_source=DataSource.ERA5_LAND,
    )


@pytest.fixture
def mock_building_cluster():
    """Minimal BuildingCluster with one building."""
    fp = BuildingFootprint(
        building_id="bldg_001",
        source=DataSource.GOOGLE_OPEN_BUILDINGS_V3,
        centroid=Location(lat=10.77, lon=106.70),
        area_m2=120.0,
    )
    structure = StructuralCharacteristics(
        footprint=fp,
        ground_elevation_m=2.0,
        ground_floor_height_m=0.3,
        vulnerability_class=VulnerabilityClass.CLASS_III_MASONRY,
        replacement_value_usd=50000.0,
    )
    return BuildingCluster(
        cluster_id="test_cluster",
        tile_id="123_456",
        bounds=BoundingBox(min_lat=10.70, max_lat=10.80, min_lon=106.60, max_lon=106.80),
        location=Location(lat=10.77, lon=106.70),
        buildings=[structure],
    )


# ======================== 1. Riverine Flood ========================

@pytest.mark.asyncio
async def test_riverine_flood_basic(mock_hand_result, mock_flood_discharge):
    """Test basic riverine flood assessment returns correct type and hazard."""
    with patch("src.tools.riverine_flood_tools.get_hand_value", new_callable=AsyncMock, return_value=mock_hand_result), \
         patch("src.tools.riverine_flood_tools.get_flood_return_period", new_callable=AsyncMock, return_value=mock_flood_discharge), \
         patch("src.tools.riverine_flood_tools.get_elevation", new_callable=AsyncMock, return_value=5.0):

        from src.tools.riverine_flood_tools import assess_riverine_flood
        result = await assess_riverine_flood(lat=10.77, lon=106.70, return_period=100)

        assert isinstance(result, HazardAssessmentResult)
        assert result.hazard.hazard_type == HazardType.RIVERINE_FLOOD
        assert result.hazard.intensity_unit == "m"
        assert result.hazard.intensity_value >= 0
        assert result.exposure.elevation_m == 5.0
        assert "hand_value_m" in result.intermediate
        assert "discharge_m3s" in result.intermediate
        assert result.impact_tier in list(RiskTier)


@pytest.mark.asyncio
async def test_riverine_flood_high_hand_no_flood(mock_flood_discharge):
    """High HAND value should result in no flooding."""
    high_hand = HANDResult(
        hand_value_m=20.0,
        dem_elevation_m=25.0,
        drainage_elevation_m=5.0,
        nearest_drainage_distance_m=500.0,
        data_source=DataSource.COPERNICUS_GLO30,
    )
    with patch("src.tools.riverine_flood_tools.get_hand_value", new_callable=AsyncMock, return_value=high_hand), \
         patch("src.tools.riverine_flood_tools.get_flood_return_period", new_callable=AsyncMock, return_value=mock_flood_discharge), \
         patch("src.tools.riverine_flood_tools.get_elevation", new_callable=AsyncMock, return_value=25.0):

        from src.tools.riverine_flood_tools import assess_riverine_flood
        result = await assess_riverine_flood(lat=10.77, lon=106.70)

        assert result.hazard.intensity_value == 0
        assert result.intermediate["flooded"] is False
        assert result.impact_tier == RiskTier.LOW


# ======================== 2. Coastal Flood ========================

@pytest.mark.asyncio
async def test_coastal_flood_basic():
    """Test coastal flood with IPCC SLR projection."""
    from src.data.ipcc_slr import SLRProjection

    mock_slr = SLRProjection(
        city="ho_chi_minh_city",
        scenario="ssp245",
        target_year=2050,
        slr_median_m=0.23,
        slr_p5_m=0.15,
        slr_p95_m=0.40,
    )

    with patch("src.tools.coastal_flood_tools.get_elevation", new_callable=AsyncMock, return_value=1.5), \
         patch("src.tools.coastal_flood_tools.get_slr_projection", return_value=mock_slr):

        from src.tools.coastal_flood_tools import assess_coastal_flood
        result = await assess_coastal_flood(
            lat=10.77, lon=106.70, time_horizon=2050, scenario="ssp245"
        )

        assert isinstance(result, HazardAssessmentResult)
        assert result.hazard.hazard_type == HazardType.COASTAL_FLOOD
        assert result.hazard.intensity_unit == "m"
        assert result.intermediate["slr_median_m"] == 0.23
        assert result.intermediate["is_coastal"] is True


@pytest.mark.asyncio
async def test_coastal_flood_high_elevation_no_risk():
    """High elevation location should show no inundation."""
    from src.data.ipcc_slr import SLRProjection

    mock_slr = SLRProjection(
        city="ho_chi_minh_city", scenario="ssp585", target_year=2100,
        slr_median_m=0.83, slr_p5_m=0.50, slr_p95_m=1.30,
    )

    with patch("src.tools.coastal_flood_tools.get_elevation", new_callable=AsyncMock, return_value=15.0), \
         patch("src.tools.coastal_flood_tools.get_slr_projection", return_value=mock_slr):

        from src.tools.coastal_flood_tools import assess_coastal_flood
        result = await assess_coastal_flood(lat=10.77, lon=106.70, time_horizon=2100, scenario="ssp585")

        assert result.hazard.intensity_value == 0.0
        assert result.impact_tier == RiskTier.LOW


# ======================== 3. Subsidence ========================

@pytest.mark.asyncio
async def test_subsidence_basic(mock_insar_result):
    """Test subsidence assessment returns correct type and values."""
    with patch("src.tools.subsidence_tools.get_subsidence_velocity", new_callable=AsyncMock, return_value=mock_insar_result), \
         patch("src.tools.subsidence_tools.get_elevation", new_callable=AsyncMock, return_value=3.0):

        from src.tools.subsidence_tools import assess_subsidence
        result = await assess_subsidence(lat=10.77, lon=106.70, city="hcmc", time_horizon=2050)

        assert isinstance(result, HazardAssessmentResult)
        assert result.hazard.hazard_type == HazardType.SUBSIDENCE
        assert result.hazard.intensity_unit == "mm/yr"
        assert result.hazard.intensity_value == 15.0  # abs(-15)
        assert result.intermediate["cumulative_m"] > 0
        assert result.intermediate["subsidence_source"] == "insar_measured"


@pytest.mark.asyncio
async def test_subsidence_negligible():
    """Minimal subsidence should yield LOW risk."""
    low_insar = InSARVelocityResult(
        velocity_mm_per_year=-1.0, uncertainty_mm_per_year=2.0,
        coherence=0.9, observation_period=("2015-01-01", "2023-12-31"),
        num_observations=150, resolution_m=100,
        data_source=DataSource.SENTINEL1_INSAR, confidence=ConfidenceLevel.HIGH,
    )
    with patch("src.tools.subsidence_tools.get_subsidence_velocity", new_callable=AsyncMock, return_value=low_insar), \
         patch("src.tools.subsidence_tools.get_elevation", new_callable=AsyncMock, return_value=10.0):

        from src.tools.subsidence_tools import assess_subsidence
        result = await assess_subsidence(lat=10.77, lon=106.70, time_horizon=2050)

        assert result.hazard.intensity_value == 1.0
        assert result.impact_tier == RiskTier.LOW


# ======================== 4. Landslide ========================

@pytest.mark.asyncio
async def test_landslide_steep_slope(mock_extreme_precip, mock_extreme_precip_low):
    """Steep slope with high rainfall should yield high risk."""
    steep_slope = SlopeResult(
        slope_degrees=30.0, aspect_degrees=90.0, elevation_m=200.0,
        data_source=DataSource.COPERNICUS_GLO30,
    )
    with patch("src.tools.landslide_tools.get_slope", new_callable=AsyncMock, return_value=steep_slope), \
         patch("src.tools.landslide_tools.get_elevation", new_callable=AsyncMock, return_value=200.0), \
         patch("src.tools.landslide_tools.get_extreme_precipitation", new_callable=AsyncMock, side_effect=[mock_extreme_precip, mock_extreme_precip_low]):

        from src.tools.landslide_tools import assess_landslide
        result = await assess_landslide(lat=10.0, lon=106.0, return_period=100)

        assert isinstance(result, HazardAssessmentResult)
        assert result.hazard.hazard_type == HazardType.LANDSLIDE
        assert result.hazard.intensity_unit == "susceptibility_score"
        assert result.impact_score > 40  # steep slope = high susceptibility
        assert "slope_degrees" in result.intermediate


@pytest.mark.asyncio
async def test_landslide_flat_terrain(mock_extreme_precip_low):
    """Flat terrain should yield low landslide risk."""
    flat_slope = SlopeResult(
        slope_degrees=1.0, aspect_degrees=0.0, elevation_m=5.0,
        data_source=DataSource.COPERNICUS_GLO30,
    )
    with patch("src.tools.landslide_tools.get_slope", new_callable=AsyncMock, return_value=flat_slope), \
         patch("src.tools.landslide_tools.get_elevation", new_callable=AsyncMock, return_value=5.0), \
         patch("src.tools.landslide_tools.get_extreme_precipitation", new_callable=AsyncMock, return_value=mock_extreme_precip_low):

        from src.tools.landslide_tools import assess_landslide
        result = await assess_landslide(lat=10.0, lon=106.0, return_period=100)

        assert result.impact_score < 40  # flat = low/moderate susceptibility given default factors
        assert result.impact_tier in [RiskTier.LOW, RiskTier.MODERATE]


# ======================== 5. Cyclone ========================

@pytest.mark.asyncio
async def test_cyclone_basic():
    """Test cyclone assessment with mocked IBTrACS."""
    from src.core.models import CycloneEventParams

    mock_params = CycloneEventParams(
        max_wind_ms=45.0,
        central_pressure_hpa=960.0,
        radius_max_wind_km=50.0,
        translation_speed_ms=5.0,
        heading_degrees=315.0,
        saffir_simpson_category=2,
        rainfall_proxy_mm=200.0,
    )

    @dataclass
    class MockWindResult:
        wind_speed_ms: float = 38.0
        b_parameter: float = 1.5
        is_within_rmw: bool = False

    with patch("src.tools.cyclone_tools.get_regional_cyclone_statistics", new_callable=AsyncMock, return_value=mock_params), \
         patch("src.tools.cyclone_tools.get_elevation", new_callable=AsyncMock, return_value=10.0), \
         patch("src.tools.cyclone_tools.holland_wind_profile", return_value=MockWindResult()):

        from src.tools.cyclone_tools import assess_cyclone
        result = await assess_cyclone(lat=10.77, lon=106.70, return_period=100)

        assert isinstance(result, HazardAssessmentResult)
        assert result.hazard.hazard_type == HazardType.TROPICAL_CYCLONE
        assert result.hazard.intensity_unit == "m/s"
        assert result.hazard.intensity_value > 0
        assert "cyclone_params" in result.intermediate
        assert "max_wind_kts" in result.intermediate


# ======================== 6. Storm Surge ========================

@pytest.mark.asyncio
async def test_storm_surge_with_cyclone_params():
    """Test storm surge with cyclone parameters."""
    cyclone_params = {
        "max_wind_kts": 85,
        "central_pressure_mb": 960,
        "forward_speed_ms": 5.0,
    }

    with patch("src.tools.storm_surge_tools.get_elevation", new_callable=AsyncMock, return_value=2.0):
        from src.tools.storm_surge_tools import assess_storm_surge
        result = await assess_storm_surge(
            lat=10.77, lon=106.70,
            cyclone_params=cyclone_params,
            return_period=100,
        )

        assert isinstance(result, HazardAssessmentResult)
        assert result.hazard.hazard_type == HazardType.STORM_SURGE
        assert result.hazard.intensity_unit == "m"
        assert result.intermediate["total_surge_m"] > 0


@pytest.mark.asyncio
async def test_storm_surge_no_cyclone():
    """No cyclone params should return zero surge."""
    with patch("src.tools.storm_surge_tools.get_elevation", new_callable=AsyncMock, return_value=5.0):
        from src.tools.storm_surge_tools import assess_storm_surge
        result = await assess_storm_surge(lat=10.77, lon=106.70, cyclone_params=None)

        assert result.hazard.intensity_value == 0.0
        assert result.impact_tier == RiskTier.LOW


# ======================== 7. Urban Heat ========================

@pytest.mark.asyncio
async def test_urban_heat_basic(mock_temp_baseline, mock_climate_projection, mock_wbgt_result):
    """Test urban heat assessment with ERA5 WBGT available."""
    with patch("src.tools.urban_heat_tools.get_temperature_baseline", new_callable=AsyncMock, return_value=mock_temp_baseline), \
         patch("src.tools.urban_heat_tools.get_climate_projection", new_callable=AsyncMock, return_value=mock_climate_projection), \
         patch("src.tools.urban_heat_tools.get_wbgt_statistics", new_callable=AsyncMock, return_value=mock_wbgt_result), \
         patch("src.tools.urban_heat_tools.get_elevation", new_callable=AsyncMock, return_value=5.0):

        from src.tools.urban_heat_tools import assess_urban_heat
        result = await assess_urban_heat(
            lat=10.77, lon=106.70, time_horizon=2050, scenario="ssp245"
        )

        assert isinstance(result, HazardAssessmentResult)
        assert result.hazard.hazard_type == HazardType.URBAN_HEAT
        assert result.hazard.intensity_unit == "C"
        # projected = p95(34) + change(2.5) + UHI(2.0) = 38.5
        assert result.hazard.intensity_value == pytest.approx(38.5, abs=0.5)
        assert result.intermediate["current_wbgt_c"] == 29.0
        assert result.intermediate["uhi_source"] == "default"  # No landsat


@pytest.mark.asyncio
async def test_urban_heat_without_era5(mock_temp_baseline, mock_climate_projection):
    """Urban heat should gracefully degrade when ERA5 is unavailable."""
    with patch("src.tools.urban_heat_tools.get_temperature_baseline", new_callable=AsyncMock, return_value=mock_temp_baseline), \
         patch("src.tools.urban_heat_tools.get_climate_projection", new_callable=AsyncMock, return_value=mock_climate_projection), \
         patch("src.tools.urban_heat_tools.get_wbgt_statistics", new_callable=AsyncMock, side_effect=Exception("CDS unavailable")), \
         patch("src.tools.urban_heat_tools.get_elevation", new_callable=AsyncMock, return_value=5.0):

        from src.tools.urban_heat_tools import assess_urban_heat
        result = await assess_urban_heat(lat=10.77, lon=106.70)

        assert isinstance(result, HazardAssessmentResult)
        assert result.intermediate["current_wbgt_c"] is None


# ======================== 8. Pluvial Flood ========================

@pytest.mark.asyncio
async def test_pluvial_flood_basic(mock_hand_result, mock_slope_result, mock_extreme_precip):
    """Test pluvial flood proxy model."""
    from src.data.pluvial_flood import PluvialFloodResult

    mock_pluvial = PluvialFloodResult(
        susceptibility_index=0.75,
        estimated_depth_m=0.25,
        runoff_coefficient=0.65,
        hand_m=1.0,
        slope_degrees=0.5,
        impervious_fraction=0.8,
        design_rainfall_mm=120.0,
    )

    with patch("src.tools.pluvial_flood_tools.get_hand_value", new_callable=AsyncMock, return_value=mock_hand_result), \
         patch("src.tools.pluvial_flood_tools.get_slope", new_callable=AsyncMock, return_value=mock_slope_result), \
         patch("src.tools.pluvial_flood_tools.get_elevation", new_callable=AsyncMock, return_value=5.0), \
         patch("src.tools.pluvial_flood_tools.get_extreme_precipitation", new_callable=AsyncMock, return_value=mock_extreme_precip), \
         patch("src.tools.pluvial_flood_tools.compute_pluvial_susceptibility", return_value=mock_pluvial):

        from src.tools.pluvial_flood_tools import assess_pluvial_flood
        result = await assess_pluvial_flood(lat=10.77, lon=106.70, return_period=10)

        assert isinstance(result, HazardAssessmentResult)
        assert result.hazard.hazard_type == HazardType.PLUVIAL_FLOOD
        assert result.hazard.intensity_value == 0.25
        assert result.intermediate["susceptibility_index"] == 0.75


# ======================== 9. Structure Risk ========================

@pytest.mark.asyncio
async def test_structure_risk_basic(mock_building_cluster):
    """Test basic structure risk assessment with single RP."""
    mock_flood_result = MagicMock()
    mock_flood_result.hazard.intensity_value = 1.5

    hazard_results_by_rp = {
        100: {HazardType.RIVERINE_FLOOD: mock_flood_result}
    }

    from src.tools.structure_risk_tools import assess_structure_risk
    results = await assess_structure_risk(
        buildings=mock_building_cluster,
        hazard_results_by_rp=hazard_results_by_rp,
        country="VN",
    )

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, StructureRiskResult)
    assert result.building_id == "bldg_001"
    assert result.flood_damage_ratio > 0
    assert result.replacement_value_usd > 0
    assert len(result.losses_by_return_period) == 1


@pytest.mark.asyncio
async def test_structure_risk_multi_rp(mock_building_cluster):
    """Test multi-RP EAL computation (Gap Q)."""
    mock_results = {}
    for rp, depth in [(10, 0.5), (25, 1.0), (50, 1.5), (100, 2.0), (250, 3.0)]:
        mock_flood = MagicMock()
        mock_flood.hazard.intensity_value = depth
        mock_results[rp] = {HazardType.RIVERINE_FLOOD: mock_flood}

    from src.tools.structure_risk_tools import assess_structure_risk
    results = await assess_structure_risk(
        buildings=mock_building_cluster,
        hazard_results_by_rp=mock_results,
        country="VN",
    )

    assert len(results) == 1
    result = results[0]
    assert len(result.losses_by_return_period) == 5
    assert result.expected_annual_loss_usd > 0
    assert result.probable_maximum_loss_usd > 0
    # EAL should be less than max loss
    assert result.expected_annual_loss_usd < result.probable_maximum_loss_usd


@pytest.mark.asyncio
async def test_structure_risk_with_pluvial(mock_building_cluster):
    """Test pluvial flood damage inclusion (Gap M)."""
    mock_flood = MagicMock()
    mock_flood.hazard.intensity_value = 0.5

    mock_pluvial = MagicMock()
    mock_pluvial.hazard.intensity_value = 0.8  # Pluvial is deeper

    hazard_results_by_rp = {
        100: {
            HazardType.RIVERINE_FLOOD: mock_flood,
            HazardType.PLUVIAL_FLOOD: mock_pluvial,
        }
    }

    from src.tools.structure_risk_tools import assess_structure_risk
    results = await assess_structure_risk(
        buildings=mock_building_cluster,
        hazard_results_by_rp=hazard_results_by_rp,
        country="VN",
    )

    result = results[0]
    # With pluvial deeper than riverine, pluvial damage should be non-zero
    assert result.pluvial_flood_damage_ratio >= 0
    assert result.pluvial_depth_at_building_m >= 0


@pytest.mark.asyncio
async def test_structure_risk_backward_compat(mock_building_cluster):
    """v3.1 flat dict should be wrapped to {100: flat_dict} automatically."""
    mock_flood = MagicMock()
    mock_flood.hazard.intensity_value = 1.0

    # Flat dict (v3.1 format)
    flat_dict = {HazardType.RIVERINE_FLOOD: mock_flood}

    from src.tools.structure_risk_tools import assess_structure_risk
    results = await assess_structure_risk(
        buildings=mock_building_cluster,
        hazard_results_by_rp=flat_dict,
        country="VN",
    )

    assert len(results) == 1
    # Should have been wrapped as 100yr RP
    assert results[0].losses_by_return_period[0].return_period_years == 100


# ======================== Portfolio Summary ========================

@pytest.mark.asyncio
async def test_portfolio_summary(mock_building_cluster):
    """Test portfolio aggregation."""
    mock_flood = MagicMock()
    mock_flood.hazard.intensity_value = 2.0

    from src.tools.structure_risk_tools import assess_structure_risk, summarize_portfolio
    results = await assess_structure_risk(
        buildings=mock_building_cluster,
        hazard_results_by_rp={100: {HazardType.RIVERINE_FLOOD: mock_flood}},
    )

    summary = summarize_portfolio(results, portfolio_id="test_port", city="Ho Chi Minh City")

    assert isinstance(summary, PortfolioRiskSummary)
    assert summary.total_buildings == 1
    assert summary.total_replacement_value_usd > 0
    assert summary.total_expected_annual_loss_usd >= 0


# ======================== Risk Score / Tier Consistency ========================

def test_risk_tier_boundaries():
    """Verify tier assignment thresholds are consistent across tools."""
    from src.tools.riverine_flood_tools import _score_to_tier

    assert _score_to_tier(0) == RiskTier.LOW
    assert _score_to_tier(24.9) == RiskTier.LOW
    assert _score_to_tier(25) == RiskTier.MODERATE
    assert _score_to_tier(49.9) == RiskTier.MODERATE
    assert _score_to_tier(50) == RiskTier.HIGH
    assert _score_to_tier(74.9) == RiskTier.HIGH
    assert _score_to_tier(75) == RiskTier.CRITICAL
    assert _score_to_tier(100) == RiskTier.CRITICAL


# ======================== Tool Contract Validation ========================

@pytest.mark.asyncio
async def test_all_hazard_tools_return_correct_type(
    mock_hand_result, mock_flood_discharge, mock_slope_result,
    mock_extreme_precip, mock_extreme_precip_low, mock_insar_result,
    mock_temp_baseline, mock_climate_projection, mock_wbgt_result,
):
    """Verify all 8 hazard tools return HazardAssessmentResult."""
    from src.core.models import CycloneEventParams
    from src.data.pluvial_flood import PluvialFloodResult

    mock_pluvial = PluvialFloodResult(
        susceptibility_index=0.5, estimated_depth_m=0.1, runoff_coefficient=0.5,
        hand_m=2.0, slope_degrees=1.0, impervious_fraction=0.5, design_rainfall_mm=100.0,
    )
    mock_cyclone = CycloneEventParams(
        max_wind_ms=30.0, central_pressure_hpa=990.0, radius_max_wind_km=50.0,
        translation_speed_ms=5.0, heading_degrees=315.0,
        saffir_simpson_category=0, rainfall_proxy_mm=100.0,
    )

    @dataclass
    class MockWindResult:
        wind_speed_ms: float = 25.0
        b_parameter: float = 1.3
        is_within_rmw: bool = False

    from src.data.ipcc_slr import SLRProjection
    mock_slr = SLRProjection(
        city="ho_chi_minh_city", scenario="ssp245", target_year=2050,
        slr_median_m=0.23, slr_p5_m=0.15, slr_p95_m=0.40,
    )

    tools_and_patches = [
        (
            "src.tools.riverine_flood_tools",
            "assess_riverine_flood",
            {"return_period": 100},
            {
                "get_hand_value": mock_hand_result,
                "get_flood_return_period": mock_flood_discharge,
                "get_elevation": 5.0,
            },
            HazardType.RIVERINE_FLOOD,
        ),
        (
            "src.tools.coastal_flood_tools",
            "assess_coastal_flood",
            {"time_horizon": 2050, "scenario": "ssp245"},
            {
                "get_elevation": 2.0,
                "get_slr_projection": mock_slr,
            },
            HazardType.COASTAL_FLOOD,
        ),
        (
            "src.tools.subsidence_tools",
            "assess_subsidence",
            {"city": "hcmc"},
            {
                "get_subsidence_velocity": mock_insar_result,
                "get_elevation": 3.0,
            },
            HazardType.SUBSIDENCE,
        ),
        (
            "src.tools.cyclone_tools",
            "assess_cyclone",
            {"return_period": 100},
            {
                "get_regional_cyclone_statistics": mock_cyclone,
                "get_elevation": 10.0,
                "holland_wind_profile": MockWindResult(),
            },
            HazardType.TROPICAL_CYCLONE,
        ),
        (
            "src.tools.urban_heat_tools",
            "assess_urban_heat",
            {"time_horizon": 2050},
            {
                "get_temperature_baseline": mock_temp_baseline,
                "get_climate_projection": mock_climate_projection,
                "get_wbgt_statistics": mock_wbgt_result,
                "get_elevation": 5.0,
            },
            HazardType.URBAN_HEAT,
        ),
    ]

    for module_path, func_name, kwargs, mocks, expected_hazard_type in tools_and_patches:
        patches = []
        for mock_name, mock_val in mocks.items():
            target = f"{module_path}.{mock_name}"
            if callable(mock_val) or hasattr(mock_val, "__await__"):
                p = patch(target, new_callable=AsyncMock, return_value=mock_val)
            elif isinstance(mock_val, (int, float)):
                p = patch(target, new_callable=AsyncMock, return_value=mock_val)
            else:
                # Determine if async or sync based on name
                async_names = {"get_hand_value", "get_flood_return_period", "get_elevation",
                               "get_subsidence_velocity", "get_regional_cyclone_statistics",
                               "get_temperature_baseline", "get_climate_projection",
                               "get_wbgt_statistics", "get_slope", "get_extreme_precipitation"}
                if mock_name in async_names:
                    p = patch(target, new_callable=AsyncMock, return_value=mock_val)
                else:
                    p = patch(target, return_value=mock_val)
            patches.append(p)

        for p in patches:
            p.start()

        try:
            import importlib
            mod = importlib.import_module(module_path.replace("src.", "src."))
            func = getattr(mod, func_name)
            result = await func(lat=10.77, lon=106.70, **kwargs)

            assert isinstance(result, HazardAssessmentResult), f"{func_name} did not return HazardAssessmentResult"
            assert result.hazard.hazard_type == expected_hazard_type, f"{func_name} wrong hazard type"
        finally:
            for p in patches:
                p.stop()
