# EcoShield Architecture v3.2

## Executive Summary

**EcoShield** is a **structure-level** climate risk intelligence Web SaaS platform for Southeast Asia. The platform delivers engineering-based climate risk analysis focused on **physical asset vulnerability and hazard exposure** at the individual building level. It models **8 hazards** specific to SEA cities — coastal, riverine, and **pluvial** flooding, subsidence, landslides, tropical cyclones, storm surge, and urban heat — using **Agno Workflows** for deterministic orchestration. MVP targets: **Ho Chi Minh City, Hanoi, Da Nang** (Vietnam).

> **Resolution Transparency (v3.2):** Climate forcing comes from NEX-GDDP-CMIP6 at **0.25° (~25 km)**. Building-level differentiation within each 625 km² climate grid cell is achieved by overlaying terrain data (GLO-30 DEM at 30 m, HAND at 30 m, Landsat LST at 30 m) onto sub-meter building footprints. Climate projections (temperature change, precipitation change) are **uniform** within each grid cell. Every `HazardIntensity` output now carries a `climate_forcing_resolution_m` field for downstream consumers to assess granularity.

### v3.2 — Structure-Level Asset Risk (H×E×V per Building) + Gap Fixes

v3.2 extends v3.1 with **critical methodological and code fixes** identified via cross-analysis:

- **Multi-return-period EAL integration** — EAL is now computed via trapezoidal integration over the full loss-exceedance curve (RPs 2, 5, 10, 25, 50, 100, 250, 500, 1000), not a single scenario loss. (Gap Q)
- **Discharge → depth conversion** — Manning's equation rating curve converts GloFAS discharge (m³/s) to water level (m) for riverine flood depth calculation. (Gap J)
- **Real ensemble uncertainty** — Multi-model spread from 5 GCMs replaces fabricated `change × 0.7/1.3` bounds. (Gap I)
- **Pluvial flood model** — Surface water flooding from intense rainfall, the most frequent flood type in SEA cities, is now modeled. (Gap M)
- **Holland (2008) wind profile** — Parametric cyclone wind field specified and implemented. (Gap P)
- **IPCC AR6 SLR module** — Regional sea-level rise projections now ingested for coastal flood mapping. (Gap K)
- **Published subsidence rates** — MVP uses peer-reviewed rates (Minderhoud 2018, Chaussard 2013) as InSAR fallback. (Gap L)
- **Data quality validation layer** — All ingested data passes NaN/range/void checks before entering models. (Gap R)
- **Occupancy-based replacement values** — Commercial, industrial, institutional buildings use appropriate multipliers. (Gap T)
- **Per-building surface adjustment** — Each building gets its own elevation/subsidence/SLR context. (Gap S)
- **Code bug fixes** — Location field names (Gap N), BoundingBox.area_degrees (Gap O), scheduler completeness (Gap U).

