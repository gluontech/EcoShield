# src/tools/structure_risk_tools.py
"""
Structure-level risk assessment using HxExV framework.

Physics: For each building, compute:
  H (Hazard):       Flood depth / wind speed / surge height at building
  E (Exposure):     Footprint, height, ground elevation, ground floor height
  V (Vulnerability): JRC depth-damage curve for building's material class

v3.2 Changes:
  - Gap Q: Multi-RP EAL via trapezoidal integration
  - Gap S: BuildingAdjustedSurface for per-building elevation/subsidence/SLR
  - Gap T: OCCUPANCY_VALUE_MULTIPLIER scales JRC replacement values
  - Gap M: Pluvial flood damage added to per-building assessment
"""

import logging
from typing import List, Optional

from src.core.models import (
    Location, HazardType, RiskTier, VulnerabilityClass,
    StructuralCharacteristics, BuildingCluster,
    StructureRiskResult, PortfolioRiskSummary,
    ReturnPeriodLoss, STANDARD_RETURN_PERIODS,
    compute_eal_trapezoidal,
    BuildingAdjustedSurface,
    OCCUPANCY_VALUE_MULTIPLIER,
    ConfidenceLevel,
)
from src.data.jrc_vulnerability import JRCVulnerabilitySource

logger = logging.getLogger(__name__)

jrc = JRCVulnerabilitySource()


