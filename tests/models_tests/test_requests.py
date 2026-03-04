# tests/models_tests/test_requests.py
"""Unit tests for EcoShield request schema (v3.0)."""

import pytest
from pydantic import ValidationError

from src.api.schemas.requests import (
    AssessRequest,
    BuildingAssessRequest,
    Location,
    PortfolioRequest,
    PortfolioSite,
    Structure,
    TimeHorizon,
)


# ── TimeHorizon ─────────────────────────────────────────────────────────────

class TestTimeHorizon:
    def test_valid_time_horizon(self) -> None:
        th = TimeHorizon(start_year=2041, end_year=2060)
        assert th.midpoint == 2050
        assert str(th) == "2041-2060"

    def test_start_after_end_raises(self) -> None:
        with pytest.raises(ValidationError, match="start_year.*before.*end_year"):
            TimeHorizon(start_year=2060, end_year=2041)

    def test_equal_years_raises(self) -> None:
        with pytest.raises(ValidationError, match="start_year.*before.*end_year"):
            TimeHorizon(start_year=2050, end_year=2050)

    def test_year_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            TimeHorizon(start_year=1900, end_year=2060)


# ── Location ────────────────────────────────────────────────────────────────

class TestLocation:
    def test_valid_location(self) -> None:
        loc = Location(lat=10.78, lon=106.69)
        assert loc.lat == 10.78

    def test_lat_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            Location(lat=100, lon=106.69)

    def test_lon_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            Location(lat=10.78, lon=200)


# ── Structure ───────────────────────────────────────────────────────────────

class TestStructure:
    def test_valid_structure(self) -> None:
        s = Structure(category="commercial", type="hotel", name="Test Hotel")
        assert s.category.value == "commercial"
        assert s.type.value == "hotel"

    def test_type_mismatch_raises(self) -> None:
        """Hotel is not valid under residential category."""
        with pytest.raises(ValidationError, match="not valid for category"):
            Structure(category="residential", type="hotel")

    def test_residential_types(self) -> None:
        s = Structure(category="residential", type="tube_house")
        assert s.type.value == "tube_house"

    def test_industrial_types(self) -> None:
        s = Structure(category="industrial", type="warehouse")
        assert s.type.value == "warehouse"

    def test_converted_type_under_commercial(self) -> None:
        s = Structure(category="commercial", type="converted_tube_house_hotel")
        assert s.type.value == "converted_tube_house_hotel"

    def test_converted_type_under_residential_raises(self) -> None:
        with pytest.raises(ValidationError, match="not valid for category"):
            Structure(category="residential", type="converted_tube_house_hotel")

    def test_invalid_type_value(self) -> None:
        with pytest.raises(ValidationError):
            Structure(category="commercial", type="spaceship")

    def test_invalid_category_value(self) -> None:
        with pytest.raises(ValidationError):
            Structure(category="agricultural", type="hotel")


# ── AssessRequest ───────────────────────────────────────────────────────────

