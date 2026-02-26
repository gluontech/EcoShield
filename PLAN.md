# Multi-Stage Spatial Matching — Implementation Plan

## Problem

In dense SEA cities (HCMC, Jakarta, Bangkok, Manila), the current centroid-based building
lookup is unreliable. Input `(lat, lon)` → find nearest centroid → return that footprint
fails when:

- Point falls near edge between adjacent polygons
- Small building sits next to a large tower
- Multi-part building geometries (podium + tower)
- Overlapping footprints (vertical stacking)
- Point offset 3–15m due to geocoding/GPS error

**Current code flow:**
1. `asset_fetch.py` computes a bounding box, fetches ALL buildings in bbox
2. For each building: haversine distance to centroid, shapely containment check (sets dist=0),
   name/address transliteration bonus (-200m/-100m)
3. Sort by adjusted distance, return sorted list

**No multi-stage fallback, no confidence scoring, no buffer intersection, no building parts.**

---

## Architecture Overview

Create a new dedicated module `src/data/spatial_matcher.py` that encapsulates the full
multi-stage matching pipeline. Refactor `asset_fetch.py` to call this module instead of
inlining its own distance/containment logic.

### Data Flow (After)

```
(lat, lon, name, address, asset_type)
    → OvertureBuildingsSource.query_buildings(bbox)          [existing]
    → OvertureBuildingsSource.query_building_parts(bbox)     [NEW - Step 4]
    → OvertureBuildingsSource.query_places(bbox)             [existing]
    → SpatialMatcher.match(point, buildings, parts, places, context)  [NEW]
        → Stage 1: Polygon containment + POI cross-check
        → Stage 2: Buffer intersection (3m adaptive)
        → Stage 3: Confidence scoring & ranking
        → Stage 4: Building part preference
        → Stage 5: Vertical stacking resolution
        → Stage 6: QA rejection + retry
    → Return ranked list with footprint_match_confidence
    → elevation.py: footprint-based median sampling          [ENHANCED - Step 5]
```

---

## File Changes

### 1. NEW: `src/data/spatial_matcher.py` (~300 lines)

Core spatial matching engine. Isolates all matching logic from the workflow step.

```python
class SpatialMatchResult:
    structure: StructuralCharacteristics
    confidence: float           # 0.0–1.0
    match_method: str           # "containment", "buffer_overlap", "confidence_scored"
    containment: bool           # True if point inside polygon
    overlap_ratio: float        # 0.0–1.0 (buffer overlap / footprint area)
    centroid_distance_m: float  # haversine to centroid
    name_matched: bool
    address_matched: bool
    poi_validated: bool         # True if POI layer confirms building type

class SpatialMatchContext:
    name: str                   # requested building name
    address: str                # requested address
    asset_type: str             # "hotel", "commercial", etc.
    city: str

class SpatialMatcher:
    def match(
        self,
        lat: float, lon: float,
        buildings: List[StructuralCharacteristics],
        building_parts: List[Dict],  # raw Overture building_part rows
        places: List[Dict],          # Overture POI data
        context: SpatialMatchContext,
    ) -> List[SpatialMatchResult]:
        """Multi-stage spatial matching pipeline."""
```

**Stage 1 — Polygon Containment + POI Cross-check** (lines ~50–120)
- For each building with WKT, check `polygon.contains(query_point)`
- If exactly 1 match → return it (confidence=0.95)
- If multiple matches → POI cross-check:
  - Find Overture places within 30m of query point
  - If a place name matches `context.name`, prefer the building whose polygon
    contains that place's centroid
  - If still ambiguous → pass all to Stage 3 (confidence scoring)

**Stage 2 — Buffer Intersection** (lines ~120–180)
- If Stage 1 found 0 matches (point not inside any polygon):
  - Create 3m buffer around query point (Shapely `point.buffer(3m_in_degrees)`)
  - Adaptive: if `context.name` suggests large building (hotel, mall), use 10m
  - `polygon.intersection(buffer)` for each candidate
  - Sort by intersection area descending
  - Take candidates with overlap > 0
  - If exactly 1 → return (confidence = 0.85 * overlap_ratio)
  - If multiple → pass to Stage 3

**Stage 3 — Confidence Scoring** (lines ~180–280)
- For all remaining candidates, compute weighted score:
  ```
  score = (
      containment * 0.40 +
      overlap_ratio * 0.25 +
      (1 / (1 + distance_m)) * 0.15 +
      height_similarity * 0.10 +
      footprint_plausibility * 0.10
  )
  ```
  Where:
  - `containment`: 1.0 if point inside polygon, else 0.0
  - `overlap_ratio`: intersection_area / footprint_area (from Stage 2 buffer)
  - `distance_m`: haversine from point to polygon centroid
  - `height_similarity`: 1.0 if no height context; else `1 - abs(expected - actual) / expected`
    (expected derived from asset_type: hotel→30m, residential→9m, etc.)
  - `footprint_plausibility`: 1.0 if area matches asset_type expectations;
    0.3 if "hotel" but area < 100m²; sigmoid scaling