async def assess_structure_risk(
    buildings: BuildingCluster,
    hazard_results_by_rp: dict,
    building_surfaces: Optional[dict] = None,
    country: str = "VN",
) -> List[StructureRiskResult]:
    """
    Apply HxExV to each building in a BuildingCluster with multi-RP EAL.

    Args:
        buildings: BuildingCluster from Step 0 (asset fetch)
        hazard_results_by_rp: Dict of {return_period: {HazardType: HazardAssessmentResult}}
            If flat dict passed (v3.1 compat), wraps as {100: flat_dict}.
        building_surfaces: Dict of {building_id: BuildingAdjustedSurface} (Gap S)
        country: ISO country code for JRC max-damage lookup

    Returns:
        List of StructureRiskResult, one per building, with multi-RP EAL
    """
    # v3.2: Handle backward compatibility
    if hazard_results_by_rp and not isinstance(next(iter(hazard_results_by_rp.keys())), int):
        hazard_results_by_rp = {100: hazard_results_by_rp}

    results = []

    for structure in buildings.buildings:
        bid = structure.footprint.building_id

        # Per-building surface (Gap S)
        bldg_surface = (building_surfaces or {}).get(bid)
        subsidence_source = "none"
        subsidence_rate = 0.0
        subsidence_cumulative = 0.0
        if bldg_surface:
            subsidence_source = bldg_surface.subsidence_source
            subsidence_rate = bldg_surface.subsidence_rate_mm_yr
            subsidence_cumulative = bldg_surface.subsidence_cumulative_m

        # Replacement value with occupancy multiplier (Gap T)
        occupancy = getattr(structure, "occupancy", None)
        multiplier = OCCUPANCY_VALUE_MULTIPLIER.get(occupancy, 1.0) if occupancy else 1.0

        if structure.replacement_value_usd:
            replacement = structure.replacement_value_usd * multiplier
            replacement_source = "user_provided"
        else:
            area_m2 = getattr(structure.footprint, "area_m2", 100.0)
            replacement = jrc.get_replacement_value_usd(
                country=country.lower(),
                area_m2=area_m2,
                occupancy_multiplier=multiplier,
            )
            replacement_source = f"jrc_country_estimate x {multiplier:.1f}"

        # Multi-RP loss-exceedance curve (Gap Q)
        rp_losses: List[ReturnPeriodLoss] = []

        # Track primary RP (100yr) for backward-compatible fields
        primary_flood_depth = 0.0
        primary_flood_damage = 0.0
        primary_surge_depth = 0.0
        primary_surge_damage = 0.0
        primary_pluvial_depth = 0.0
        primary_pluvial_damage = 0.0
        primary_wind_damage = 0.0
        primary_wind_speed = 0.0

        for rp in sorted(hazard_results_by_rp.keys()):
            hazard_results = hazard_results_by_rp[rp]

            # Flood depth at building
            flood_depth_field = _extract_flood_depth(hazard_results)
            
            # Hazard tools return depth ABOVE GROUND.
            # We compare vs ground floor height above ground.
            threshold_m = structure.ground_floor_height_m
            if structure.has_stilts:
                threshold_m += 1.5

            flood_depth_at_bldg = max(
                0.0, (flood_depth_field or 0.0) - threshold_m
            )

            # Pluvial flood depth (Gap M)
            pluvial_depth_at_bldg = 0.0
            if HazardType.PLUVIAL_FLOOD in hazard_results:
                pluvial_result = hazard_results[HazardType.PLUVIAL_FLOOD]
                pluvial_depth_at_bldg = max(
                    0.0, pluvial_result.hazard.intensity_value - threshold_m
                )

            # Surge depth
            surge_depth_at_bldg = 0.0
            if HazardType.STORM_SURGE in hazard_results:
                surge_result = hazard_results[HazardType.STORM_SURGE]
                surge_depth_at_bldg = max(
                    0.0, surge_result.hazard.intensity_value - threshold_m
                )

            # Max flood depth across all flood-like hazards
            max_flood_depth = max(flood_depth_at_bldg, pluvial_depth_at_bldg,
                                  surge_depth_at_bldg)

            # Flood damage ratio from JRC curve
            vuln_class = getattr(structure, "vulnerability_class",
                                 VulnerabilityClass.CLASS_III_MASONRY)
            flood_damage_ratio = jrc.get_flood_damage_ratio(
                vulnerability_class=vuln_class,
                flood_depth_m=max_flood_depth,
            )

            # Wind damage ratio
            wind_speed_ms = _extract_wind_speed_ms(hazard_results)
            wind_damage_ratio = jrc.get_wind_damage_ratio(
                vulnerability_class=vuln_class,
                wind_speed_ms=wind_speed_ms or 0.0,
            )

            # Max damage for this RP
            max_damage_ratio = max(flood_damage_ratio, wind_damage_ratio)

            rp_losses.append(ReturnPeriodLoss(
                return_period_years=rp,
                exceedance_probability=1.0 / rp,
                damage_ratio=max_damage_ratio,
                loss_usd=max_damage_ratio * replacement,
                hazard_intensity=(
                    max_flood_depth
                    if flood_damage_ratio >= wind_damage_ratio
                    else (wind_speed_ms or 0.0)
                ),
                hazard_intensity_unit=(
                    "m" if flood_damage_ratio >= wind_damage_ratio else "m/s"
                ),
            ))

            # Track primary RP (100yr) for backward-compat fields
            if rp == 100 or (
                rp == max(hazard_results_by_rp.keys())
                and 100 not in hazard_results_by_rp
            ):
                primary_flood_depth = flood_depth_at_bldg
                primary_flood_damage = jrc.get_flood_damage_ratio(
                    vulnerability_class=vuln_class,
                    flood_depth_m=flood_depth_at_bldg,
                )
                primary_surge_depth = surge_depth_at_bldg
                primary_surge_damage = jrc.get_flood_damage_ratio(
                    vulnerability_class=vuln_class,
                    flood_depth_m=surge_depth_at_bldg,
                )
                primary_pluvial_depth = pluvial_depth_at_bldg
                primary_pluvial_damage = jrc.get_flood_damage_ratio(
                    vulnerability_class=vuln_class,
                    flood_depth_m=pluvial_depth_at_bldg,
                )
                primary_wind_damage = wind_damage_ratio
                primary_wind_speed = wind_speed_ms or 0.0

        # EAL via trapezoidal integration (Gap Q)
        eal_usd = (
            compute_eal_trapezoidal(rp_losses)
            if len(rp_losses) >= 2 else None
        )

        # PML at 250-year (v3.2: was 100-year)
        pml_loss = next(
            (loss for loss in rp_losses if loss.return_period_years == 250),
            next(
                (loss for loss in sorted(rp_losses, key=lambda x: -x.return_period_years)),
                None,
            ),
        )
        pml_usd = pml_loss.loss_usd if pml_loss else 0.0

        # Composite risk score
        max_damage = max((loss.damage_ratio for loss in rp_losses), default=0.0)
        risk_score = max_damage * 100.0

        # Dominant hazard
        dominant = _determine_dominant_hazard(
            primary_flood_damage, primary_surge_damage,
            primary_pluvial_damage, primary_wind_damage,
        )

        results.append(StructureRiskResult(
            building_id=bid,
            latitude=structure.footprint.centroid.lat,
            longitude=structure.footprint.centroid.lon,
            footprint_area_m2=getattr(structure.footprint, "area_m2", None),
            height_m=getattr(structure, "height_m", None),
            num_stories=getattr(structure, "num_stories", None) or 1,
            vulnerability_class=vuln_class,
            ground_floor_elevation_m=structure.effective_ground_floor_m,
            replacement_value_usd=round(replacement, 0),
            replacement_value_source=replacement_source,
            flood_damage_ratio=round(primary_flood_damage, 4),
            flood_depth_at_building_m=round(primary_flood_depth, 2),
            surge_damage_ratio=round(primary_surge_damage, 4),
            surge_depth_at_building_m=round(primary_surge_depth, 2),
            pluvial_flood_damage_ratio=round(primary_pluvial_damage, 4),
            pluvial_depth_at_building_m=round(primary_pluvial_depth, 2),
            wind_damage_ratio=round(primary_wind_damage, 4),
            max_wind_speed_ms=round(primary_wind_speed, 1),
            subsidence_mm_per_year=round(subsidence_rate, 1),
            subsidence_cumulative_m=round(subsidence_cumulative, 3),
            subsidence_source=subsidence_source,
            losses_by_return_period=rp_losses,
            max_damage_ratio=round(max_damage, 4),
            combined_risk_score=round(risk_score, 1),
            risk_tier=_score_to_tier(risk_score),
            dominant_hazard=dominant,
            expected_annual_loss_usd=round(eal_usd, 2) if eal_usd is not None else None,
            probable_maximum_loss_usd=round(pml_usd, 2),
            data_sources=[
                "JRC Flood Depth-Damage (Huizinga 2017)",
                "Google Open Buildings + Overture Maps",
                f"Multi-RP EAL: {len(rp_losses)} return periods",
            ],
            limitations=[
                "JRC curves are residential-baseline" + (
                    f" (occupancy multiplier {multiplier:.1f}x applied)"
                    if multiplier != 1.0 else ""
                ),
                f"Subsidence source: {subsidence_source}",
            ],
        ))

    return results