The core output is **H×E×V per building**: Hazard intensity × Exposure (building footprint, height, elevation) × Vulnerability (material-based damage curves) = damage ratio and expected annual loss per structure.

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Orchestration** | Agno Workflows | Deterministic execution, dependency ordering, parallel hazards |
| **Agent Pattern** | Team + Specialized Agents | ClimateTeam coordinates ClimateAgent + HazardAgents |
| **API Version** | `/v1/` | Clean start, no legacy conflicts |
| **Tool Naming** | `{hazard}_tools.py` | Consistent: `riverine_flood_tools.py` |
| **Function Naming** | `assess_{hazard}()` | Consistent: `assess_riverine_flood()` |
| **Return Types** | Pydantic Models Only | All tools return validated Pydantic models |
| **LLM Provider** | DeepSeek Chat | Cost-effective, sufficient capability |
| **Data Strategy** | API-first ingestion → local cache | All external data via public APIs → PostGIS/S3 |
| **Climate Projections** | NASA NEX-GDDP-CMIP6 | Replaces CMIP6-VN: global coverage, 4 API access methods |
| **DEM Source** | Copernicus GLO-30 | Replaces FABDEM: open API via AWS S3 OpenData |
| **Reanalysis** | ERA5-Land via CDS API | WBGT, wind, humidity for heat stress |
| **River Discharge** | GloFAS v4 via CDS API | Calibrated return-period floods |
| **Soil Data** | ISRIC SoilGrids v2 REST | Clay/sand for landslide susceptibility |
| **Vegetation** | Sentinel-2 L2A via STAC | NDVI for landslide vegetation stability |
| **Bathymetry** | GEBCO 2024 via BODC API | Storm surge shelf amplification |
| **Cyclone Tracks** | IBTrACS v04r01 via NCEI | Historical tropical cyclone best tracks |
| **Surface Temp** | Landsat C02 L2 via STAC/GEE | Urban heat island LST at 30m |
| **Subsidence** | Sentinel-1 InSAR via ASF DAAC | Ground deformation velocity |
| **Building Footprints** | Google Open Buildings V3 (GEE/GCS) | 1.8B buildings, 50cm ML-detected polygons, SEA coverage (**NEW v3.1**) |
| **Building Heights** | Google Open Buildings 2.5D Temporal (GEE) | 4m effective resolution, annual 2016-2023, story estimation (**NEW v3.1**) |
| **Building Attributes** | Overture Maps Buildings (S3 GeoParquet) | 2.6B conflated footprints, OSM material/type tags (**NEW v3.1**) |
| **Vulnerability Curves** | JRC Global Flood Depth-Damage (Huizinga 2017) | 4-class material system, Asia-calibrated (**NEW v3.1**) |
| **Risk Output** | Structure-level H×E×V | Per-building damage ratio, EAL, PML (**NEW v3.1**) |
| **EAL Method** | Multi-RP trapezoidal integration | RPs [2,5,10,25,50,100,250,500,1000] → loss-exceedance curve (**FIX v3.2 — Gap Q**) |
| **Discharge→Depth** | Manning's equation rating curve | `rating_curve.py` converts GloFAS m³/s → water level m (**FIX v3.2 — Gap J**) |
| **Wind Field Model** | Holland (2008) revised parametric vortex | B-parameter from Vmax + Pc, clamped [1.0, 2.5] (**FIX v3.2 — Gap P**) |
| **Pluvial Flood** | HAND + slope + impervious + extreme precip | Surface water flooding proxy for SEA cities (**NEW v3.2 — Gap M**) |
| **SLR Projections** | IPCC AR6 regional tables | `ipcc_slr.py` with SSP-stratified 2050/2100 values (**FIX v3.2 — Gap K**) |
| **Subsidence Fallback** | Published literature rates | Minderhoud 2018 (HCMC), Chaussard 2013 (Jakarta) (**FIX v3.2 — Gap L**) |
| **Ensemble Uncertainty** | Real multi-model spread | 5 GCMs → percentile bounds, not fabricated ±30% (**FIX v3.2 — Gap I**) |
| **Data Validation** | `validation.py` decorators | NaN/range/void checks on all ingested data (**NEW v3.2 — Gap R**) |

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                       ECOSHIELD ARCHITECTURE v3.1                            │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                          CLIENT LAYER                                  │  │
│  │                     (Next.js / React Frontend)                         │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                     │                                        │
│                                     ▼                                        │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                           API LAYER                                    │  │
│  │                     FastAPI + Pydantic Schemas                         │  │
│  │   POST /v1/assess    POST /v1/portfolio    GET /v1/hazards/{type}     │  │
│  │   POST /v1/buildings/assess ← Structure-level (NEW v3.1)             │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                     │                                        │
│                                     ▼                                        │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                       WORKFLOW LAYER                                    │  │
│  │                   (Agno Workflow Orchestration)                         │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │  │
│  │  │              HazardAssessmentWorkflow                             │  │  │
│  │  │  ┌────────────────────────────────────────────────────────────┐  │  │  │
│  │  │  │ Step 0: Asset Fetch (NEW v3.1)                             │  │  │  │
│  │  │  │   └── fetch_buildings() → BuildingCluster + elevations     │  │  │  │
│  │  │  ├────────────────────────────────────────────────────────────┤  │  │  │
│  │  │  │ Step 1: Chronic Hazards (Parallel)                         │  │  │  │
│  │  │  │   ├── assess_subsidence() → AdjustedSurface                │  │  │  │
│  │  │  │   └── assess_urban_heat()                                  │  │  │  │
│  │  │  ├────────────────────────────────────────────────────────────┤  │  │  │
│  │  │  │ Step 2: Cyclone Assessment                                 │  │  │  │
│  │  │  │   └── assess_cyclone() → CycloneEventParams                │  │  │  │
│  │  │  ├────────────────────────────────────────────────────────────┤  │  │  │
│  │  │  │ Step 3: Acute Hazards (Parallel)                           │  │  │  │
│  │  │  │   ├── assess_storm_surge(cyclone_params, surface)          │  │  │  │
│  │  │  │   ├── assess_coastal_flood(surface)                        │  │  │  │
│  │  │  │   ├── assess_riverine_flood(surface)                       │  │  │  │
│  │  │  │   ├── assess_pluvial_flood(surface)   ← NEW v3.2 (Gap M)  │  │  │  │
│  │  │  │   └── assess_landslide()                                   │  │  │  │
│  │  │  ├────────────────────────────────────────────────────────────┤  │  │  │
│  │  │  │ Step 4: Structure Risk (NEW v3.1)                          │  │  │  │
│  │  │  │   └── H×E×V per building → StructureRiskResult             │  │  │  │
│  │  │  ├────────────────────────────────────────────────────────────┤  │  │  │
│  │  │  │ Step 5: Composite Risk Calculation                         │  │  │  │
│  │  │  │   └── aggregate → PortfolioRiskSummary / FullRiskProfile   │  │  │  │
│  │  │  └────────────────────────────────────────────────────────────┘  │  │  │
│  │  └──────────────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                     │                                        │
│                                     ▼                                        │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                          AGENT LAYER                                   │  │
│  │                     (Agno Agents + DeepSeek LLM)                       │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │  │
│  │  │ ClimateAgent │  │ HazardAgent  │  │ ReportAgent  │                 │  │
│  │  │ (NEX-GDDP)  │  │  (8 Tools)   │  │  (Synthesis) │                 │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                 │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                     │                                        │
│                                     ▼                                        │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                          TOOLS LAYER                                   │  │
│  │                    (Pydantic Models In/Out)                            │  │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐         │  │
│  │  │ nex_gddp   │ │ elevation  │ │  riverine  │ │  coastal   │         │  │
│  │  │  _tools    │ │  _tools    │ │   _flood   │ │   _flood   │         │  │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘         │  │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐         │  │
│  │  │ subsidence │ │ landslide  │ │  cyclone   │ │   surge    │         │  │
│  │  │   _tools   │ │  _tools    │ │  _tools    │ │  _tools    │         │  │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘         │  │
│  │  ┌────────────┐ ┌────────────┐                                       │  │
│  │  │urban_heat  │ │ structure  │ ← NEW v3.1: H×E×V damage calc        │  │
│  │  │  _tools    │ │ _risk_tools│                                       │  │
│  │  └────────────┘ └────────────┘                                       │  │
│  │  ┌────────────┐ ┌────────────┐                                       │  │
│  │  │ pluvial    │ │  rating    │ ← NEW v3.2: Pluvial + discharge→depth │  │
│  │  │_flood_tools│ │ _curve     │                                       │  │
│  │  └────────────┘ └────────────┘                                       │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                     │                                        │
│                                     ▼                                        │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │           DATA LAYER (API-First Ingestion → Local Cache)               │  │
│  │  ┌─ HAZARD DATA ──────────────────────────────────────────────────┐   │  │
│  │  │ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐   │   │  │
│  │  │ │ NEX-GDDP   │ │ Copernicus │ │ Sentinel-1 │ │  IBTrACS   │   │   │  │
│  │  │ │  (S3/STAC) │ │ GLO-30(S3) │ │  ASF API   │ │  (REST)    │   │   │  │
│  │  │ └────────────┘ └────────────┘ └────────────┘ └────────────┘   │   │  │
│  │  │ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐   │   │  │
│  │  │ │  Landsat   │ │ ERA5-Land  │ │ GloFAS v4  │ │ SoilGrids  │   │   │  │
│  │  │ │ (GEE/STAC) │ │  (CDS API) │ │ (CDS API)  │ │ (REST API) │   │   │  │
│  │  │ └────────────┘ └────────────┘ └────────────┘ └────────────┘   │   │  │
│  │  │ ┌────────────┐ ┌────────────┐                                  │   │  │
│  │  │ │   GEBCO    │ │Sentinel-2  │                                  │   │  │
│  │  │ │ (BODC API) │ │ (PC STAC)  │                                  │   │  │
│  │  │ └────────────┘ └────────────┘                                  │   │  │
│  │  └────────────────────────────────────────────────────────────────┘   │  │
│  │  ┌─ ASSET LAYER (NEW v3.1) ───────────────────────────────────────┐  │  │
│  │  │ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐   │  │  │
│  │  │ │ Google Open│ │Google Open │ │  Overture   │ │  JRC Flood │   │  │  │
│  │  │ │Buildings V3│ │Build. 2.5D │ │  Maps Bldg  │ │Damage Func │   │  │  │
│  │  │ │(GEE / GCS) │ │ (GEE/GCS)  │ │ (S3 Parq.) │ │  (Static)  │   │  │  │
│  │  │ └────────────┘ └────────────┘ └────────────┘ └────────────┘   │  │  │
│  │  └────────────────────────────────────────────────────────────────┘  │  │
│  │  ┌────────────┐                                                      │  │
│  │  │  PostGIS   │ ← Buildings cache + spatial index                    │  │
│  │  └────────────┘                                                      │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Source Matrix — v3.1 API-First + Asset Layer

