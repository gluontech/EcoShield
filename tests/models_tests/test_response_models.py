# tests/models_tests/test_response_models.py
"""Tests for the strict Pydantic v2 response schema (v3.0)."""

import json
import copy
from pathlib import Path

import pytest

from src.core.models.response_models import (
    RiskAssessmentReport,
    load_report,
    Asset,
    BuildingFootprint,
    BuildingHeight,
    HazardWeights,
    EventContext,
    HazardIntensityInfo,
    SubsidenceHazard,
    LandslideHazard,
    LandslideIntermediate,
    UnassessedHazard,
    TimeHorizonResponse,
    ConfidenceScore,
    DataSourceRef,
    ImpactResult,
    ResolutionInfo,
    DataLineage,
    ExposureOverrides,
)
from src.core.models.enums import HazardType, MatchMethod
from src.api.routes.assess import _select_primary_rp


FIXTURE_PATH = Path(__file__).resolve().parents[2] / "response_improved.json"


@pytest.fixture
def improved_data() -> dict:
    """Load the reference response_improved.json as a dict."""
    with open(FIXTURE_PATH) as f:
        return json.load(f)


@pytest.fixture
def report(improved_data: dict) -> RiskAssessmentReport:
    """Parse the reference response into a validated report."""
    return RiskAssessmentReport.model_validate(improved_data)


# ── Happy path ──

class TestRoundTrip:
    """Validate that response_improved.json parses and round-trips cleanly."""

    def test_parse_succeeds(self, report: RiskAssessmentReport) -> None:
        assert report.schema_version == "3.0"

    def test_location(self, report: RiskAssessmentReport) -> None:
        assert report.location.name == "The Waterfront Residence"
        assert -90 <= report.location.lat <= 90
        assert -180 <= report.location.lon <= 180

    def test_asset_not_none(self, report: RiskAssessmentReport) -> None:
        assert report.asset is not None
        assert report.asset.footprint.area_m2 > 0

    def test_hazard_count(self, report: RiskAssessmentReport) -> None:
        assert len(report.hazards) >= 1

    def test_no_duplicate_hazards(self, report: RiskAssessmentReport) -> None:
        types = [h.hazard_type for h in report.hazards]
        assert len(types) == len(set(types))

    def test_assessed_hazards_have_intermediates(
        self, report: RiskAssessmentReport
    ) -> None:
        for h in report.assessed_hazards():
            assert hasattr(h, "intermediate")

    def test_unassessed_hazard_in_fixture(self, report: RiskAssessmentReport) -> None:
        """Landslide is unassessed in the reference fixture (HCMC)."""
        landslide = report.hazard_by_type(HazardType.LANDSLIDE)
        assert isinstance(landslide, UnassessedHazard)
        assert landslide.risk_score == 0

    def test_round_trip_json(self, report: RiskAssessmentReport) -> None:
        dumped = report.model_dump_json()
        re_parsed = RiskAssessmentReport.model_validate_json(dumped)
        assert re_parsed.schema_version == report.schema_version
        assert len(re_parsed.hazards) == len(report.hazards)

    def test_structured_time_horizon(self, report: RiskAssessmentReport) -> None:
        assert report.time_horizon.start_year == 2041
        assert report.time_horizon.end_year == 2060
        assert report.time_horizon.representative_year == 2050

    def test_structured_confidence(self, report: RiskAssessmentReport) -> None:
        subsidence = report.hazard_by_type(HazardType.SUBSIDENCE)
        assert isinstance(subsidence.confidence, ConfidenceScore)
        assert subsidence.confidence.category.value == "low"
        assert 0 <= subsidence.confidence.score <= 1

    def test_structured_data_sources(self, report: RiskAssessmentReport) -> None:
        for ds in report.data_sources:
            assert isinstance(ds, DataSourceRef)
            assert len(ds.id) > 0

    def test_impact_score_normalized(self, report: RiskAssessmentReport) -> None:
        for h in report.assessed_hazards():
            assert 0 <= h.impact.score <= 1

    def test_no_return_period_or_multi_rp(self, report: RiskAssessmentReport) -> None:
        assert not hasattr(report, "return_period")
        assert not hasattr(report, "multi_rp")

    def test_flood_depth_capped(self, report: RiskAssessmentReport) -> None:
        """Riverine flood 45.92m should be capped to 15m by guardrail."""
        riverine = report.hazard_by_type(HazardType.RIVERINE_FLOOD)
        assert riverine.intermediate.flood_depth_m <= 15.0
        assert riverine.intermediate.depth_capped is True

    def test_wind_speed_capped(self, report: RiskAssessmentReport) -> None:
        """Tropical cyclone 120 m/s should be capped to 85 m/s."""
        cyclone = report.hazard_by_type(HazardType.TROPICAL_CYCLONE)
        assert cyclone.intermediate.site_wind_ms <= 85.0
        assert cyclone.intermediate.wind_capped is True

    def test_is_applicable_flag(self, report: RiskAssessmentReport) -> None:
        for h in report.assessed_hazards():
            if h.risk_score == 0:
                assert h.is_applicable is False
            else:
                assert h.is_applicable is True

    def test_none_risk_category_for_zero_score(
        self, report: RiskAssessmentReport
    ) -> None:
        surge = report.hazard_by_type(HazardType.STORM_SURGE)
        assert surge.risk_score == 0
        assert surge.risk_category.value == "None"

    def test_no_city_in_intermediates(self, report: RiskAssessmentReport) -> None:
        for h in report.assessed_hazards():
            inter_dict = h.intermediate.model_dump()
            assert "city" not in inter_dict


