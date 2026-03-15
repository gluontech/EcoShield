# tests/unit/test_models.py
"""Unit tests for EcoShield v3.2 core models."""

import pytest
from datetime import datetime, timezone
from src.core.models import *

def test_location_validation():
    loc = Location(lat=10.7, lon=106.7)
    assert loc.lat == 10.7
    
def test_location_invalid():
    with pytest.raises(ValueError):
        Location(lat=100, lon=106.7)  # lat > 90

def test_bounding_box_area_correction():
    # 1x1 degree execution near equator vs near 0
    # Equator (0 deg lat)
    bb_eq = BoundingBox(min_lat=0, max_lat=1, min_lon=0, max_lon=1)
    # 45 deg lat (cos(45) ~ 0.707)
    bb_45 = BoundingBox(min_lat=45, max_lat=46, min_lon=0, max_lon=1)
    
    assert bb_eq.area_km2 > bb_45.area_km2
    assert bb_45.area_km2 < 12300  # Should be ~8700 km2

def test_data_lineage_integration():
    lineage = DataLineage(
        source=DataSource.GOOGLE_OPEN_BUILDINGS_V3,
        version="v1.0"
    )
    assert lineage.timestamp <= datetime.now(timezone.utc)
    assert lineage.processor == "EcoShield Core"

# --- Gap 2.1: Validation Metrics ---
def test_validation_metrics_integration():
    metrics = ValidationMetrics(
        rmse=0.5,
        bias=0.1,
        validation_source="gauge_data"
    )
    assert metrics.rmse == 0.5
    
    result = HazardAssessmentResult(
        hazard=HazardIntensity(
            hazard_type=HazardType.RIVERINE_FLOOD,
            event_context=HazardEventContext(
                event_type="acute",
                return_period_years=100
            ),
            intensity_value=2.5,
            intensity_unit="m",
            native_resolution_m=30,
            effective_resolution_m=30
        ),
        exposure=ExposureProfile(
            location=Location(lat=0, lon=0),
            structure=StructuralCharacteristics(
                footprint=BuildingFootprint(
                    building_id="test",
                    source=DataSource.GOOGLE_OPEN_BUILDINGS_V3,
                    centroid=Location(lat=0, lon=0),
                    area_m2=100
                )
            ),
            elevation_m=5.0
        ),
        impact_score=50,
        impact_tier=RiskTier.MODERATE,
        validation=metrics,
        status=ValidationStatus.VALIDATED
    )
    assert result.status == ValidationStatus.VALIDATED
    assert result.validation.rmse == 0.5

# --- Asset Models (v3.2) ---

def test_building_footprint():
    fp = BuildingFootprint(
        building_id="8Q7X+M2",
        source=DataSource.GOOGLE_OPEN_BUILDINGS_V3,
        centroid=Location(lat=10.77, lon=106.70),
        area_m2=120.5,
        confidence=0.85,
    )
    assert fp.area_m2 == 120.5
    assert fp.confidence >= 0.65

def test_building_height_confidence():
    # Gap 4.1 fix
    h = BuildingHeight(
        height_m=12.5, 
        height_year=2023,
        height_confidence=0.4  # Low confidence
    )
    # estimated_stories is None on standalone BuildingHeight without num_floors
    # (populated later by StructuralCharacteristics with occupancy-aware ratio)
    assert h.estimated_stories is None
    assert h.height_confidence == 0.4

def test_structural_characteristics_effective_floor():
    fp = BuildingFootprint(
        building_id="test_001",
        source=DataSource.GOOGLE_OPEN_BUILDINGS_V3,
        centroid=Location(lat=10.77, lon=106.70),
        area_m2=100.0,
    )
    sc = StructuralCharacteristics(
        footprint=fp,
        ground_elevation_m=3.5,
        ground_floor_height_m=0.5,
        has_stilts=True,
    )
    # 3.5 + 0.5 + 1.5 (stilts) = 5.5m above MSL
    assert sc.effective_ground_floor_m == 5.5

# --- Surface Adjustments (Gap S) ---

def test_building_adjusted_surface_subsidence_source():
    # Gap 4.2 fix
    bas = BuildingAdjustedSurface(
        building_id="b1",
        original_elevation_m=2.0,
        subsidence_source="insar_measured"
    )
    bas.apply_subsidence(rate_mm_yr=10.0, horizon_years=20)
    # 10mm/yr * 20yr = 200mm = 0.2m
    assert bas.subsidence_cumulative_m == 0.2
    assert bas.effective_elevation_m == 1.8
    assert bas.subsidence_source == "insar_measured"

def test_building_adjusted_surface_double_count_prevention():
    bas = BuildingAdjustedSurface(
        building_id="b1",
        original_elevation_m=2.0
    )
    bas.apply_slr(0.5)
    with pytest.raises(ValueError):
        bas.apply_slr(0.3)

# --- Multi-RP EAL (Gap Q) ---

def test_eal_calculation_trapezoidal():
    # 3 points: 10yr (p=0.1), 50yr (p=0.02), 100yr (p=0.01)
    points = [
        ReturnPeriodLoss(return_period_years=10, exceedance_probability=0.1, damage_ratio=0.1, loss_usd=10000),
        ReturnPeriodLoss(return_period_years=50, exceedance_probability=0.02, damage_ratio=0.5, loss_usd=50000),
        ReturnPeriodLoss(return_period_years=100, exceedance_probability=0.01, damage_ratio=0.8, loss_usd=80000),
    ]
    replacement_value = 100000
    
    eal = compute_eal_trapezoidal(points)
    
    # Expected logic:
    # 1. 0.1 to 0.02: avg loss (0.1+0.5)/2 * RV = 0.3*100k = 30k. Prob width = 0.08. Contribution = 2400.
    # 2. 0.02 to 0.01: avg loss (0.5+0.8)/2 * RV = 0.65*100k = 65k. Prob width = 0.01. Contribution = 650.
    # 3. Tail upper (p=0.01 to 0): loss 0.8*100k = 80k. Width 0.01. Contribution = 800.
    # 4. Tail lower (p=1 to 0.1): loss 0 to 0.1*100k. Avg ~5k? Logic says 0.5*min_loss*(1-max_p) = 0.5*10k*0.9 = 4500.
    
    # Total approx: 2400 + 650 = 3050 (trapezoidal without tails)
    assert eal > 0
    assert 3000 < eal < 3100

# --- JRC Vulnerability ---

def test_depth_damage_interpolation_jrc():
    curve = DepthDamageCurve(
        vulnerability_class=VulnerabilityClass.CLASS_I_INFORMAL,
        points=[
            DepthDamagePoint(depth_m=0.0, damage_ratio=0.05),
            DepthDamagePoint(depth_m=1.0, damage_ratio=0.55),
        ]
    )
    # 0.5m should be halfway between 0.05 and 0.55 = 0.30
    assert curve.interpolate_damage(0.5) == pytest.approx(0.30)

def test_occupancy_multiplier():
    assert APP_OCCUPANCY_VALUE_MULTIPLIER[BuildingOccupancy.COMMERCIAL] == 2.5
    assert APP_OCCUPANCY_VALUE_MULTIPLIER[BuildingOccupancy.RESIDENTIAL_INFORMAL] == 0.3