### Primary Climate Replacement: CMIP6-VN → NASA NEX-GDDP-CMIP6

| Attribute | CMIP6-VN (REMOVED) | NEX-GDDP-CMIP6 (v3.0) |
|-----------|---------------------|------------------------|
| **Coverage** | Vietnam only | Global (180°W–180°E, 60°S–90°N) |
| **Resolution** | 10km (0.1°) | 25km (0.25°) — BCSD downscaled |
| **GCM Models** | ~5 subset | 35 CMIP6 GCMs |
| **SSP Scenarios** | SSP245, SSP585 | SSP126, SSP245, SSP370, SSP585 |
| **Variables** | pr, tas, tasmax, tasmin | pr, tas, tasmax, tasmin, hurs, sfcWind, rsds, rlds |
| **Time Coverage** | 1980–2099 | 1950–2100 (historical + projections) |
| **Access Method** | Manual Figshare download | 4 programmatic APIs (see below) |
| **License** | CC-BY-4.0 | CC0-1.0 (fully open, commercial-friendly) |
| **Format** | NetCDF (Figshare tarballs) | NetCDF4 + Cloud-Optimized GeoTIFF |
| **SEA Expansion** | ❌ Vietnam only | ✅ Jakarta, Manila, Bangkok, Singapore, all SEA |
| **Downscaling** | BCSD against VN observations | BCSD against GMFD global observations |
| **Reference** | Tran-Anh et al. 2023 | Thrasher et al. 2022, Scientific Data 9:262 |

### NEX-GDDP-CMIP6: Four API Access Methods

| Priority | Method | Endpoint | Auth | Best For |
|----------|--------|----------|------|----------|
| **1** | AWS S3 Open Data | `s3://nex-gddp-cmip6` (us-west-2) | None | Production bulk ingestion |
| **2** | NASA THREDDS NetCDF Subset | `https://ds.nccs.nasa.gov/thredds/ncss/grid/AMES/NEX/GDDP-CMIP6/` | None | Spatial/temporal subsets |
| **3** | Planetary Computer STAC | `https://planetarycomputer.microsoft.com/api/stac/v1` | `planetary-computer` lib | Catalog search, metadata |
| **4** | Google Earth Engine | `ee.ImageCollection('NASA/GDDP-CMIP6')` | GEE service account | Geospatial analysis pipelines |

**Production recommendation**: Use AWS S3 for batch ingestion of city bounding boxes.  Use THREDDS for on-demand point/polygon queries for locations outside cached regions.

### Complete Data Source Matrix