# ── Cross-field validators ──

class TestValidators:
    """Verify cross-field validators reject invalid data."""

    def test_weights_must_sum_to_one(self) -> None:
        with pytest.raises(ValueError, match="sum to 1.0"):
            HazardWeights(primary=0.5, secondary=0.5, tertiary=0.5)

    def test_weights_valid(self) -> None:
        w = HazardWeights(primary=0.6, secondary=0.25, tertiary=0.15)
        assert w.primary == 0.6

    def test_p5_gt_p95_rejected(self) -> None:
        with pytest.raises(ValueError, match="p5.*p95"):
            HazardIntensityInfo(
                value=10, unit="m", p5=50, p95=10,
                uncertainty_type="proxy_model_high_uncertainty",
            )

    def test_time_horizon_start_after_end(self) -> None:
        with pytest.raises(ValueError, match="start_year.*before end_year"):
            TimeHorizonResponse(
                start_year=2060, end_year=2041, representative_year=2050
            )

    def test_time_horizon_representative_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="representative_year.*must be within"):
            TimeHorizonResponse(
                start_year=2041, end_year=2060, representative_year=2030
            )

    def test_duplicate_hazard_types_rejected(self, improved_data: dict) -> None:
        data = copy.deepcopy(improved_data)
        # Duplicate the subsidence hazard (an assessed hazard, not landslide)
        data["hazards"].append(copy.deepcopy(data["hazards"][0]))
        with pytest.raises(ValueError, match="Duplicate hazard_type"):
            RiskAssessmentReport.model_validate(data)


# ── Scalar type enforcement ──

class TestScalarConstraints:
    """Verify annotated scalars reject out-of-range values."""

    def test_negative_area_rejected(self) -> None:
        with pytest.raises(ValueError):
            BuildingFootprint(
                building_id="test",
                source="test",
                centroid={"lat": 10, "lon": 106},
                footprint_wkt="POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))",
                area_m2=-100,
                confidence=0.5,
                match_method="buffer_overlap",
                footprint_match_confidence=0.9,
            )

    def test_confidence_gt_1_rejected(self) -> None:
        with pytest.raises(ValueError):
            BuildingFootprint(
                building_id="test",
                source="test",
                centroid={"lat": 10, "lon": 106},
                footprint_wkt="POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))",
                area_m2=100,
                confidence=1.5,
                match_method="buffer_overlap",
                footprint_match_confidence=0.9,
            )

    def test_invalid_wkt_rejected(self) -> None:
        with pytest.raises(ValueError, match="POLYGON"):
            BuildingFootprint(
                building_id="test",
                source="test",
                centroid={"lat": 10, "lon": 106},
                footprint_wkt="LINESTRING (0 0, 1 1)",
                area_m2=100,
                confidence=0.5,
                match_method="buffer_overlap",
                footprint_match_confidence=0.9,
            )


# ── Enum enforcement ──

class TestEnums:
    """Verify controlled enums reject unknown values."""

    def test_match_method_enum(self) -> None:
        assert MatchMethod("buffer_overlap") == MatchMethod.BUFFER_OVERLAP

    def test_invalid_match_method(self) -> None:
        with pytest.raises(ValueError):
            MatchMethod("teleportation")

    def test_hazard_type_enum_coverage(self) -> None:
        expected = {
            "subsidence", "urban_heat", "storm_surge", "coastal_flood",
            "riverine_flood", "pluvial_flood", "tropical_cyclone", "landslide",
        }
        actual = {h.value for h in HazardType}
        assert expected == actual


# ── Summary profile Optional fields (Issue 1) ──

