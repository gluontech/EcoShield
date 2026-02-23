# EcoShield Forensic Technical Review

## Assessment of Request vs Response Integrity

This document analyzes the provided assessment request and response JSON
files and identifies: - Numerical impossibilities - Logical
inconsistencies - Schema mismatches - Model credibility risks - Required
remediation actions

------------------------------------------------------------------------

# CRITICAL NUMERICAL ERRORS

## 1. Tropical Cyclone Wind Speed Physically Impossible

Response contains:

-   intensity_value: 68,682,566.8 m/s
-   max_wind_kts: 133,519,764

These values exceed physical limits by several orders of magnitude.

### Required Fix

Recalibrate wind speed calculation. Implement physical guardrails:

-   Hard cap wind speed ≤ 120 m/s
-   Raise exception if exceeded
-   Validate extreme value distribution fit before propagation

------------------------------------------------------------------------

## 2. Storm Surge Depth = 667,582 meters

Response contains:

-   intensity_value: 667,582.41 m

This equals a 667 km storm surge, which is physically impossible.

Root cause: Surge model consumed corrupted wind input.

### Required Fix

-   Double check storm surge depth data source and calculation   
-   Cap surge ≤ 20 m
-   Add validation step between cyclone → surge
-   Reject corrupted upstream hazard values

------------------------------------------------------------------------

## 4. Hazard Mapping Inconsistency

Request hazards include: - flood - heat - cyclone - surge - wind

Response expands or renames hazards inconsistently: - flood →
coastal_flood + riverine_flood - heat → urban_heat - wind + cyclone →
tropical_cyclone

Additionally, landslide requested but missing in response.

### Required Fix

Introduce canonical hazard mapping layer and return mapping metadata.

------------------------------------------------------------------------

# MODELING WEAKNESSES

## 5. Urban Heat Shows No Climate Signal

-   temperature_change_c = 0
-   heat_wave_days_change = 0
-   ensemble_size = 1

Under SSP245, zero warming is not credible.

### Required Fix

-   Use ≥ 5 GCM ensemble
-   Apply delta method
-   Enforce non-zero warming under SSP scenarios

------------------------------------------------------------------------

## 6. Subsidence Projection Oversimplified

-   Linear projection only
-   No uncertainty propagation
-   No policy or nonlinear compaction consideration

### Required Fix

Include P5/P95 projection bounds and scenario variability.

------------------------------------------------------------------------

## 7. Coastal Flood Confidence Overstated

Model uses bathtub approach but confidence labeled "high".

### Required Fix

Downgrade confidence or implement rubric-based scoring.

------------------------------------------------------------------------

## 8. Riverine Flood Zero Depth in HCMC

10-year return period yields zero flood depth despite subsidence.

### Required Fix

Validate against historical flood extents and recalibrate HAND
thresholds.

------------------------------------------------------------------------

# FINANCIAL OUTPUT FAILURE

## 9. portfolio_eal_usd = 0 Despite Extreme Hazards

Extreme cyclone and surge risk but no loss computed.

Cause: - replacement_value_usd = null - vulnerability = null

### Required Fix

If loss inputs missing: - Mark EAL as "not_computed" - Or estimate
replacement value - Never return zero silently

------------------------------------------------------------------------

# EXPOSURE DATA FAILURE

## 10. Building Mismatch

Asset: Eastin Grand Hotel Saigon\
Returned structure: - 89 m² - 2 stories - residential_single

Clearly not a hotel.

Likely incorrect footprint match.

### Required Fix

-   Validate footprint intersects lat/lon
-   Reject low-confidence building matches
-   Cross-check occupancy classification

------------------------------------------------------------------------

# PIPELINE VALIDATION GAPS

## 11. Missing Lineage and Validation Fields

Many hazards have: - lineage: null - validation: null

Unacceptable for insurer-grade output.

------------------------------------------------------------------------

## 12. Dependency Validation Missing

Storm surge consumed corrupted cyclone output without sanity checks.

Required pipeline:

Cyclone validated → Surge computed → Flood derived

------------------------------------------------------------------------

# AGGREGATION PROBLEM

## 13. overall_risk_score Opaque

Two hazards are Extreme, yet composite score = 0.455.

No explanation of weighting or normalization.

### Required Fix

Return: - hazard_weights - aggregation_method - normalization_method

------------------------------------------------------------------------

# PRIORITY REMEDIATION ROADMAP

1.  Implement physical guardrails for all hazards.
2.  Enforce strict request/response schema consistency.
3.  Add exposure validation layer.
4.  Fix cyclone extreme value overflow.
5.  Prevent silent EAL=0.
6.  Implement pre-response sanity-check filter.


