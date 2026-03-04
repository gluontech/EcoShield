# src/api/hazard_adapter.py
"""
Adapter layer: converts legacy ``HazardAssessmentResult`` dicts
(with embedded exposure) into the new strict ``HazardRecord`` subtypes
for schema v3.0.

Changes from v2.0:
- Confidence emitted as structured {score, category} dict.
- Impact score normalized to 0-1 (was 0-100).
- Data sources emitted as structured {id, name, version} dicts.
- City removed from intermediate dicts.
- is_applicable flag derived from risk_score.
- response_profile controls field inclusion.
"""

from __future__ import annotations

import re
from typing import Any

from src.core.models.enums import HazardType


# Map hazard_type string → intermediate model key expectations
_INTERMEDIATE_KEYS: dict[str, set[str]] = {
    "subsidence": {
        "velocity_mm_yr", "abs_rate_mm_yr", "cumulative_mm", "cumulative_m",
        "years_forward", "original_elevation_m", "adjusted_elevation_m",
        "subsidence_source",
    },
    "urban_heat": {
        "baseline_annual_mean_c", "baseline_p95_c", "projected_temp_c",
        "uhi_effect_c", "ensemble_size", "scenario",
    },
    "storm_surge": {
        "cyclone_wind_kts", "pressure_deficit_mb", "base_surge_m",
        "shelf_factor", "total_surge_m", "effective_elevation_m",
        "inundation_depth_m", "subsidence_effect_m",
    },
    "coastal_flood": {
        "raw_elevation_m", "effective_elevation_m", "slr_median_m",
        "tidal_range_m", "total_water_level_m", "inundation_depth_m",
        "scenario", "time_horizon", "is_coastal",
    },
    "riverine_flood": {
        "hand_value_m", "discharge_m3s", "water_level_m",
        "channel_width_m", "manning_n", "flood_depth_m", "flooded",
    },
    "pluvial_flood": {
        "hand_value_m", "slope_degrees", "impervious_fraction",
        "design_rainfall_mm", "susceptibility_index", "estimated_depth_m",
        "runoff_coefficient", "scenario",
    },
    "tropical_cyclone": {
        "return_period_wind_ms", "site_wind_ms", "central_pressure_mb",
        "rmw_km", "saffir_simpson_category", "cyclone_params",
        "max_wind_kts",
    },
}

# Known data source patterns → structured refs
_SOURCE_PATTERN = re.compile(r"^(.+?)\s*\((\w+)\)(?:\s*—\s*(.+))?$")


def _parse_data_source(raw: str) -> dict[str, Any]:
    """Parse a legacy data source string into structured {id, name, version}."""
    m = _SOURCE_PATTERN.match(raw)
    if m:
        name_part = m.group(1).strip()
        source_id = m.group(2).strip()
        # Try to extract version from name
        version = None
        v_match = re.search(r"[vV](\d+[\w.]*)", name_part)
        if v_match:
            version = f"v{v_match.group(1)}"
        return {"id": source_id, "name": name_part, "version": version}
    # Fallback for non-standard strings (e.g. "HAND index (flood susceptibility)")
    return {"id": raw.lower().replace(" ", "_")[:40], "name": raw, "version": None}


def _confidence_to_score(level: str) -> float:
    """Convert categorical confidence to numeric score."""
    mapping = {"low": 0.25, "moderate": 0.50, "high": 0.80}
    return mapping.get(level, 0.25)