| # | Dataset | Module | Hazard(s) | API Access | Auth | Resolution | Format |
|---|---------|--------|-----------|------------|------|------------|--------|
| 1 | **NEX-GDDP-CMIP6** | `nex_gddp.py` | Flood, Heat, Landslide | AWS S3 / THREDDS / PC STAC / GEE | None / None / PC lib / GEE key | 0.25° (~25km) | NetCDF4 |
| 2 | **Copernicus GLO-30** | `elevation.py` | Flood, Surge, Landslide | AWS S3 OpenData `s3://copernicus-dem-30m` | None | 30m | COG |
| 3 | **ERA5-Land** | `era5.py` | Heat (WBGT), Wind | CDS API `cds.climate.copernicus.eu` | CDS API key | 9km (0.1°) | GRIB2/NetCDF |
| 4 | **GloFAS v4** | `glofas.py` | Riverine Flood | CDS API `cds.climate.copernicus.eu` | CDS API key | 0.05° (~5km) | GRIB2/NetCDF |
| 5 | **IBTrACS v04r01** | `ibtracs.py` | Cyclone, Surge | NCEI HTTPS `ibtracs.unca.edu` / REST | None | Point tracks | CSV/NetCDF |
| 6 | **Sentinel-1 InSAR** | `insar.py` | Subsidence | ASF DAAC API `api.daac.asf.alaska.edu` | NASA Earthdata | 100m | GeoTIFF |
| 7 | **Landsat C02 L2** | `landsat.py` | Urban Heat (LST) | PC STAC / Google Earth Engine | PC lib / GEE key | 30m | COG |
| 8 | **SoilGrids v2** | `soilgrids.py` | Landslide | REST API `rest.isric.org/soilgrids/v2.0` | None | 250m | GeoTIFF/JSON |
| 9 | **GEBCO 2024** | `gebco.py` | Storm Surge (bathy) | BODC OGC WCS `www.gebco.net/data_and_products` | None | 15 arc-sec (~450m) | NetCDF/COG |
| 10 | **Sentinel-2 L2A** | `sentinel2.py` | Landslide (NDVI) | PC STAC `planetarycomputer.microsoft.com` | PC lib | 10m | COG |
| — | **Meteomatics API** *(OPTIONAL — Tier 2, Future)* | `meteomatics_client.py` | Real-time weather (Phase 6) | REST `api.meteomatics.com` | Username + Password (paid) | 90m (downscaled) | CSV/JSON/NetCDF |
| 11 | **Google Open Buildings V3** | `open_buildings.py` | Asset footprints | GEE `GOOGLE/Research/open-buildings/v3/polygons` / GCS | GEE key / None | 50cm (ML-detected) | GeoJSON/CSV | ← **NEW v3.1** |
| 12 | **Google Open Buildings 2.5D Temporal** | `open_buildings.py` | Asset heights | GEE `GOOGLE/Research/open-buildings-temporal/v1` | GEE key | 4m effective (0.5m raster) | Raster | ← **NEW v3.1** |
| 13 | **Overture Maps Buildings** | `overture_buildings.py` | Asset attributes (material, type) | S3 `s3://overturemaps-us-west-2/release/` via DuckDB | None | Building-level | GeoParquet | ← **NEW v3.1** |
| 14 | **JRC Global Flood Depth-Damage** | `jrc_vulnerability.py` | Vulnerability curves | Static (Huizinga et al. 2017) / HydroMT-FIAT | None | 4 material classes | Tabular | ← **NEW v3.1** |

> **Note on Meteomatics:** Evaluated and classified as **Optional/Future (Tier 2)**. Provides 1,800+ real-time weather parameters at 90m resolution, but overlaps ~90% with free sources (NEX-GDDP-CMIP6 + ERA5-Land) for climate risk. Climate projections limited to 1 GCM (MRI-ESM2.0) vs NEX-GDDP's 35-model ensemble. Enterprise pricing with no free production tier. Primary value is real-time forecasting (1–14 day), which is not in v3 scope. See `ECOSHIELD-METEOMATICS-ANALYSIS.md` for full evaluation.

### Hazard → Data Source Mapping

