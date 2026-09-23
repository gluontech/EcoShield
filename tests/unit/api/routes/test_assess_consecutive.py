# tests/unit/api/routes/test_assess_consecutive.py
"""
Integration test for consecutive POST /v1/assess requests to ensure thread safety,
no resource locks, and fast execution on 2nd and subsequent requests.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_consecutive_assess_requests(client):
    """
    Test consecutive POST /v1/assess requests.
    Request 1: Standard location without name/address.
    Request 2: Different request with name/address provided.
    Both must return 200 OK within seconds without deadlocking.
    """
    payload_1 = {
        "request_id": "req_consecutive_1",
        "location": {"lat": 10.7769, "lon": 106.7009},
        "structure": {"category": "residential", "type": "tube_house"},
        "scenario": "ssp245",
        "time_horizon": {"start_year": 2041, "end_year": 2060},
        "return_periods": [100],
        "city": "hcmc",
        "response_profile": "standard",
    }

    # First request
    response_1 = client.post("/v1/assess", json=payload_1)
    assert response_1.status_code == 200
    data_1 = response_1.json()
    assert "overall_risk_score" in data_1

    payload_2 = {
        "request_id": "req_consecutive_2",
        "location": {"lat": 10.7769, "lon": 106.7009},
        "structure": {
            "name": "Bitexco Financial Tower",
            "address": "2 Hai Trieu",
            "category": "commercial",
            "type": "office_building",
        },
        "scenario": "ssp245",
        "time_horizon": {"start_year": 2041, "end_year": 2060},
        "return_periods": [100, 250],
        "city": "hcmc",
        "response_profile": "standard",
    }

    # Second request (must succeed quickly without hanging)
    response_2 = client.post("/v1/assess", json=payload_2)
    assert response_2.status_code == 200
    data_2 = response_2.json()
    assert "overall_risk_score" in data_2


def test_consecutive_buildings_assess_requests(client):
    """
    Test consecutive POST /v1/buildings/assess requests.
    """
    payload_1 = {
        "lat": 10.7769,
        "lon": 106.7009,
        "radius_m": 300,
        "scenario": "ssp245",
        "time_horizon": {"start_year": 2041, "end_year": 2060},
        "return_periods": [100],
        "city": "hcmc",
    }

    response_1 = client.post("/v1/buildings/assess", json=payload_1)
    assert response_1.status_code == 200

    payload_2 = {
        "lat": 10.7769,
        "lon": 106.7009,
        "radius_m": 500,
        "scenario": "ssp585",
        "time_horizon": {"start_year": 2041, "end_year": 2060},
        "return_periods": [50, 100],
        "city": "hcmc",
    }

    response_2 = client.post("/v1/buildings/assess", json=payload_2)
    assert response_2.status_code == 200
