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
            roof_type=request.structure.roof_type,
            wall_material=request.structure.wall_material,
            ground_floor_height_m=request.structure.ground_floor_height_m,
            num_floors=request.structure.num_floors,
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
        exposure = hazard_result.get("exposure", {}) if isinstance(hazard_result, dict) else {}
        structure = exposure.get("structure")
        if not structure or not isinstance(structure, dict):
            continue

        footprint_raw = structure.get("footprint") or {}
        height_raw = structure.get("height") or {}

        wkt = footprint_raw.get("footprint_wkt")
        if not wkt or not isinstance(wkt, str) or not wkt.strip().upper().startswith("POLYGON"):
            wkt = "POLYGON EMPTY"

        match_method = footprint_raw.get("match_method") or "buffer_overlap"
        if not match_method or not isinstance(match_method, str):
            match_method = "buffer_overlap"

        gfh = float(structure.get("ground_floor_height_m") or 0.0)
        egfh = max(float(structure.get("effective_ground_floor_m") or 0.0), gfh)

        return {
            "footprint": {
                "building_id": footprint_raw.get("building_id") or "unknown",
                "source": footprint_raw.get("source") or "unknown",
                "overture_id": footprint_raw.get("overture_id"),
                "osm_id": footprint_raw.get("osm_id"),
                "name": footprint_raw.get("name"),
                "address": footprint_raw.get("address"),
                "name_aliases": footprint_raw.get("name_aliases") or [],
                "centroid": footprint_raw.get("centroid") or {"lat": 0.0, "lon": 0.0},
                "footprint_wkt": wkt,
                "area_m2": float(footprint_raw.get("area_m2") or 1.0),
                "confidence": float(footprint_raw.get("confidence") or 0.0),
                "match_method": match_method,
                "footprint_match_confidence": float(
                    footprint_raw.get("footprint_match_confidence") or 0.0
                ),
            },
            "height": {
                "height_m": float(height_raw.get("height_m") or height_raw.get("height") or 3.0),
                "source": height_raw.get("height_source") or height_raw.get("source") or "unknown",
                "year": int(height_raw.get("height_year") or height_raw.get("year") or 2023),
                "uncertainty_m": float(
                    height_raw.get("height_uncertainty_m") or height_raw.get("uncertainty_m") or 1.5
                ),
                "confidence": float(
                    height_raw.get("height_confidence") or height_raw.get("confidence") or 0.5
                ),
                "building_presence": float(height_raw.get("building_presence") or 0.5),
                "num_floors": height_raw.get("num_floors"),
                "estimated_stories": height_raw.get("estimated_stories"),
            },
            "structural_material": structure.get("material") or "unknown",
            "material_inferred": structure.get("material_inferred") if structure.get("material_inferred") is not None else True,
            "occupancy": structure.get("occupancy") or "unknown",
            "vulnerability_class": structure.get("vulnerability_class") or "class_iii",
            "classification_source": structure.get(
                "classification_source"
            ) or "area_height_inference",
            "construction_year": structure.get("construction_year"),
            "num_stories": structure.get("num_stories"),
            "has_basement": bool(structure.get("has_basement", False)),
            "has_stilts": bool(structure.get("has_stilts", False)),
            "roof_type": structure.get("roof_type"),
            "wall_material": structure.get("wall_material"),
            "ground_elevation_m": float(structure.get("ground_elevation_m") or 0.0),
            "ground_floor_height_m": gfh,
            "effective_ground_floor_m": egfh,
            "poi_validated": bool(structure.get("poi_validated", False)),
            "replacement_value_usd": structure.get("replacement_value_usd"),
            "replacement_value_source": structure.get(
                "replacement_value_source"
            ) or "jrc_country_estimate",
            "elevation_m": float(exposure.get("elevation_m") or 0.0),
            "elevation_source": exposure.get("elevation_source") or "copernicus_glo30",
            "elevation_uncertainty_m": float(
                exposure.get("elevation_uncertainty_m") or 0.5
            ),
        }

    # Fallback default asset when no structure is present in hazards_data
    return {
        "footprint": {
            "building_id": "unknown",
            "source": "unknown",
            "centroid": {"lat": 0.0, "lon": 0.0},
            "footprint_wkt": "POLYGON EMPTY",
            "area_m2": 1.0,
            "confidence": 0.0,
            "match_method": "buffer_overlap",
            "footprint_match_confidence": 0.0,
        },
        "height": {
            "height_m": 3.0,
            "source": "unknown",
            "year": 2023,
            "uncertainty_m": 1.5,
            "confidence": 0.5,
            "building_presence": 0.5,
        },
        "structural_material": "unknown",
        "material_inferred": True,
        "occupancy": "unknown",
        "vulnerability_class": "class_iii",
        "classification_source": "area_height_inference",
        "has_basement": False,
        "has_stilts": False,
        "ground_elevation_m": 0.0,
        "ground_floor_height_m": 0.0,
        "effective_ground_floor_m": 0.0,
        "poi_validated": False,
        "replacement_value_source": "jrc_country_estimate",
        "elevation_m": 0.0,
        "elevation_source": "copernicus_glo30",
        "elevation_uncertainty_m": 0.5,
    }


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

