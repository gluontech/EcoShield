# src/data/ipcc_slr.py
"""
IPCC AR6 Regional Sea Level Rise Projections.

NEW v3.2 (Gap K): DataSource.IPCC_AR6 was declared in enums and referenced
in coastal flood mapping, but no data module existed. SLR values had no
ingestion, caching, or query interface.

This module provides hardcoded IPCC AR6 regional SLR projections for SEA
target cities at 2050 and 2100 under each SSP scenario.

Source: IPCC AR6 WGI Chapter 9, Table 9.9 + Fox-Kemper et al. (2021)
        Regional values from IPCC AR6 Sea Level Projection Tool:
        https://sealevel.nasa.gov/ipcc-ar6-sea-level-projection-tool

Values are median projections relative to 1995-2014 baseline (m).
"""

from typing import Dict, Optional, Tuple
from pydantic import BaseModel, Field


# --- IPCC AR6 Regional SLR Projections (meters above 1995-2014 baseline) ---
# Format: {city: {scenario: {year: (median, p5, p95)}}}
IPCC_AR6_SLR_M: Dict[str, Dict[str, Dict[int, Tuple[float, float, float]]]] = {
    "ho_chi_minh_city": {
        "ssp126": {2050: (0.20, 0.13, 0.29), 2100: (0.44, 0.28, 0.66)},
        "ssp245": {2050: (0.22, 0.15, 0.31), 2100: (0.56, 0.37, 0.83)},
        "ssp370": {2050: (0.23, 0.15, 0.32), 2100: (0.68, 0.44, 1.01)},
        "ssp585": {2050: (0.24, 0.16, 0.34), 2100: (0.83, 0.53, 1.22)},
    },
    "jakarta": {
        "ssp126": {2050: (0.19, 0.12, 0.28), 2100: (0.42, 0.26, 0.63)},
        "ssp245": {2050: (0.21, 0.14, 0.30), 2100: (0.54, 0.35, 0.80)},
        "ssp370": {2050: (0.22, 0.14, 0.31), 2100: (0.66, 0.42, 0.98)},
        "ssp585": {2050: (0.23, 0.15, 0.33), 2100: (0.80, 0.51, 1.19)},
    },
    "manila": {
        "ssp126": {2050: (0.21, 0.14, 0.30), 2100: (0.46, 0.30, 0.68)},
        "ssp245": {2050: (0.23, 0.16, 0.32), 2100: (0.58, 0.39, 0.85)},
        "ssp370": {2050: (0.24, 0.16, 0.33), 2100: (0.70, 0.46, 1.04)},
        "ssp585": {2050: (0.25, 0.17, 0.35), 2100: (0.85, 0.55, 1.26)},
    },
    "bangkok": {
        "ssp126": {2050: (0.18, 0.11, 0.27), 2100: (0.40, 0.25, 0.61)},
        "ssp245": {2050: (0.20, 0.13, 0.29), 2100: (0.52, 0.34, 0.78)},
        "ssp370": {2050: (0.21, 0.13, 0.30), 2100: (0.64, 0.41, 0.96)},
        "ssp585": {2050: (0.22, 0.14, 0.32), 2100: (0.78, 0.50, 1.17)},
    },
    "hanoi": {  # Coastal proxy — Hanoi is inland but serves as HCMC companion
        "ssp126": {2050: (0.18, 0.11, 0.27), 2100: (0.40, 0.25, 0.61)},
        "ssp245": {2050: (0.20, 0.13, 0.29), 2100: (0.52, 0.34, 0.78)},
        "ssp370": {2050: (0.21, 0.13, 0.30), 2100: (0.64, 0.41, 0.96)},
        "ssp585": {2050: (0.22, 0.14, 0.32), 2100: (0.78, 0.50, 1.17)},
    },
    "singapore": {
        "ssp126": {2050: (0.19, 0.12, 0.28), 2100: (0.43, 0.27, 0.64)},
        "ssp245": {2050: (0.21, 0.14, 0.30), 2100: (0.55, 0.36, 0.81)},
        "ssp370": {2050: (0.22, 0.14, 0.31), 2100: (0.67, 0.43, 0.99)},
        "ssp585": {2050: (0.23, 0.15, 0.33), 2100: (0.81, 0.52, 1.20)},
    },
}


class SLRProjection(BaseModel):
    """Sea level rise projection for a city/scenario/year."""
    city: str
    scenario: str
    target_year: int
    slr_median_m: float = Field(..., description="Median SLR (m above 1995-2014)")
    slr_p5_m: float = Field(..., description="5th percentile (low estimate)")
    slr_p95_m: float = Field(..., description="95th percentile (high estimate)")
    baseline_period: str = Field(default="1995-2014")
    source: str = Field(default="IPCC AR6 WGI Ch.9 (Fox-Kemper et al. 2021)")


def get_slr_projection(
    city: str,
    scenario: str = "ssp245",
    target_year: int = 2050,
) -> SLRProjection:
    """
    Get IPCC AR6 SLR projection for a SEA city.
    
    Args:
        city: City name (e.g., "ho_chi_minh_city", "jakarta")
        scenario: SSP scenario (ssp126, ssp245, ssp370, ssp585)
        target_year: 2050 or 2100
    
    Returns:
        SLRProjection with median and uncertainty bounds
    """
    city_data = IPCC_AR6_SLR_M.get(city)
    if not city_data:
        raise ValueError(
            f"No SLR data for {city}. Available: {list(IPCC_AR6_SLR_M.keys())}"
        )
    
    scenario_data = city_data.get(scenario)
    if not scenario_data:
        raise ValueError(f"No SLR data for scenario {scenario}")
    
    year_data = scenario_data.get(target_year)
    if not year_data:
        # Interpolate between 2050 and 2100
        if 2050 < target_year < 2100:
            d50 = scenario_data[2050]
            d100 = scenario_data[2100]
            frac = (target_year - 2050) / 50.0
            year_data = tuple(
                d50[i] + frac * (d100[i] - d50[i]) for i in range(3)
            )
        else:
            raise ValueError(f"No SLR data for year {target_year}")
    
    return SLRProjection(
        city=city,
        scenario=scenario,
        target_year=target_year,
        slr_median_m=float(year_data[0]),
        slr_p5_m=float(year_data[1]),
        slr_p95_m=float(year_data[2]),
    )