class TestSummaryProfileOptionalFields:
    """Verify assessed hazards validate without summary-stripped fields."""

    def _minimal_hazard_dict(self) -> dict:
        """Return a minimal SubsidenceHazard dict without optional fields."""
        return {
            "hazard_type": "subsidence",
            "risk_score": 0.3,
            "risk_category": "Low",
            "confidence": {"score": 0.25, "category": "low"},
            "is_applicable": True,
            "key_drivers": [],
            # event_context, resolution, lineage, exposure_overrides, limitations
            # are intentionally OMITTED (summary profile)
            "intensity": {
                "value": 5.0, "unit": "mm/yr", "p5": 2.0, "p95": 8.0,
                "uncertainty_type": "proxy_model_high_uncertainty",
            },
            "data_sources": [{"id": "test", "name": "Test", "version": None}],
            "impact": {
                "score": 0.3, "tier": "Low",
                "status": "unvalidated",
                "validation_source": "unvalidated_baseline",
            },
            "can_aggregate_with": [],
            "dependency_order": 1,
            # intermediate also omitted (summary profile strips it)
        }

    def test_subsidence_without_optional_fields(self) -> None:
        """Summary profile record validates as SubsidenceHazard."""
        hazard = SubsidenceHazard.model_validate(self._minimal_hazard_dict())
        assert hazard.event_context is None
        assert hazard.resolution is None
        assert hazard.lineage is None
        assert hazard.exposure_overrides is None
        assert hazard.limitations is None
        assert hazard.intermediate is None

    def test_with_all_fields_still_works(self) -> None:
        """Standard profile with all fields still validates."""
        data = self._minimal_hazard_dict()
        data["event_context"] = {
            "event_type": "chronic", "return_period_years": None,
        }
        data["resolution"] = {
            "climate_forcing_m": 25000, "native_m": 30,
            "effective_m": 30, "signal_uniformity": "grid_cell",
            "downscaling_method": "terrain_overlay_only",
        }
        data["lineage"] = {"source": "insar", "timestamp": "2026-01-01T00:00:00Z"}
        data["exposure_overrides"] = {"adjustments_applied": []}
        data["limitations"] = ["Limited InSAR coverage"]
        data["intermediate"] = {
            "velocity_mm_yr": -5.0, "abs_rate_mm_yr": 5.0,
            "cumulative_mm": 150.0, "cumulative_m": 0.15,
            "years_forward": 30, "original_elevation_m": 3.0,
            "adjusted_elevation_m": 2.85, "subsidence_source": "insar",
        }
        hazard = SubsidenceHazard.model_validate(data)
        assert hazard.event_context is not None
        assert hazard.intermediate is not None


# ── Landslide assessed hazard (Issue 2) ──

class TestLandslideAssessedHazard:
    """Verify landslide records parse as LandslideHazard, not UnassessedHazard."""

    def test_landslide_hazard_construction(self) -> None:
        data = {
            "hazard_type": "landslide",
            "risk_score": 0.45,
            "risk_category": "Moderate",
            "confidence": {"score": 0.50, "category": "moderate"},
            "is_applicable": True,
            "key_drivers": [],
            "intensity": {
                "value": 42.0, "unit": "m",
                "p5": 29.4, "p95": 54.6,
                "uncertainty_type": "proxy_model_high_uncertainty",
            },
            "data_sources": [
                {"id": "copernicus_glo30", "name": "GLO-30 DEM", "version": None},
            ],
            "impact": {
                "score": 0.42, "tier": "Moderate",
                "status": "unvalidated",
                "validation_source": "unvalidated_baseline",
            },
            "can_aggregate_with": ["riverine_flood", "tropical_cyclone"],
            "dependency_order": 6,
            "intermediate": {
                "slope_degrees": 18.5,
                "base_susceptibility": 35.0,
                "soil_factor": 0.45,
                "vegetation_factor": 0.6,
                "trigger_ratio": 1.2,
                "triggered": True,
                "combined_score": 42.0,
                "precip_mm_day": 85.3,
            },
        }
        hazard = LandslideHazard.model_validate(data)
        assert hazard.hazard_type == HazardType.LANDSLIDE
        assert hazard.intermediate.triggered is True
        assert hazard.intermediate.slope_degrees == 18.5

    def test_landslide_summary_mode(self) -> None:
        """Landslide in summary mode (no intermediate) still validates."""
        data = {
            "hazard_type": "landslide",
            "risk_score": 0.45,
            "risk_category": "Moderate",
            "confidence": {"score": 0.50, "category": "moderate"},
            "is_applicable": True,
            "key_drivers": [],
            "intensity": {
                "value": 42.0, "unit": "m",
                "p5": 29.4, "p95": 54.6,
                "uncertainty_type": "proxy_model_high_uncertainty",
            },
            "data_sources": [
                {"id": "copernicus_glo30", "name": "GLO-30 DEM", "version": None},
            ],
            "impact": {
                "score": 0.42, "tier": "Moderate",
                "status": "unvalidated",
                "validation_source": "unvalidated_baseline",
            },
            "can_aggregate_with": [],
            "dependency_order": 6,
        }
        hazard = LandslideHazard.model_validate(data)
        assert hazard.intermediate is None


# ── Primary RP selection (Issue 3) ──

class TestSelectPrimaryRp:
    """Verify _select_primary_rp picks the right return period."""

    def test_default_periods_returns_100(self) -> None:
        assert _select_primary_rp([10, 25, 50, 100, 250]) == 100

    def test_single_period_100(self) -> None:
        assert _select_primary_rp([100]) == 100

    def test_no_100_returns_max(self) -> None:
        assert _select_primary_rp([10, 25, 50]) == 50

    def test_single_non_100(self) -> None:
        assert _select_primary_rp([250]) == 250

    def test_all_standard_periods(self) -> None:
        assert _select_primary_rp([2, 5, 10, 25, 50, 100, 250, 500, 1000]) == 100