- Name/address matching applied as tie-breaker multiplier (not distance hack):
  - Name match: score *= 1.5
  - Address match: score *= 1.3

- Reject candidates with score < 0.6
- Return sorted by score descending, attach `footprint_match_confidence`

**Stage 4 — Building Part Preference** (integrated into Stage 1)
- When multiple polygons contain the point:
  - Separate into `building` vs `building_part` types
  - If any `building_part` contains the point → prefer it (smaller, more specific polygon)
  - Fall back to parent `building` if no part contains point
  - This handles podium + tower stacking naturally

**Stage 5 — Vertical Stacking Resolution** (integrated into Stage 3)
- When multiple overlapping polygons detected:
  - Prefer the **smallest** polygon containing the point (tower > podium)
  - Unless height context suggests otherwise:
    if expected_height < 15m, prefer the larger polygon (likely the low-rise part)
  - Add 0.1 bonus to smaller-polygon candidates in scoring

**Stage 6 — QA Rejection + Retry** (lines ~280–330)
- After scoring, validate best match:
  - If `area_m2 < 50` AND `context.name` contains "hotel"/"mall"/"tower" → flag mismatch
  - If `num_stories < 2` AND `context.asset_type == "commercial"` → flag
  - If `building_presence < 0.8` → flag
  - If `footprint_match_confidence < 0.7` → flag
- On mismatch:
  - Expand buffer to 30m → re-run Stage 2 with wider search
  - Re-score with Stage 3
  - If still no good match → return best candidate with low confidence flag

### 2. MODIFY: `src/data/overture_buildings.py` (~80 new lines)

**Add `query_building_parts()` method** (new, ~40 lines)
```python
OVERTURE_BUILDING_PARTS_PATH = f"{OVERTURE_S3_BASE}/theme=buildings/type=building_part/"

def query_building_parts(self, bbox: BoundingBox, limit: int = 10000) -> List[Dict]:
    """Query Overture building_part polygons for complex structures."""
    query = f"""
    SELECT
        id,
        ST_AsText(geometry) AS geometry_wkt,
        ST_Area_Spheroid(geometry) AS area_m2,
        ST_Y(ST_Centroid(geometry)) AS centroid_lat,
        ST_X(ST_Centroid(geometry)) AS centroid_lon,
        height,
        num_floors,
        building_id    -- parent building reference
    FROM read_parquet('{OVERTURE_BUILDING_PARTS_PATH}*.parquet', hive_partitioning=1)
    WHERE bbox.xmin >= {bbox.min_lon}
      AND bbox.xmax <= {bbox.max_lon}
      AND bbox.ymin >= {bbox.min_lat}
      AND bbox.ymax <= {bbox.max_lat}
    LIMIT {limit}
    """
```

**Add `query_buildings_containing_point()` method** (new, ~30 lines)
- Push containment check to DuckDB for efficiency with large datasets:
```python
def query_buildings_containing_point(self, lat: float, lon: float, buffer_m: float = 0) -> List[Dict]:
    """Find buildings whose polygon contains (or is within buffer of) a point."""
    query = f"""
    SELECT ...
    FROM read_parquet(...)
    WHERE ST_Contains(geometry, ST_Point({lon}, {lat}))
       OR ST_DWithin(geometry, ST_Point({lon}, {lat}), {buffer_deg})
    """
```
Note: This pushdown is an optimization. The primary containment logic lives in
SpatialMatcher using Shapely (works on the already-fetched bbox results).

### 3. MODIFY: `src/workflows/steps/asset_fetch.py` (~100 lines changed)

**Refactor `fetch_buildings_step()`:**
- Remove inline distance/containment/name-matching logic (lines 121–225)
- Replace with call to `SpatialMatcher.match()`
- Add building_parts fetch when name/address provided
- Pass POI places data to matcher

Key changes:
```python
from src.data.spatial_matcher import SpatialMatcher, SpatialMatchContext

# After fetching buildings + places:
matcher = SpatialMatcher()
context = SpatialMatchContext(
    name=req_name, address=req_address,
    asset_type=data.get("asset_type", ""),
    city=data.get("city", "unknown"),
)

# Fetch building parts for complex structures (only when name/address hint)
building_parts = []
if req_name or req_address:
    building_parts = await asyncio.to_thread(
        overture_source.query_building_parts, bbox=bbox
    )

match_results = matcher.match(lat, lon, structures, building_parts, places, context)

# Convert to structures list, attach confidence
structures = []
for mr in match_results:
    mr.structure.footprint.confidence = mr.confidence  # footprint_match_confidence
    structures.append(mr.structure)
```