| Hazard | Primary Data | Climate Projection (NEX-GDDP) | Resolution |
|--------|-------------|-------------------------------|------------|
| **Riverine Flood** | GloFAS v4 + **rating_curve.py** (Manning's) + GLO-30 DEM + HAND | ✅ Extreme precip (pr) projections | 30m (DEM) |
| **Coastal Flood** | GLO-30 DEM + **IPCC AR6 SLR tables** (`ipcc_slr.py`) | ❌ Not used directly | 30m (DEM) |
| **Pluvial Flood** | HAND + slope + impervious fraction + NEX-GDDP extreme precip | ✅ Extreme precip (pr) projections | 30m (DEM) ← **NEW v3.2** |
| **Subsidence** | Sentinel-1 InSAR + GLO-30 DEM + **published rate fallback** | ❌ Not used | 100m (InSAR) |
| **Landslide** | GLO-30 + SoilGrids + Sentinel-2 NDVI | ✅ Rainfall triggers (pr) | 30m (DEM) |
| **Tropical Cyclone** | IBTrACS v04r01 best tracks + **Holland (2008) parametric vortex** | ❌ Not used directly | 1–10km (tracks) |
| **Storm Surge** | Parametric model + GEBCO bathy + GLO-30 | ❌ Not used directly | 30–100m |
| **Urban Heat** | Landsat LST + ERA5-Land (WBGT) | ✅ Temperature projections (tasmax) | 30m (LST) |

> **Climate Forcing Resolution Note (Gap H):** NEX-GDDP-CMIP6 climate projections are at 0.25° (~25 km). All buildings within a ~625 km² grid cell share identical climate forcing values (precipitation change, temperature change). Building-level hazard differentiation comes from terrain layers (DEM, HAND, LST) at 30 m, not from climate model resolution. The `HazardIntensity.climate_forcing_resolution_m` field (v3.2) makes this transparent to all consumers.

### Asset Layer → Risk Output Mapping (NEW v3.1)

| Component | Data Source | Output | Resolution |
|-----------|------------|--------|------------|
| **Building Footprints** | Google Open Buildings V3 + Overture Maps | `BuildingFootprint` (centroid, area, polygon) | Sub-meter |
| **Building Heights** | Google Open Buildings 2.5D Temporal | `BuildingHeight` (height_m, estimated stories) | 4m effective |
| **Structural Classification** | Inferred from area + height + OSM tags | `StructuralCharacteristics` (material, occupancy, vulnerability class) | Per-building |
| **Vulnerability Curves** | JRC Huizinga et al. 2017 (Asia) | `DepthDamageCurve` (4 classes: informal → reinforced) | 4 material classes |
| **Structure Risk** | H×E×V calculation | `StructureRiskResult` (damage ratio, EAL, PML per building) | Per-building |
| **Portfolio Aggregation** | Aggregation over BuildingCluster | `PortfolioRiskSummary` (city/district stats) | Tile/district |

---

## Technology Stack

| Layer | Technology | Version | Notes |
|-------|------------|---------|-------|
| **Frontend** | Next.js + React | 14.x | Static + SSR |
| **API** | FastAPI | 0.111+ | Async, Pydantic v2 |
| **Orchestration** | Agno Workflows | 1.0+ | Deterministic pipelines |
| **Agents** | Agno Agents | 1.0+ | Tool-equipped agents |
| **LLM** | DeepSeek Chat | — | Via Agno provider |
| **Database** | PostgreSQL + PostGIS | 16+ | Spatial queries + cached data |
| **Cache** | Redis | 7+ | Session state + API response cache |
| **Object Storage** | S3-compatible (MinIO) | — | NetCDF, COG tiles |
| **Task Queue** | Celery + Redis | — | Async ingestion jobs |
| **Containers** | Docker Compose | — | Multi-stage builds |

### Python Dependencies

```toml
[project]
dependencies = [
    # Core
    "xarray>=2024.1",
    "netcdf4>=1.6",
    "rasterio>=1.3",
    "numpy>=1.26",
    "scipy>=1.12",
    "pandas>=2.1",
    # API clients
    "boto3>=1.34",              # AWS S3 (NEX-GDDP, GLO-30)
    "cdsapi>=0.7",              # Copernicus CDS (ERA5-Land, GloFAS)
    "pystac-client>=0.8",       # STAC catalogs (Planetary Computer)
    "planetary-computer>=1.0",  # PC token signing
    "earthengine-api>=0.1.390", # Google Earth Engine (Landsat)
    "asf-search>=7.0",          # ASF DAAC (Sentinel-1 InSAR)
    "requests>=2.31",           # REST APIs (SoilGrids, IBTrACS, GEBCO)
    # Geospatial
    "geopandas>=0.14",
    "shapely>=2.0",
    "pyproj>=3.6",
    "richdem>=2.3",             # HAND computation
    "duckdb>=0.10",             # Overture Maps GeoParquet queries (NEW v3.1)
    # Framework
    "fastapi>=0.111",
    "uvicorn[standard]>=0.29",
    "pydantic>=2.7",
    "agno>=1.0",
    "celery>=5.3",
    # Database
    "sqlalchemy>=2.0",
    "geoalchemy2>=0.14",
    "asyncpg>=0.29",
    "redis>=5.0",
]
```

---

## Project Structure

```
ecoshield/
├── pyproject.toml
├── .env.example
├── docker-compose.yml
│
├── docs/
│   ├── ECOSHIELD-ARCHITECTURE-v3.1.md     # ← This file
│   ├── ECOSHIELD-PHASE1-MODELS-v3.md
│   ├── ECOSHIELD-PHASE2-DATA-v3.md
│   ├── ECOSHIELD-PHASE3-TOOLS-v3.md
│   ├── ECOSHIELD-PHASE4-WORKFLOW-v3.md
│   └── ECOSHIELD-PHASE5-API-v3.md
│
├── src/
│   ├── core/models/                  # Phase 1: Pydantic models
│   │   ├── __init__.py
│   │   ├── enums.py                  # HazardType (8 incl. PLUVIAL_FLOOD v3.2), DataSource, SSPScenario, BuildingMaterial, VulnerabilityClass
│   │   ├── geometry.py               # Location, BBox (with area_km2 cosine-corrected — FIX v3.2 Gap O)
│   │   ├── asset.py                  # BuildingFootprint, BuildingHeight, StructuralCharacteristics (NEW v3.1)
│   │   ├── climate.py                # ClimateBaseline, ClimateProjection
│   │   ├── elevation.py              # ElevationResult, SlopeResult
│   │   ├── events.py                 # HazardEventContext
│   │   ├── hazard.py                 # HazardIntensity (+ climate_forcing_resolution_m v3.2)
│   │   ├── exposure.py               # ExposureProfile (anchored to StructuralCharacteristics v3.1)
│   │   ├── vulnerability.py          # VulnerabilityAssessment, DepthDamageCurve, OccupancyValueMultiplier (FIX v3.2 Gap T)
│   │   ├── surface.py                # AdjustedSurface + BuildingAdjustedSurface (FIX v3.2 Gap S)
│   │   ├── results.py                # HazardAssessmentResult, StructureRiskResult (multi-RP EAL v3.2), PortfolioRiskSummary
│   │   └── composite.py              # FullRiskProfile
│   │
│   ├── data/                         # Phase 2: Data access layer (API-first)
│   │   ├── __init__.py
│   │   ├── nex_gddp.py              # NEX-GDDP-CMIP6 (AWS S3 + THREDDS) — ensemble wired (FIX v3.2)
│   │   ├── elevation.py              # Copernicus GLO-30 (AWS S3 COG)
│   │   ├── hand.py                   # HAND index (computed from GLO-30)
│   │   ├── era5.py                   # ERA5-Land (CDS API)
│   │   ├── glofas.py                 # GloFAS v4 river discharge (CDS API)
│   │   ├── rating_curve.py           # Discharge→depth via Manning's equation — NEW v3.2 (Gap J)
│   │   ├── ipcc_slr.py               # IPCC AR6 regional SLR projections — NEW v3.2 (Gap K)
│   │   ├── soilgrids.py              # ISRIC SoilGrids v2 (REST)
│   │   ├── landsat.py                # Landsat C02 L2 LST (PC STAC / GEE)
│   │   ├── gebco.py                  # GEBCO 2024 bathymetry (BODC WCS)
│   │   ├── sentinel2.py              # Sentinel-2 L2A NDVI (PC STAC)
│   │   ├── insar.py                  # Sentinel-1 InSAR + published-rate fallback (FIX v3.2)
│   │   ├── ibtracs.py                # IBTrACS cyclone tracks (NCEI REST)
│   │   ├── open_buildings.py         # Google Open Buildings V3 + 2.5D (GEE) — NEW v3.1
│   │   ├── overture_buildings.py     # Overture Maps buildings (S3 GeoParquet) — BUG FIX v3.2 (Gap N)
│   │   ├── jrc_vulnerability.py      # JRC depth-damage curves (static) — NEW v3.1
│   │   ├── validation.py             # Data quality validation decorators — NEW v3.2 (Gap R)
│   │   └── ingestion/
│   │       ├── __init__.py
│   │       ├── nex_gddp_ingest.py    # Batch S3 → local NetCDF
│   │       ├── dem_ingest.py          # Batch COG tiles → local
│   │       ├── buildings_ingest.py    # Batch building footprint → PostGIS — NEW v3.1
│   │       ├── ibtracs_ingest.py      # Full CSV → PostGIS
│   │       └── scheduler.py           # Cron/Celery scheduling — ALL modules (FIX v3.2 Gap U)
│   │
│   ├── tools/                        # Phase 3: Hazard assessment tools
│   │   ├── __init__.py
│   │   ├── riverine_flood_tools.py   # GloFAS + rating_curve + HAND + GLO-30 + NEX-GDDP
│   │   ├── coastal_flood_tools.py    # IPCC SLR + GLO-30
│   │   ├── pluvial_flood_tools.py    # HAND + slope + impervious + precip — NEW v3.2 (Gap M)
│   │   ├── subsidence_tools.py       # Sentinel-1 InSAR + published fallback + GLO-30
│   │   ├── landslide_tools.py        # GLO-30 + NEX-GDDP + SoilGrids + S2
│   │   ├── cyclone_tools.py          # IBTrACS + Holland (2008) wind profile — FIX v3.2 (Gap P)
│   │   ├── storm_surge_tools.py      # IBTrACS + GEBCO + GLO-30
│   │   ├── urban_heat_tools.py       # Landsat LST + ERA5 WBGT + NEX-GDDP
│   │   └── structure_risk_tools.py   # H×E×V per building, multi-RP EAL — FIX v3.2 (Gap Q)
│   │
│   ├── workflows/                    # Phase 4: Agno Workflows
│   │   ├── __init__.py
│   │   ├── hazard_workflow.py        # Main 6-step workflow (was 4-step, v3.1)
│   │   ├── portfolio_workflow.py     # Batch portfolio
│   │   └── steps/
│   │       ├── __init__.py
│   │       ├── asset_fetch.py        # Step 0: Fetch buildings for tile — NEW v3.1
│   │       ├── chronic_hazards.py    # Step 1: subsidence + heat (parallel)
│   │       ├── cyclone_step.py       # Step 2: cyclone → params
│   │       ├── acute_hazards.py      # Step 3: flood + surge + slide (parallel)
│   │       ├── structure_risk.py     # Step 4: H×E×V per building — NEW v3.1
│   │       └── composite.py          # Step 5: weighted composite (was Step 4)
│   │
│   ├── api/                          # Phase 5: FastAPI routes
│   │   ├── __init__.py
│   │   ├── main.py                   # App + lifespan
│   │   ├── routes/
│   │   │   ├── assess.py             # POST /v1/assess
│   │   │   ├── portfolio.py          # POST /v1/portfolio
│   │   │   ├── buildings.py          # POST /v1/buildings/assess — NEW v3.1
│   │   │   └── hazards.py            # GET /v1/hazards/{type}
│   │   ├── schemas/
│   │   │   ├── requests.py           # + BuildingAssessRequest (v3.1)
│   │   │   └── responses.py          # + BuildingRiskResponse (v3.1)
│   │   ├── middleware/
│   │   │   ├── auth.py
│   │   │   └── rate_limit.py
│   │   └── errors.py
│   │
│   └── config/
│       ├── settings.py               # Centralized settings (env vars)
│       └── hazard_weights.yaml       # City-specific hazard weights
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
└── scripts/
    ├── ingest_climate_data.py        # CLI: batch data ingestion
    ├── validate_sources.py           # Health-check all API sources
    └── seed_ibtracs.py               # Seed IBTrACS into PostGIS
```

---

## Data Ingestion Strategy

EcoShield uses an **API-first, local-cache** architecture with three ingestion modes:

```
┌───────────────────────────────────────────────────────────────┐
│                   DATA INGESTION PIPELINE                      │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌───────────┐    ┌────────────────┐    ┌─────────────────┐  │
│  │ External  │    │   Ingestion    │    │   Local Store   │  │
│  │   APIs    │───▶│   Pipeline     │───▶│  PostGIS + S3   │  │
│  │ (public)  │    │ (Celery async) │    │  (low latency)  │  │
│  └───────────┘    └────────────────┘    └─────────────────┘  │
│       │                                         │             │
│  ┌────┴──────┐                           ┌──────┴───────┐    │
│  │ AWS S3    │                           │  Assessment  │    │
│  │ CDS API   │                           │    Engine    │    │
│  │ REST APIs │                           │ (real-time)  │    │
│  │ STAC APIs │                           └──────────────┘    │
│  │ GEE       │                                                │
│  └───────────┘                                                │
│                                                                │
│  Ingestion modes:                                              │
│  • BATCH:     Pre-fetch city bbox on deployment (CLI/Celery)  │
│  • ON-DEMAND: Fetch for uncached locations at query time       │
│  • REFRESH:   Scheduled re-fetch (weekly ERA5, monthly GDDP)  │
│                                                                │
│  Cache policy:                                                 │
│  • Climate (NEX-GDDP): cache per model/scenario/year/bbox     │
│  • DEM (GLO-30): cache per tile (permanent, terrain is static) │
│  • ERA5-Land: cache per month/variable/bbox (refresh monthly)  │
│  • GloFAS: cache per return-period/bbox (refresh monthly)      │
│  • IBTrACS: full database in PostGIS (refresh weekly)          │
│  • SoilGrids: cache per query point (permanent)                │
│  • Satellite: cache per scene/tile (permanent)                 │
│  • Buildings: PostGIS per city bbox (refresh quarterly) ← v3.1 │
│  • Vulnerability: JRC curves embedded (static) ← v3.1         │
│                                                                │
└───────────────────────────────────────────────────────────────┘
```

---

## Dependency Graph

The workflow enforces this execution order, ensuring subsidence results feed into flood depth calculations:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         DEPENDENCY GRAPH v3.1                              │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ STEP 0: ASSET FETCH (NEW v3.1)                                      │  │
│  │  ┌─────────────────────────────────────────────────────────────┐    │  │
│  │  │ Fetch buildings for tile from PostGIS                       │    │  │
│  │  │ → BuildingCluster (footprints, heights, materials, elev)   │    │  │
│  │  └─────────────────────────────────────────────────────────────┘    │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ STEP 1: CHRONIC (Parallel)                                         │  │
│  │  ┌─────────────┐     ┌─────────────────────────────────────────┐   │  │
│  │  │ Subsidence  │     │ Urban Heat                              │   │  │
│  │  │ InSAR(ASF)  │     │ Landsat LST + ERA5-Land WBGT + NEX-GDDP│   │  │
│  │  └──────┬──────┘     └─────────────────────────────────────────┘   │  │
│  │         │                                                           │  │
│  │         ▼                                                           │  │
│  │  ┌─────────────────┐                                                │  │
│  │  │ AdjustedSurface │ ← Subsidence modifies ground elevation        │  │
│  │  └────────┬────────┘                                                │  │
│  └───────────┼─────────────────────────────────────────────────────────┘  │
│              │                                                            │
│  ┌───────────┼─────────────────────────────────────────────────────────┐  │
│  │ STEP 2: CYCLONE (Sequential — exports params for surge)            │  │
│  │           │                                                          │  │
│  │           ▼                                                          │  │
│  │    ┌─────────────┐                                                   │  │
│  │    │   Cyclone   │──────► CycloneEventParams                        │  │
│  │    │  (IBTrACS)  │        (wind_kts, pressure_mb, rmw_km)           │  │
│  │    └──────┬──────┘                                                   │  │
│  └───────────┼─────────────────────────────────────────────────────────┘  │
│              │                                                            │
│  ┌───────────┼─────────────────────────────────────────────────────────┐  │
│  │ STEP 3: ACUTE (Parallel with dependencies)                          │  │
│  │           │                                                          │  │
│  │           ▼                                                          │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │  │
│  │  │ Storm Surge │  │  Riverine   │  │  Coastal    │  │ Landslide │  │  │
│  │  │ (cyclone +  │  │   Flood     │  │   Flood     │  │ (NEX-GDDP │  │  │
│  │  │  surface +  │  │ (GloFAS +   │  │ (SLR +      │  │ + SoilGrid│  │  │
│  │  │  GEBCO)     │  │ rating_curve│  │  surface)   │  │ + S2 NDVI)│  │  │
│  │  │             │  │ + surface)  │  │             │  │           │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘  │  │
│  │                                                                     │  │
│  │  ┌─────────────┐                                                    │  │
│  │  │  Pluvial    │ ← NEW v3.2 (Gap M)                                │  │
│  │  │   Flood     │                                                    │  │
│  │  │ (HAND+slope │                                                    │  │
│  │  │ +precip)    │                                                    │  │
│  │  └─────────────┘                                                    │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ STEP 4: STRUCTURE RISK (NEW v3.1)                                   │  │
│  │  ┌──────────────────────────────────────────────────────────────┐   │  │
│  │  │ For each building in BuildingCluster:                        │   │  │
│  │  │   flood_depth = hazard_water_level - effective_ground_floor  │   │  │
│  │  │   damage_ratio = JRC_curve.interpolate(flood_depth)          │   │  │
│  │  │   loss_usd = damage_ratio × replacement_value               │   │  │
│  │  │   ↓ Repeat for RPs [2, 5, 10, 25, 50, 100, 250, 500, 1000] (FIX v3.2 Gap Q) │   │  │
│  │  │   EAL = ∫₀¹ L(p) dp  (trapezoidal on loss-exceedance)      │   │  │
│  │  │   → StructureRiskResult (per building, multi-RP)             │   │  │
│  │  └──────────────────────────────────────────────────────────────┘   │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ STEP 5: COMPOSITE                                                   │  │
│  │  ┌──────────────────────────────────────────────────────────────┐   │  │
│  │  │ Aggregate acute scores  (same return period) — weighted sum │   │  │
│  │  │ Aggregate chronic scores (same time horizon) — weighted sum │   │  │
│  │  │ Aggregate structure results → PortfolioRiskSummary           │   │  │
│  │  │ NEVER combine acute + chronic into a single score           │   │  │
│  │  └──────────────────────────────────────────────────────────────┘   │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

| Phase | Document | Focus | Key Deliverables |
|-------|----------|-------|------------------|
| **Phase 1** | `ECOSHIELD-PHASE1-MODELS-v3.md` | Core Pydantic models + asset models | 20+ model classes, DataSource (14 sources), HazardType (8 incl. PLUVIAL_FLOOD), BuildingMaterial, VulnerabilityClass, StructureRiskResult (multi-RP EAL), BuildingAdjustedSurface, OccupancyValueMultiplier |
| **Phase 2** | `ECOSHIELD-PHASE2-DATA-v3.md` | Data access layer (API-first + asset) | 14 data modules + 5 ingestion pipelines + `rating_curve.py` + `ipcc_slr.py` + `validation.py` + published subsidence fallback |
| **Phase 3** | `ECOSHIELD-PHASE3-TOOLS-v3.md` | Hazard + structure risk tools | 8 hazard tools (incl. pluvial_flood) + structure_risk_tools (multi-RP H×E×V) + Holland (2008) wind field |
| **Phase 4** | `ECOSHIELD-PHASE4-WORKFLOW-v3.md` | Agno workflow orchestration | 6-step workflow (asset fetch → chronic → cyclone → acute [5 hazards] → structure risk → composite) |
| **Phase 5** | `ECOSHIELD-PHASE5-API-v3.md` | API integration | FastAPI routes + building assessment endpoint + auth + rate limiting |

---

## Release Strategy

| Version | Cities | Timeline | Notes |
|---------|--------|----------|-------|
| **v1.0 MVP** | Ho Chi Minh City | Q1–Q2 2026 | All 7 hazards, initial data ingestion |
| **v1.1** | Hanoi, Da Nang | Q3–Q4 2026 | Same data, new city configs + weights |
| **v2.0** | Jakarta, Manila | 2027 | NEX-GDDP global coverage enables this |
| **v3.0** | Bangkok, Singapore | 2027–2028 | Full SEA coverage |

---

## Environment Variables

```bash
# Required — Core services
DEEPSEEK_API_KEY=sk-...
DATABASE_URL=postgresql://ecoshield:password@localhost:5432/ecoshield
REDIS_URL=redis://localhost:6379
S3_BUCKET=ecoshield-data
S3_ENDPOINT=http://localhost:9000            # MinIO for local dev
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin

# Required — Data API credentials
CDS_API_URL=https://cds.climate.copernicus.eu/api
CDS_API_KEY=<uid>:<api-key>                  # ERA5-Land + GloFAS
EARTHDATA_TOKEN=<nasa-earthdata-bearer>      # ASF DAAC (Sentinel-1)
GEE_SERVICE_ACCOUNT_JSON=/path/to/gee.json   # Google Earth Engine (Landsat)

# NEX-GDDP Configuration (NO auth required)
NEX_GDDP_S3_BUCKET=nex-gddp-cmip6
NEX_GDDP_S3_REGION=us-west-2
NEX_GDDP_THREDDS_BASE=https://ds.nccs.nasa.gov/thredds

# Copernicus GLO-30 (NO auth required)
GLO30_S3_BUCKET=copernicus-dem-30m
GLO30_S3_REGION=eu-central-1

# Optional — Tuning
LOG_LEVEL=INFO
ENVIRONMENT=development

# Optional — Tier 2 Data Sources (Future)
# METEOMATICS_USERNAME=<your-username>        # Meteomatics API (Phase 6 early-warning)
# METEOMATICS_PASSWORD=<your-password>        # Requires paid subscription
ECOSHIELD_API_KEYS=key1,key2                 # Comma-separated valid API keys
INGESTION_CONCURRENCY=4                      # Parallel ingestion workers
```

---

## Docker Compose

```yaml
version: "3.9"
services:
  api:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [postgres, redis, minio]

  postgres:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_DB: ecoshield
      POSTGRES_USER: ecoshield
      POSTGRES_PASSWORD: password
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    ports: ["9000:9000", "9001:9001"]
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes: ["miniodata:/data"]

  worker:
    build: .
    command: celery -A src.data.ingestion.scheduler worker -l info
    env_file: .env
    depends_on: [redis, minio]

volumes:
  pgdata:
  miniodata:
```

---

## Quick Start

```bash
# 1. Start services
docker-compose up -d

# 2. Initial data ingestion for HCMC (MVP)
docker-compose exec api python scripts/ingest_climate_data.py --city hcmc

# 3. Ingest building footprints for HCMC (NEW v3.1)
docker-compose exec api python scripts/ingest_buildings.py --city hcmc

# 4. Validate all API sources are reachable
docker-compose exec api python scripts/validate_sources.py

# 5. Run API
docker-compose exec api uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 6. Test point assessment
curl -X POST http://localhost:8000/v1/assess \
  -H "Content-Type: application/json" \
  -d '{"location": {"lat": 10.8, "lon": 106.6}, "hazards": ["flood", "heat"]}'

# 7. Test structure-level assessment (NEW v3.1)
curl -X POST http://localhost:8000/v1/buildings/assess \
  -H "Content-Type: application/json" \
  -d '{"lat": 10.8, "lon": 106.6, "radius_m": 500, "return_period": 100}'
```

---

## References

1. **NEX-GDDP-CMIP6**: Thrasher, B. et al. (2022). NASA Global Daily Downscaled Projections, CMIP6. *Scientific Data*, 9, 262. DOI: 10.1038/s41597-022-01393-4
2. **NEX-GDDP-CMIP6 AWS**: https://registry.opendata.aws/nex-gddp-cmip6/
3. **NEX-GDDP-CMIP6 THREDDS**: https://ds.nccs.nasa.gov/thredds/catalog/AMES/NEX/GDDP-CMIP6/
4. **Planetary Computer**: https://planetarycomputer.microsoft.com/dataset/nasa-nex-gddp-cmip6
5. **Copernicus GLO-30**: https://registry.opendata.aws/copernicus-dem/
6. **CDS API**: https://cds.climate.copernicus.eu/
7. **GloFAS**: https://cds.climate.copernicus.eu/datasets/cems-glofas-reforecast
8. **IBTrACS**: https://www.ncei.noaa.gov/products/international-best-track-archive
9. **SoilGrids**: https://rest.isric.org/soilgrids/v2.0/docs
10. **GEBCO**: https://www.gebco.net/data_and_products/gridded_bathymetry_data/
11. **Google Open Buildings V3**: https://sites.research.google/open-buildings/ — 1.8B footprints, GEE `GOOGLE/Research/open-buildings/v3/polygons` (**NEW v3.1**)
12. **Google Open Buildings 2.5D Temporal**: GEE `GOOGLE/Research/open-buildings-temporal/v1` — Building heights 2016-2023 (**NEW v3.1**)
13. **Overture Maps Buildings**: https://overturemaps.org/ — S3 `s3://overturemaps-us-west-2/release/`, CDLA Permissive v2 (**NEW v3.1**)
14. **JRC Global Flood Depth-Damage**: Huizinga, J. et al. (2017). *Global flood depth-damage functions*. JRC105688. https://publications.jrc.ec.europa.eu/repository/handle/JRC105688 (**NEW v3.1**)
15. **Agno**: https://docs.agno.com/
16. **DeepSeek**: https://platform.deepseek.com/
17. **Meteomatics Weather API** (evaluated, optional): https://www.meteomatics.com/en/api/getting-started/ — See `ECOSHIELD-METEOMATICS-ANALYSIS.md`

---

*EcoShield Architecture v3.2 | API-First + Structure-Level Asset Risk (H×E×V) + Gap Fixes*