def summarize_portfolio(
    structure_results: List[StructureRiskResult],
    portfolio_id: str,
    city: str,
) -> PortfolioRiskSummary:
    """Aggregate per-building results into portfolio-level stats."""
    n = len(structure_results)
    # Portfolio PML: sum of per-building 250yr PML losses
    pml_250yr = sum(
        next(
            (loss.loss_usd for loss in r.losses_by_return_period if loss.return_period_years == 250),
            r.probable_maximum_loss_usd or 0
        )
        for r in structure_results
    ) if structure_results else None
    return PortfolioRiskSummary(
        portfolio_id=portfolio_id,
        city=city,
        total_buildings=n,
        buildings_critical=sum(
            1 for r in structure_results if r.risk_tier == RiskTier.CRITICAL
        ),
        buildings_high=sum(
            1 for r in structure_results if r.risk_tier == RiskTier.HIGH
        ),
        buildings_moderate=sum(
            1 for r in structure_results if r.risk_tier == RiskTier.MODERATE
        ),
        buildings_low=sum(
            1 for r in structure_results if r.risk_tier == RiskTier.LOW
        ),
        total_replacement_value_usd=sum(
            r.replacement_value_usd or 0 for r in structure_results
        ),
        total_expected_annual_loss_usd=sum(
            r.expected_annual_loss_usd or 0 for r in structure_results
        ),
        mean_damage_ratio=round(
            sum(r.max_damage_ratio for r in structure_results) / max(n, 1), 4
        ),
        pml_250yr_usd=round(pml_250yr, 2) if pml_250yr else None,
    )


# -- Private helpers --

def _extract_flood_depth(hazard_results: dict) -> Optional[float]:
    """Get maximum flood water level from any flood hazard result."""
    for htype in [HazardType.RIVERINE_FLOOD, HazardType.COASTAL_FLOOD,
                  HazardType.STORM_SURGE]:
        if htype in hazard_results:
            return hazard_results[htype].hazard.intensity_value
    return None


def _extract_wind_speed_ms(hazard_results: dict) -> Optional[float]:
    """Get wind speed from cyclone result (m/s)."""
    if HazardType.TROPICAL_CYCLONE in hazard_results:
        return hazard_results[HazardType.TROPICAL_CYCLONE].hazard.intensity_value
    return None


def _determine_dominant_hazard(
    flood_dr: float, surge_dr: float, pluvial_dr: float, wind_dr: float,
) -> Optional[HazardType]:
    """Determine which hazard contributes most damage."""
    damages = {
        HazardType.RIVERINE_FLOOD: flood_dr,
        HazardType.STORM_SURGE: surge_dr,
        HazardType.PLUVIAL_FLOOD: pluvial_dr,
        HazardType.TROPICAL_CYCLONE: wind_dr,
    }
    max_hazard = max(damages, key=damages.get)
    return max_hazard if damages[max_hazard] > 0 else None


def _score_to_tier(score: float) -> RiskTier:
    if score >= 75:
        return RiskTier.CRITICAL
    elif score >= 50:
        return RiskTier.HIGH
    elif score >= 25:
        return RiskTier.MODERATE
    return RiskTier.LOW