### 4. MODIFY: `src/data/elevation.py` (~60 new lines)

**Add footprint-based median elevation sampling:**

```python
def _read_elevation_footprint_sync(wkt_polygon: str) -> float:
    """Sample median elevation across a building footprint polygon.

    Instead of single-pixel at centroid, clips the DEM to the footprint
    and returns the median value. Handles:
    - Height raster misalignment (±5m shift)
    - Mixed pixel bleed at polygon edges
    - DEM void fill (nodata pixels excluded from median)
    """
    from shapely.wkt import loads as load_wkt
    from rasterio.mask import mask as rio_mask

    poly = load_wkt(wkt_polygon)
    centroid = poly.centroid
    dem_path = _get_dem_path(centroid.y, centroid.x)
    if not dem_path:
        return 0.0

    src = _get_cached_dataset(dem_path)
    # Convert shapely polygon to GeoJSON for rasterio mask
    geojson = [poly.__geo_interface__]
    out_image, _ = rio_mask(src, geojson, crop=True, nodata=src.nodata)
    valid = out_image[out_image != src.nodata]
    valid = valid[valid > -1000]

    if len(valid) == 0:
        # Fallback to centroid single-pixel
        return _read_elevation_sync(centroid.y, centroid.x)

    return float(np.median(valid))


async def get_elevation_footprint(wkt_polygon: str) -> float:
    """Get median elevation across a building footprint polygon."""
    return await asyncio.to_thread(_read_elevation_footprint_sync, wkt_polygon)
```

**Update `asset_fetch.py` elevation calls:**
- When WKT polygon available: use `get_elevation_footprint(wkt)`
- Fallback to `get_elevation(lat, lon)` if no polygon

### 5. MODIFY: `src/core/models/asset.py` (~25 new lines)

**Add `footprint_match_confidence` field to BuildingFootprint:**
```python
footprint_match_confidence: float = Field(
    default=0.0, ge=0.0, le=1.0,
    description="Confidence that this footprint is the correct building (0.0–1.0)"
)
match_method: Optional[str] = Field(
    None,
    description="How this building was matched: containment, buffer_overlap, confidence_scored"
)
```

**Add match context fields to StructuralCharacteristics:**
```python
poi_validated: bool = Field(
    default=False,
    description="True if Overture POI cross-check confirmed building type"
)
```

### 6. MODIFY: `src/api/schemas/requests.py` (~5 lines)

**Add `asset_type` to Location/AssessRequest** (if not already present):
```python
asset_type: Optional[str] = Field(
    None,
    description="Expected building type: hotel, commercial, residential, industrial"
)
```
This enables plausibility checks in the confidence scoring model.

---

## Implementation Order

1. **`src/core/models/asset.py`** — Add new fields first (other modules depend on models)
2. **`src/api/schemas/requests.py`** — Add `asset_type` parameter
3. **`src/data/overture_buildings.py`** — Add `query_building_parts()` method
4. **`src/data/spatial_matcher.py`** — NEW: Core matching engine (largest piece)
5. **`src/workflows/steps/asset_fetch.py`** — Refactor to use SpatialMatcher
6. **`src/data/elevation.py`** — Add footprint-based median elevation

Steps 1-3 can be done first (foundation). Step 4 is the core work. Steps 5-6 integrate everything.

---

## What This Does NOT Include (Out of Scope)

- **Step 6 from proposal (Street Network Constraint)**: Requires OSM road network data
  from Overture transportation theme. This adds significant query overhead and a new data
  dependency. Recommend deferring to a follow-up PR — the confidence scoring model already
  handles most edge cases that street proximity would catch. Can be added as an optional
  Stage 3 scoring factor later.

- **PostGIS spatial indexing**: Current architecture uses DuckDB for S3 Parquet queries.
  Pushing ST_Contains to DuckDB works but is slower than a PostGIS R-tree index.
  The `query_buildings_containing_point()` DuckDB method is included as an optimization
  hint, but the primary path uses Shapely on already-fetched bbox results (which works
  well for the typical 500m search radius returning <5000 buildings).

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Building parts parquet path may differ | Verify path against Overture schema docs; graceful fallback to buildings-only |
| Shapely buffer in degrees vs meters | Convert meters to degrees using lat-adjusted factor: `buffer_deg = buffer_m / (111320 * cos(lat))` |
| Confidence threshold 0.6 may reject valid matches | Make threshold configurable; log rejections for tuning |
| DEM rasterio.mask on small polygons may return empty | Fallback to centroid single-pixel sampling |
| Performance: multi-stage adds latency | Stages are sequential but each is O(n) on already-fetched buildings; total <100ms for typical queries |