class TestAssessRequest:
    def _valid_payload(self, **overrides) -> dict:
        """Build a valid AssessRequest dict, with optional overrides."""
        payload = {
            "request_id": "test-req-001",
            "location": {"lat": 10.78, "lon": 106.69},
            "structure": {"category": "commercial", "type": "hotel"},
            "city": "hcmc",
            "scenario": "ssp245",
            "time_horizon": {"start_year": 2041, "end_year": 2060},
            "return_periods": [10, 25, 50, 100, 250],
            "response_profile": "standard",
        }
        payload.update(overrides)
        return payload

    def test_valid_request(self) -> None:
        req = AssessRequest(**self._valid_payload())
        assert req.request_id == "test-req-001"
        assert req.location.lat == 10.78
        assert req.structure.type.value == "hotel"
        assert req.time_horizon.midpoint == 2050
        assert len(req.return_periods) == 5

    def test_missing_request_id_raises(self) -> None:
        payload = self._valid_payload()
        del payload["request_id"]
        with pytest.raises(ValidationError, match="request_id"):
            AssessRequest(**payload)

    def test_empty_request_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            AssessRequest(**self._valid_payload(request_id=""))

    def test_invalid_scenario_raises(self) -> None:
        with pytest.raises(ValidationError):
            AssessRequest(**self._valid_payload(scenario="rcp85"))

    def test_valid_scenario_enum(self) -> None:
        for scenario in ["ssp119", "ssp126", "ssp245", "ssp370", "ssp585"]:
            req = AssessRequest(**self._valid_payload(scenario=scenario))
            assert req.scenario.value == scenario

    def test_return_periods_out_of_range_raises(self) -> None:
        with pytest.raises(ValidationError, match="out of range"):
            AssessRequest(**self._valid_payload(return_periods=[1]))

    def test_return_periods_too_many_raises(self) -> None:
        with pytest.raises(ValidationError, match="at most 10"):
            AssessRequest(**self._valid_payload(
                return_periods=list(range(2, 14))  # 12 values
            ))

    def test_return_periods_empty_raises(self) -> None:
        with pytest.raises(ValidationError, match="at least 1"):
            AssessRequest(**self._valid_payload(return_periods=[]))

    def test_return_periods_sorted_and_deduplicated(self) -> None:
        req = AssessRequest(**self._valid_payload(return_periods=[100, 10, 50, 10]))
        assert req.return_periods == [10, 50, 100]

    def test_defaults(self) -> None:
        """Minimal payload with defaults."""
        req = AssessRequest(
            request_id="min-001",
            location={"lat": 10, "lon": 106},
            structure={"category": "commercial", "type": "hotel"},
        )
        assert req.scenario.value == "ssp245"
        assert req.city == "hcmc"
        assert req.time_horizon.midpoint == 2050
        assert req.return_periods == [10, 25, 50, 100, 250]
        assert req.response_profile.value == "standard"

    def test_response_profile_values(self) -> None:
        for profile in ["summary", "standard", "full_debug"]:
            req = AssessRequest(**self._valid_payload(response_profile=profile))
            assert req.response_profile.value == profile

    def test_invalid_response_profile_raises(self) -> None:
        with pytest.raises(ValidationError):
            AssessRequest(**self._valid_payload(response_profile="verbose"))

    def test_structure_hierarchical_validation(self) -> None:
        """Category/type mismatch caught at request level."""
        with pytest.raises(ValidationError, match="not valid for category"):
            AssessRequest(**self._valid_payload(
                structure={"category": "residential", "type": "hotel"}
            ))


# ── BuildingAssessRequest ───────────────────────────────────────────────────

class TestBuildingAssessRequest:
    def test_valid_request(self) -> None:
        req = BuildingAssessRequest(lat=10.78, lon=106.69, city="hcmc")
        assert req.time_horizon.midpoint == 2050
        assert len(req.return_periods) == 5

    def test_invalid_city_raises(self) -> None:
        with pytest.raises(ValidationError, match="not supported"):
            BuildingAssessRequest(lat=10.78, lon=106.69, city="london")

    def test_all_valid_cities(self) -> None:
        for city in ["hcmc", "hanoi", "danang", "jakarta", "manila", "bangkok", "singapore"]:
            req = BuildingAssessRequest(lat=10.78, lon=106.69, city=city)
            assert req.city == city


# ── PortfolioRequest ────────────────────────────────────────────────────────

class TestPortfolioRequest:
    def test_valid_portfolio(self) -> None:
        req = PortfolioRequest(
            request_id="port-001",
            sites=[
                {
                    "location": {"lat": 10.78, "lon": 106.69},
                    "structure": {"category": "commercial", "type": "hotel"},
                    "city": "hcmc",
                },
                {
                    "location": {"lat": 21.02, "lon": 105.85},
                    "city": "hanoi",
                },
            ],
        )
        assert req.request_id == "port-001"
        assert len(req.sites) == 2
        assert req.sites[0].structure is not None
        assert req.sites[1].structure is None

    def test_empty_sites_raises(self) -> None:
        with pytest.raises(ValidationError):
            PortfolioRequest(request_id="empty", sites=[])
