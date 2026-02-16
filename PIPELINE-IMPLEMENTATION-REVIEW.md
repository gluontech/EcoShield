## CRITICAL — Bugs That Will Cause Runtime Errors

### C1. Duplicate class definitions in `composite.py`

**File:** `src/core/models/composite.py:38-101 and 95-149`

`SurfaceAdjustments` is defined twice (lines 38 and 95). `FullRiskProfile` is defined
twice (lines 46 and 103). Python will silently use the **second** definition, but this
is clearly an accidental duplication — possibly a failed merge or paste. The first
definition (lines 38-93) is dead code.

```python
# Lines 38-44 (DEAD — overridden by lines 95-100)
class SurfaceAdjustments(BaseModel):
    ...

# Lines 46-92 (DEAD — overridden by lines 103-149)
class FullRiskProfile(BaseModel):
    ...

# Lines 95-100 (ACTIVE — this is what Python uses)
class SurfaceAdjustments(BaseModel):
    ...

# Lines 103-149 (ACTIVE)
class FullRiskProfile(BaseModel):
    ...
```

**Impact:** No runtime crash today (second definition wins), but any future edit to the
first copy will appear to have no effect — a debugging nightmare.

**Fix:** Delete lines 38-93 (the first definitions of both classes).

---

### C2. Hazard result key mismatch: string keys vs `HazardType` enum keys

**File:** `src/workflows/steps/acute_hazards.py:79` vs `src/tools/structure_risk_tools.py:122-131`

The acute step stores results with **string keys**:
```python
keys = ["storm_surge", "coastal_flood", "riverine_flood", "pluvial_flood", "landslide"]
```

But `structure_risk_tools.py` looks up results with **`HazardType` enum keys**:
```python
if HazardType.PLUVIAL_FLOOD in hazard_results:      # "pluvial_flood" (str) != HazardType.PLUVIAL_FLOOD
if HazardType.STORM_SURGE in hazard_results:         # Same mismatch
```

And `_extract_flood_depth` uses:
```python
for htype in [HazardType.RIVERINE_FLOOD, HazardType.COASTAL_FLOOD, HazardType.STORM_SURGE]:
    if htype in hazard_results:  # Will NEVER match a string key
```

Since `HazardType` is a `str` enum (`class HazardType(str, Enum)`), the `in` check
**does** work in Python (`"storm_surge" == HazardType.STORM_SURGE` is `True` for str
enums), but this is fragile and confusing. More importantly, if `model_config =
{"use_enum_values": True}` is set, Pydantic serialization could surface this mismatch.

**Impact:** Currently works by accident due to Python's `str` enum equality, but is a
latent bug that will surface if anyone uses `is` comparison or non-string enum.

**Fix:** Use `HazardType` enum values as keys in `acute_hazards.py`:
```python
keys = [HazardType.STORM_SURGE, HazardType.COASTAL_FLOOD, ...]
```

---

### C3. `chronic_hazards.py` references `surf._subsidence_applied` (private attr with leading underscore)

**File:** `src/workflows/steps/chronic_hazards.py:103`

```python
if not surf._subsidence_applied:
    surf.apply_subsidence(rate_mm_yr, horizon_years=years)
```

Accessing `_subsidence_applied` (a Pydantic `PrivateAttr`) directly works but violates
encapsulation. The `BuildingAdjustedSurface` class does not expose a public
`subsidence_applied` property (unlike `AdjustedSurface` which has
`subsidenceApplied`).

**Impact:** Works in CPython but is fragile. Pydantic private attrs are not part of the
public API and their access pattern could change.

**Fix:** Add a `@property def subsidence_applied(self) -> bool` to
`BuildingAdjustedSurface` (like `AdjustedSurface.subsidenceApplied`), and use it.

---

## HIGH — Logic Errors Affecting Correctness

### H1. `STANDARD_RETURN_PERIODS` mismatch: docs say 9 RPs, but the code constant has 9 while the previous commit reduced it to 5

**Files:**
- `src/core/models/results.py:90`: `STANDARD_RETURN_PERIODS = [2, 5, 10, 25, 50, 100, 250, 500, 1000]` (9 RPs)
- `docs/ECOSHIELD-ARCHITECTURE-v3_2.md`: Updated to say `[2, 5, 10, 25, 50, 100, 250, 500, 1000]`
- `src/workflows/hazard_workflow.py:89`: Comment says `# [2, 5, 10, 25, 50, 100, 250, 500, 1000]`

