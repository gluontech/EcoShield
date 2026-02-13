## **Gaps Analysis Report**

### **1. High-Level Systemic Issues**

#### **1.1 Hazard Count Inconsistency** (⚠️ Credibility Issue)

* 
**Problem**: There is a discrepancy across documentation; the Architecture doc lists 8 hazards (including pluvial), while Phase 1 models assume 7, and Phase 2 data has pluvial inputs that aren't fully integrated.

* 
**Risk**: This signals drifting scope and weak requirements control, posing a red flag for technical due diligence.

* **Fix**:
* Declare an authoritative registry (coastal flood, riverine flood, pluvial flood, storm surge, subsidence, landslide, tropical cyclone, urban heat).

* Implement CI checks to ensure every hazard has a corresponding tool, model description, data source, and validation metric.

#### **1.2 “Structure-Level” Claim vs. Climate Forcing Reality** (⚠️ Methodological Risk)

* 
**Problem**: While climate forcing is disclosed at 25 km with uniform deltas, downstream reports visually imply building-specific projections, leading to potential misinterpretation of precision.

* 
**Risk**: Legal and ESG risk; regulators and insurers are highly sensitive to "false precision".

* **Fix**:
* Add mandatory output fields: `climate_signal_uniformity: "grid_cell"` and `downscaling_method: "terrain_overlay_only"`.

* Label the frontend clearly: “Climate signal uniform within 25 km cell; building differentiation from terrain & exposure only”.

---

### **2. Architecture Document (v3.2)**

#### **2.1 Missing Model Validation Layer**

* 
**Problem**: The system validates data integrity but lacks model correctness checks like backtesting, skill scores, or observed vs. modeled comparisons.

* 
**Risk**: Without validation, the system functions as an analysis engine rather than a true risk model.

* 
**Fix**: Add a validation workflow (e.g., comparing flood depths to historical marks or LST vs. ERA5-Land air temp) and expose metrics like `rmse`, `bias`, and `data_coverage_pct`.

#### **2.2 Composite Risk Agent Is Underspecified**

* 
**Problem**: The portfolio-level composite agent lacks correlation handling, hazard dependency logic, and compounding event logic (e.g., cyclone → surge → flood).
* 
**Risk**: This breaks use cases for institutional clients like banks and insurers.
* 
**Fix**: Define independence assumptions, optional correlation matrices, and event chaining graphs.

#### **2.3 Agno + LLM Role Confusion**

* 
**Problem**: Agents are described as "reasoning," yet most outputs are actually deterministic.
* 
**Risk**: LLMs introduce audit opacity if they are not tightly scoped.
* 
**Fix**: Restrict LLMs to synthesis and narration; strictly ban LLM involvement in numeric computation, hazard intensity, or damage calculation.
---

### **3. Phase 1 Models Document**

#### **3.1 Flood Depth Method Over-Simplified**

* 
**Problem**: The Manning-based approach assumes uniform channel geometry and lacks urban drainage interaction.
* 
**Risk**: Urban flooding in Southeast Asia is often dominated by compound factors and drainage failure.
* 
**Fix**: Classify outputs as “screening-level hydraulic approximation” and define an upgrade path for 2D models like LISFLOOD-FP.



#### **3.2 Landslide Model Lacks Triggering Dynamics**
* 
**Problem**: The current model measures susceptibility, not annual hazard probability, and misses rainfall/moisture triggers.

* 
**Risk**: Users may incorrectly interpret the index as an annual probability.
* 
**Fix**: Rename output to “Landslide Susceptibility Index (LSI)” and add conditional probability based on extreme rainfall.


#### **3.3 Cyclone Model Omits Duration & Gust Factors**

* 
**Problem**: The model includes the Holland wind profile but misses gust factors and duration above damage thresholds.
* 
**Risk**: Structural damage is not determined by peak wind speed alone.
* 
**Fix**: Add a gust multiplier (1.3–1.5) and duration bins for sustained wind speeds.

---

### **4. Phase 2 Data Document**

#### **4.1 Google Open Buildings Height Accuracy Risk**

* 
**Problem**: 2.5D height inference has a ±1–2 story uncertainty with no surfaced confidence score.
* 
**Risk**: Height errors cascade into wind exposure, flood depth, and replacement value calculations.
* 
**Fix**: Propagate `height_confidence` and inflate vulnerability uncertainty when confidence is low.


#### **4.2 InSAR Subsidence Coverage Gaps**

* 
**Problem**: Sentinel-1 data suffers from temporal gaps and decorrelation in urban or vegetated coastal areas.
* 
**Risk**: Errors in slow, cumulative subsidence compound over decades.
* 
**Fix**: Add a `subsidence_data_source` flag (InSAR vs. literature/interpolated) and increase uncertainty for fallbacks.


#### **4.3 No Data Lineage or Timestamping**

* 
**Problem**: Outputs lack acquisition dates, processing dates, and versioning.
* 
**Risk**: Issues with auditability, ESG reporting, and ISO alignment.
* 
**Fix**: Include a `data_lineage` block in every output object containing source, version, and retrieval/processing dates.

