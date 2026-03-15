# src/api/routes/assess.py
"""POST /v1/assess — single-site hazard assessment (schema v2.0)."""

import time

from fastapi import APIRouter, HTTPException

from src.api.schemas.requests import AssessRequest
from src.api.schemas.responses import RiskAssessmentReport
from src.api.hazard_adapter import adapt_hazard_result
from src.api.utils import score_to_category
from src.workflows.hazard_workflow import run_hazard_assessment

router = APIRouter()


@router.post("/assess", response_model=RiskAssessmentReport)
async def assess_site(request: AssessRequest):
    """
    Perform multi-hazard climate risk assessment for a single location.

    Hazards are auto-detected from the city key via CITY_HAZARDS config.

    Returns a schema v2.0 ``RiskAssessmentReport`` with:
    - A single root-level ``asset`` (no per-hazard duplication)
    - Discriminated-union ``hazards`` with typed intermediates
    - Strict validation on all fields
    """
    start = time.monotonic()

    try:
        result = await run_hazard_assessment(
            lat=request.location.lat,
            lon=request.location.lon,
            name=request.structure.name,
            address=request.structure.address,
            city=request.city,
            slr_scenario=request.scenario.value,
            time_horizon=request.time_horizon.midpoint,
            return_period=_select_primary_rp(request.return_periods),
            include_buildings=True,
            multi_rp=len(request.return_periods) > 1,
            return_periods=request.return_periods,
            structure_category=request.structure.category,
            structure_type=request.structure.type,
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Data not available: {e}. Run ingestion first.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # ── Unpack legacy result ──
    result_dict = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    chronic = result_dict.get("chronic_hazard_details", {})
    acute = result_dict.get("acute_hazard_details", {})
    hazards_data = {**chronic, **acute}

    # ── Build asset ONCE from the first hazard that has exposure ──
    asset_dict = _extract_asset(hazards_data)

    # ── Build each hazard record via adapter ──
    hazard_records: list[dict] = []
    scores: list[float] = []
    all_data_sources: dict[str, dict] = {}  # keyed by source id for dedup

    for hazard_type, hazard_result in hazards_data.items():
        raw_score = hazard_result.get("impact_score", 0.0)
        norm_score = raw_score / 100.0 if raw_score > 1 else raw_score
        scores.append(raw_score)

        hazard_node = hazard_result.get("hazard", {})
        confidence = str(hazard_node.get("confidence", "moderate"))

        record = adapt_hazard_result(
            hazard_type=hazard_type,
            result_dict=hazard_result,
            risk_score=round(norm_score, 4),
            risk_category=score_to_category(norm_score),
            confidence=confidence,
            response_profile=request.response_profile.value,
        )
        hazard_records.append(record)

        # Collect data sources for top-level dedup
        for ds in record.get("data_sources", []):
            all_data_sources[ds["id"]] = ds

    overall = sum(scores) / len(scores) if scores else 0.0
    overall_norm = overall / 100.0 if overall > 1 else overall

    portfolio_eal = result_dict.get("portfolio_eal_usd", 0)

    report_dict = {
        "schema_version": "3.0",
        "engine": {
            "version": "v3.2.0",
            "processor": "EcoShield Core",
        },
        "location": {
            "lat": request.location.lat,
            "lon": request.location.lon,
            "name": request.structure.name or "Unknown",
        },
        "scenario": request.scenario.value,
        "time_horizon": {
            "start_year": request.time_horizon.start_year,
            "end_year": request.time_horizon.end_year,
            "representative_year": request.time_horizon.midpoint,
        },
        "return_periods_assessed": request.return_periods,
        "asset": asset_dict,
        "overall_risk_score": round(overall_norm, 3),
        "overall_risk_category": score_to_category(overall_norm),
        "aggregation_method": "composite_weighted_average",
        "hazard_weights": {"primary": 0.6, "secondary": 0.25, "tertiary": 0.15},
        "hazards": hazard_records,
        "portfolio_eal_usd": portfolio_eal or 0,
        "data_sources": list(all_data_sources.values()),
    }

    return RiskAssessmentReport.model_validate(report_dict)


def _extract_asset(hazards_data: dict) -> dict:
    """Extract the asset from the first hazard's exposure block.

    The legacy format embeds the full structure under each hazard's
    ``exposure.structure``. We pull it from the first available hazard
    and reshape into the v2.0 flat ``Asset`` format.
    """
    for _, hazard_result in hazards_data.items():
        exposure = hazard_result.get("exposure", {})
        structure = exposure.get("structure")
        if not structure:
            continue

        footprint_raw = structure.get("footprint", {})
        height_raw = structure.get("height", {})

        return {
            "footprint": {
                "building_id": footprint_raw.get("building_id", "unknown"),
                "source": footprint_raw.get("source", "unknown"),
                "overture_id": footprint_raw.get("overture_id"),
                "osm_id": footprint_raw.get("osm_id"),
                "name": footprint_raw.get("name"),
                "address": footprint_raw.get("address"),
                "name_aliases": footprint_raw.get("name_aliases", []),
                "centroid": footprint_raw.get("centroid", {"lat": 0, "lon": 0}),
                "footprint_wkt": footprint_raw.get("footprint_wkt", "POLYGON EMPTY"),
                "area_m2": footprint_raw.get("area_m2", 1.0),
                "confidence": footprint_raw.get("confidence", 0),
                "match_method": footprint_raw.get("match_method", "buffer_overlap"),
                "footprint_match_confidence": footprint_raw.get(
                    "footprint_match_confidence", 0
                ),
            },
            "height": {
                "height_m": height_raw.get("height_m", 3.0),
                "source": height_raw.get("height_source", "unknown"),
                "year": height_raw.get("height_year", 2023),
                "uncertainty_m": height_raw.get("height_uncertainty_m", 1.5),
                "confidence": height_raw.get("height_confidence", 0.5),
                "building_presence": height_raw.get("building_presence", 0.5),
                "num_floors": height_raw.get("num_floors"),
                "estimated_stories": height_raw.get("estimated_stories"),
            },
            "material": structure.get("material", "unknown"),
            "material_inferred": structure.get("material_inferred", True),
            "occupancy": structure.get("occupancy", "unknown"),
            "vulnerability_class": structure.get("vulnerability_class", "class_iii"),
            "classification_source": structure.get(
                "classification_source", "area_height_inference"
            ),
            "construction_year": structure.get("construction_year"),
            "num_stories": structure.get("num_stories"),
            "has_basement": structure.get("has_basement", False),
            "has_stilts": structure.get("has_stilts", False),
            "roof_type": structure.get("roof_type"),
            "wall_material": structure.get("wall_material"),
            "ground_elevation_m": structure.get("ground_elevation_m", 0),
            "ground_floor_height_m": structure.get("ground_floor_height_m", 0),
            "effective_ground_floor_m": structure.get("effective_ground_floor_m", 0),
            "poi_validated": structure.get("poi_validated", False),
            "replacement_value_usd": structure.get("replacement_value_usd"),
            "replacement_value_source": structure.get(
                "replacement_value_source", "jrc_country_estimate"
            ),
            "elevation_m": exposure.get("elevation_m", 0),
            "elevation_source": exposure.get("elevation_source", "copernicus_glo30"),
            "elevation_uncertainty_m": exposure.get("elevation_uncertainty_m", 0.5),
        }

    # Fallback — should never happen in practice
    raise ValueError("No hazard result contained exposure/structure data")


def _select_primary_rp(periods: list[int]) -> int:
    """Select 100-year RP if available, otherwise largest.

    The request validator sorts periods ascending, so periods[0] is
    the smallest (e.g. 10-year).  Using it as the primary RP biases
    assessments toward low-severity events.  We prefer RP=100 as the
    industry-standard design return period.
    """
    if 100 in periods:
        return 100
    return max(periods)