The earlier commit (`0e851b0`) changed this from 9 to 5 values `[10, 25, 50, 100, 250]`.
This latest commit restored the 9-RP list. This is now **internally consistent**, but
the original gaps analysis concern remains: running 9 RPs x 5 acute hazards = 45
concurrent tasks per assessment, which may be excessive for MVP.

**Impact:** Functional correctness is fine. Performance concern for production.

**Fix:** No code fix needed. Document the performance trade-off and consider making RP
list configurable per tier (screening vs. detailed).

---

### H2. `coastal_flood` does not vary by return period in acute step

**File:** `src/workflows/steps/acute_hazards.py:55-58`

```python
t_coastal = assess_coastal_flood(
    lat=lat, lon=lon, time_horizon=horizon,
    scenario=scenario, surface=surface, city=city
)
```

The `return_period` parameter (`rp`) is **not passed** to `assess_coastal_flood`. This
means the same coastal flood result is computed identically for every RP in the loop.
The loss-exceedance curve for coastal flood will be flat (same loss at every RP),
making the trapezoidal EAL for coastal flood equal to `loss × 1.0` — a massive
overestimate.

**Impact:** Coastal flood EAL will be wildly inflated because the same SLR-driven flood
depth is treated as occurring at every return period (including 2-year), rather than
being modulated by return period.

**Fix:** Either pass `return_period=rp` to `assess_coastal_flood` so it can modulate
intensity by RP, or exclude coastal flood from the multi-RP loop and treat it as a
chronic/deterministic hazard (which it arguably is — SLR is not a stochastic event).

---

### H3. Composite uncertainty is fabricated: `±20%` of max score

**File:** `src/workflows/steps/composite.py:162-163`

```python
composite_p5=max_score * 0.8,    # Mock uncertainty
composite_p95=min(100.0, max_score * 1.2),
```

The comment says "Mock uncertainty." This fabricates a symmetric ±20% band around the
max score. The individual hazard tools provide real p5/p95 bounds (Gap I), but the
composite step ignores them entirely.

**Impact:** The `CompositeRiskResult.composite_p5` and `composite_p95` fields contain
meaningless values. Any downstream consumer (API, reports, TCFD disclosure) that uses
these as confidence intervals will present false precision.

**Fix:** Propagate individual hazard p5/p95 through the aggregation. For max-aggregation,
`composite_p5 = max(individual_p5_values)` and `composite_p95 =
max(individual_p95_values)` is a reasonable first pass.

---

### H4. `AdjustedSurface.adjusted_elevation_m` ignores SLR

**File:** `src/core/models/surface.py:36-38`

```python
@computed_field
@property
def adjusted_elevation_m(self) -> float:
    """Ground elevation after subsidence."""
    return self.original_elevation_m - self.subsidence_adjustment_m
```

The `adjusted_elevation_m` property subtracts subsidence but ignores
`slr_adjustment_m`. Yet `SurfaceAdjustments` in composite.py stores it as the "final"
adjusted elevation:

```python
adjusted_elevation_m=adj_surface.adjusted_elevation_m if adj_surface else 0.0
```

**Impact:** The reported `adjusted_elevation_m` in `SurfaceAdjustments` will not
reflect SLR. This is misleading because the `getEffectiveFloodDepth` method *does*
account for SLR (line 56), but the stored field does not.

**Fix:** Either rename the property to `subsidence_adjusted_elevation_m` (accurate), or
include SLR: `return self.original_elevation_m - self.subsidence_adjustment_m -
self.slr_adjustment_m`. The latter is semantically wrong though (SLR raises water, not
lowers ground), so renaming is better.

---

## MEDIUM — Inconsistencies and Missing Pieces

### M1. `hazard_weights.yaml` loaded but never used

**File:** `src/config/hazard_weights.yaml` (103 lines)

This well-structured YAML defines per-city acute/chronic hazard weights (e.g., HCMC
riverine_flood: 0.25). But no code in `src/` loads or references this file. The
composite step (`composite.py:133-143`) uses a simple max-aggregation with
`weights[name] = 1.0` for all hazards:

```python
weights[name] = 1.0  # Equal weight / Max logic
```

**Impact:** The weights configuration is dead configuration. The composite score is
max-of-all, not a weighted sum, contradicting both the YAML and the `methodology`
dict in `FullRiskProfile` which says `"acute_aggregation": "Weighted sum within same
return period"`.