def adapt_hazard_result(
    hazard_type: str,
    result_dict: dict[str, Any],
    risk_score: float,
    risk_category: str,
    confidence: str,
    response_profile: str = "standard",
) -> dict[str, Any]:
    """Convert a legacy HazardAssessmentResult dict → v3.0 flat hazard dict.

    Args:
        hazard_type: Internal hazard name (e.g. "riverine_flood").
        result_dict: The raw dict from hazard workflow (has nested
            ``hazard``, ``exposure``, ``intermediate``, etc.).
        risk_score: Normalised 0-1 risk score.
        risk_category: Category label (None / Low / Moderate / High / Extreme).
        confidence: Confidence level string.
        response_profile: Detail level ("summary", "standard", "full_debug").

    Returns:
        A dict matching the shape expected by ``HazardRecord`` subtypes.
    """
    hazard_node = result_dict.get("hazard", {})
    exposure_node = result_dict.get("exposure", {})
    intermediate = result_dict.get("intermediate", {})

    # Strip `city` from intermediate — it belongs to location, not hazard
    intermediate.pop("city", None)

    # Impact — normalize to 0-1
    raw_impact = result_dict.get("impact_score", 0.0)
    impact_score_01 = raw_impact / 100.0 if raw_impact > 1 else raw_impact
    impact_tier = _score_to_tier(impact_score_01)

    # Structured confidence
    confidence_dict = {
        "score": _confidence_to_score(confidence),
        "category": confidence,
    }

    # Structured data sources
    raw_sources = hazard_node.get("data_sources", [])
    data_sources = [_parse_data_source(s) for s in raw_sources]

    # is_applicable: False when risk is zero and intensity is zero
    is_applicable = risk_score > 0

    # Event context — directly from hazard node
    event_ctx = hazard_node.get("event_context", {})

    # Intensity — flatten from legacy nested structure
    intensity = {
        "value": hazard_node.get("intensity_value", 0),
        "unit": hazard_node.get("intensity_unit", "m"),
        "p5": hazard_node.get("intensity_p5", 0),
        "p95": hazard_node.get("intensity_p95", 0),
        "uncertainty_type": hazard_node.get("uncertainty_type", "proxy_model_high_uncertainty"),
    }

    # Resolution
    resolution = {
        "climate_forcing_m": hazard_node.get("climate_forcing_resolution_m", 25000),
        "native_m": hazard_node.get("native_resolution_m", 30),
        "effective_m": hazard_node.get("effective_resolution_m", 30),
        "signal_uniformity": hazard_node.get("climate_signal_uniformity", "grid_cell"),
        "downscaling_method": hazard_node.get("downscaling_method", "terrain_overlay_only"),
    }

    # Lineage
    lineage_raw = hazard_node.get("lineage", {})
    lineage = {
        "source": lineage_raw.get("source", "unknown"),
        "timestamp": lineage_raw.get("timestamp", "2026-01-01T00:00:00Z"),
    }

    # Exposure overrides
    exposure_overrides = {
        "adjustments_applied": exposure_node.get("adjustments_applied", []),
        "urban_context": exposure_node.get("urban_context"),
        "slope_degrees": exposure_node.get("slope_degrees"),
        "coastal_distance_m": exposure_node.get("coastal_distance_m"),
        "coastal_type": exposure_node.get("coastal_type"),
    }

    # Impact result (0-1 normalized)
    impact = {
        "score": round(impact_score_01, 4),
        "tier": impact_tier,
        "status": result_dict.get("status", "unvalidated"),
        "validation_source": (
            result_dict.get("validation", {}).get("validation_source", "unvalidated_baseline")
        ),
    }

    record = {
        "hazard_type": hazard_type,
        "risk_score": risk_score,
        "risk_category": risk_category,
        "confidence": confidence_dict,
        "is_applicable": is_applicable,
        "key_drivers": [],
        "event_context": event_ctx,
        "intensity": intensity,
        "resolution": resolution,
        "data_sources": data_sources,
        "limitations": hazard_node.get("limitations", []),
        "lineage": lineage,
        "exposure_overrides": exposure_overrides,
        "impact": impact,
        "intermediate": intermediate,
        "can_aggregate_with": result_dict.get("can_aggregate_with", []),
        "dependency_order": result_dict.get("dependency_order", 1),
    }

    # Response profile filtering
    if response_profile == "summary":
        for key in ("intermediate", "lineage", "resolution", "limitations",
                     "exposure_overrides", "event_context"):
            record.pop(key, None)
    elif response_profile == "standard":
        # Remove optional debug-only fields from intermediate
        # Note: only strip fields that are Optional on the model
        if isinstance(record.get("intermediate"), dict):
            for raw_key in ("holland_b_parameter",):
                record["intermediate"].pop(raw_key, None)

    return record


def _score_to_tier(score: float) -> str:
    """Map a 0-1 impact score to a tier label."""
    if score <= 0:
        return "None"
    if score >= 0.75:
        return "Critical"
    if score >= 0.50:
        return "High"
    if score >= 0.25:
        return "Moderate"
    return "Low"