**Fix:** Either load and use the YAML weights for weighted aggregation, or remove the
YAML file and update the methodology string to say "Max-aggregation."

---

### M2. `hazard_config` passed into pipeline but never consumed

**File:** `src/workflows/hazard_workflow.py:85,101`

```python
hazard_config = CITY_HAZARDS.get(city, CITY_HAZARDS["hcmc"])
input_data = {
    ...
    "hazard_config": hazard_config,
    ...
}
```

The `hazard_config` includes which hazards are active per city (e.g., Singapore has no
`riverine_flood` or `tropical_cyclone`). But no step reads `data["hazard_config"]` to
filter which hazards to run. The acute step always runs all 5 hazards regardless of
city configuration.

**Impact:** Singapore will get `riverine_flood` and `landslide` assessments (which are
not in its config). The per-building assessments will include irrelevant hazards. This
is wasteful and could produce misleading results for cities like Singapore that
genuinely don't have riverine flood risk.

**Fix:** In `acute_hazards.py`, read `data["hazard_config"]["acute"]` and only dispatch
tasks for hazards in the city's active list. Same for `chronic_hazards.py` with
`data["hazard_config"]["chronic"]`.

---

### M3. Missing `portfolio_workflow.py`

**Files:**
- `docs/ECOSHIELD-ARCHITECTURE-v3_2.md` lists `src/workflows/portfolio_workflow.py`
- `docs/ECOSHIELD-PHASE4-WORKFLOW-v3_2.md` lists it in "Files Created"
- **The file does not exist.**

The portfolio workflow (batch processing multiple sites with EAL aggregation) is
referenced in architecture docs but was not created.

**Fix:** Create a stub or remove from docs to avoid confusion.

---

### M4. `reproduce_eal.py` is a debug script committed to repo root

**File:** `reproduce_eal.py` (13 lines)

This is a manual reproduction script with no test structure:
```python
if __name__ == "__main__":
    run()
```

**Impact:** Clutters the repo root. Not harmful but unprofessional.

**Fix:** Move to `tests/` or `scripts/`, or delete if the EAL test in
`test_models.py:140-159` covers the same case.

---

### M5. `InSARVelocityResult.num_observations` restored to `ge=1` but previous commit had `ge=0`

**File:** `src/core/models/elevation.py:140-143`

The latest commit restored `num_observations: int = Field(..., ge=1)`, which is
correct — zero observations is physically meaningless. The previous commit's `ge=0`
was flagged in the first review. This is now **fixed**.

---

### M6. `chronic_hazards.py` hardcodes `horizon - 2024` as "years from now"

**File:** `src/workflows/steps/chronic_hazards.py:99`

```python
years = max(0, horizon - 2024)
```

This will be wrong in 2025. The current year should be computed dynamically.

**Fix:** `years = max(0, horizon - datetime.now().year)`

---

## Summary Table

| ID | Severity | File | Issue |
|----|----------|------|-------|
| **C1** | CRITICAL | `composite.py` | Duplicate `SurfaceAdjustments` + `FullRiskProfile` class definitions |
| **C2** | CRITICAL | `acute_hazards.py` / `structure_risk_tools.py` | String vs `HazardType` enum key mismatch (works by accident) |
| **C3** | CRITICAL | `chronic_hazards.py` | Accesses `_subsidence_applied` private attr directly |
| **H1** | HIGH | `results.py` / docs | 9 RPs restored — internally consistent now, performance TBD |
| **H2** | HIGH | `acute_hazards.py` | `coastal_flood` ignores return period — EAL will be inflated |
| **H3** | HIGH | `composite.py` | Composite p5/p95 uncertainty is fabricated (±20%), ignores real bounds |
| **H4** | HIGH | `surface.py` | `adjusted_elevation_m` ignores SLR component |
| **M1** | MEDIUM | `hazard_weights.yaml` / `composite.py` | Weights YAML defined but never loaded; composite uses max not weighted sum |
| **M2** | MEDIUM | `hazard_workflow.py` / all steps | `hazard_config` per-city filtering never applied |
| **M3** | MEDIUM | docs | `portfolio_workflow.py` referenced but doesn't exist |
| **M4** | MEDIUM | `reproduce_eal.py` | Debug script in repo root |
| **M5** | INFO | `elevation.py` | `num_observations ge=1` restored (fixed) |
| **M6** | MEDIUM | `chronic_hazards.py` | `horizon - 2024` hardcoded year |


