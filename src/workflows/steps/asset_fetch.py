
import asyncio
import logging
from typing import Dict, Any, List

from src.core.models.geometry import BoundingBox
from src.core.models.surface import BuildingAdjustedSurface
from src.core.models.asset import BuildingCluster
from src.core.models.enums import (
    BuildingOccupancy, StructureCategory, StructureType,
)
from src.data.open_buildings import OpenBuildingsSource
from src.data.elevation import get_elevation, get_elevation_footprint
from src.data.spatial_matcher import SpatialMatcher, SpatialMatchContext
from src.data.structure_expectations import get_expectation
from src.config.settings import settings

logger = logging.getLogger(__name__)


async def fetch_buildings_step(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 0: Fetch buildings + spatially match + create BuildingAdjustedSurface.

    Inputs:
        data["lat"]: float
        data["lon"]: float
        data["building_radius_m"]: int
        data["include_buildings"]: bool (optional)
        data["name"]: str (optional — building name for matching)
        data["address"]: str (optional — address for matching)
        data["structure_category"]: str (optional — residential/commercial/industrial)
        data["structure_type"]: str (optional — hotel, tube_house, etc.)

    Outputs:
        data["building_cluster"]: BuildingCluster
        data["building_surfaces"]: Dict[str, BuildingAdjustedSurface]
    """
    lat = data["lat"]
    lon = data["lon"]
    req_name = (data.get("name") or "").lower().strip()
    req_address = (data.get("address") or "").lower().strip()
    radius_m = data.get("building_radius_m", 500)
    include_buildings = data.get("include_buildings", True)

    # Parse structure hints
    raw_cat = data.get("structure_category")
    raw_type = data.get("structure_type")
    structure_category = StructureCategory(raw_cat) if raw_cat else None
    structure_type = StructureType(raw_type) if raw_type else None
    
    # Premium user-provided enrichment fields
    req_roof = data.get("roof_type")
    req_wall = data.get("wall_material")
    req_gfh = data.get("ground_floor_height_m")
    req_floors = data.get("num_floors")

    # Initialize connection to asset source
    asset_source = OpenBuildingsSource(db_url=settings.DATABASE_URL)

    if not include_buildings:
        logger.info("Building fetch skipped (include_buildings=False)")
        data["building_cluster"] = None
        data["building_surfaces"] = {}
        return data

    # 1. Compute BBox from radius
    delta_deg = radius_m / 111320.0
    bbox = BoundingBox(
        min_lat=lat - delta_deg,
        max_lat=lat + delta_deg,
        min_lon=lon - delta_deg,
        max_lon=lon + delta_deg
    )

    # ------------------------------------------------------------------
    # Fetch buildings from data sources
    # ------------------------------------------------------------------
    overture_source = None
    places = []
    building_parts = []

    async def fetch_overture(search_bbox, enrich_places=False):
        nonlocal overture_source, places
        try:
            from src.data.overture_buildings import OvertureBuildingsSource
            overture_source = OvertureBuildingsSource()
            raw_buildings = await asyncio.to_thread(
                overture_source.query_buildings, bbox=search_bbox,
            )
            if raw_buildings:
                enriched = overture_source.enrich_with_osm_tags(raw_buildings)
                if enrich_places:
                    try:
                        places = await asyncio.to_thread(
                            overture_source.query_places, bbox=search_bbox,
                        )
                        if places:
                            enriched = overture_source.enrich_buildings_with_places(
                                enriched, places,
                            )
                    except Exception as e:
                        logger.warning(f"Overture places enrichment failed (non-fatal): {e}")
                return overture_source.to_structural_characteristics(enriched)
        except Exception as e:
            logger.error(f"Overture Maps fetch failed: {e}")
        return []

    structures = []
    overture_tried = False

    # If the user is specifically trying to match a building by name or address,
    # we MUST use Overture Maps first because Google Open Buildings lacks metadata.
    if req_name or req_address:
        logger.info("Name/address provided. Prioritizing Overture Maps for metadata matching.")
        structures = await fetch_overture(bbox, enrich_places=True)
        overture_tried = True

    # 2. Fetch from default source (Google) if we haven't found anything yet
    if not structures:
        logger.info(f"Fetching buildings in bbox {bbox} from default source...")
        structures = await asset_source.get_buildings_in_bbox(bbox)

    # Fallback to Overture Maps if Google returns empty (and we haven't tried yet)
    if not structures and not overture_tried:
        logger.info("Google Open Buildings returned no results. Attempting Overture Maps fallback...")
        structures = await fetch_overture(bbox)

    logger.info(f"Fetched {len(structures)} buildings total")

    # 3. Fetch building parts for complex structures (when metadata hints available)
    if (req_name or req_address or structure_type) and overture_source:
        try:
            building_parts = await asyncio.to_thread(
                overture_source.query_building_parts, bbox=bbox,
            )
            if building_parts:
                logger.info(f"Fetched {len(building_parts)} building parts")
        except Exception as e:
            logger.warning(f"Building parts fetch failed (non-fatal): {e}")

    # 3.5. Enrich Overture buildings with GEE heights if missing
    if overture_tried and structures and asset_source._gee_available:
        try:
            import ee
            from src.core.models.asset import BuildingHeight
            from src.core.models.enums import (
                DataSource, BuildingMaterial, VulnerabilityClass,
            )
            
            logger.info("Enriching Overture buildings with Google Earth Engine heights...")
            height_image = await asyncio.to_thread(asset_source._fetch_heights_gee, bbox, 2023)
            
            if height_image is not None:
                # convert wkt to GEE geometry
                from shapely.wkt import loads as load_wkt
                features = []
                for i, st in enumerate(structures):
                    if st.height is None and st.footprint.footprint_wkt:
                        try:
                            poly = load_wkt(st.footprint.footprint_wkt)
                            # simple bounds or centroid since Full polygon might fail GEE limits
                            geom = ee.Geometry.Point([st.footprint.centroid.lon, st.footprint.centroid.lat])
                            features.append(ee.Feature(geom, {'idx': i}))
                        except Exception:
                            pass
                
                if features:
                    fc = ee.FeatureCollection(features)
                    stats = await asyncio.to_thread(
                        lambda: height_image.reduceRegions(
                            collection=fc,
                            reducer=ee.Reducer.mean(),
                            scale=4
                        ).getInfo()
                    )
                    
                    enriched_indices: list[int] = []
                    for f in stats.get('features', []):
                        props = f.get('properties', {})
                        idx = props.get('idx')
                        h = props.get('building_height')
                        p = props.get('building_presence', 1.0)
                        
                        if idx is not None and h is not None:
                            structures[idx].height = BuildingHeight(
                                height_m=h,
                                height_source=DataSource.GOOGLE_OPEN_BUILDINGS_V3,
                                height_year=2023,
                                building_presence=p
                            )
                            enriched_indices.append(idx)

                    # Re-infer material/vulnerability for structures that
                    # just received GEE height.  The initial inference in
                    # to_structural_characteristics() could not see height
                    # data, so it fell back to the SEA masonry default.
                    for idx in enriched_indices:
                        st = structures[idx]
                        height_m = st.height.height_m if st.height else None
                        area_m2 = st.footprint.area_m2

                        if height_m and height_m > 15:
                            st.material = BuildingMaterial.CONCRETE_REINFORCED
                            st.vulnerability_class = VulnerabilityClass.CLASS_IV_REINFORCED
                        elif area_m2 > 1000:
                            st.material = BuildingMaterial.CONCRETE_REINFORCED
                            st.vulnerability_class = VulnerabilityClass.CLASS_IV_REINFORCED

                        # Keep classification_source updated
                        if st.material != BuildingMaterial.MASONRY_UNREINFORCED:
                            st.classification_source = "area_height_inference"

        except Exception as e:
            logger.warning(f"Failed to enrich heights from GEE (non-fatal): {e}")

    # ------------------------------------------------------------------
    # Multi-stage spatial matching
    # ------------------------------------------------------------------
    matcher = SpatialMatcher()
    context = SpatialMatchContext(
        name=req_name,
        address=req_address,
        structure_category=structure_category,
        structure_type=structure_type,
        city=data.get("city", "unknown"),
    )

    match_results = matcher.match(
        lat, lon, structures,
        building_parts=building_parts or None,
        places=places or None,
        context=context,
    )

    # Apply match results back to structures
    matched_structures = []
    for mr in match_results:
        fp = mr.structure.footprint
        fp.footprint_match_confidence = mr.confidence
        fp.match_method = mr.match_method
        mr.structure.poi_validated = mr.poi_validated
        matched_structures.append(mr.structure)

    structures = matched_structures
    logger.info(f"Kept {len(structures)} buildings after spatial matching")

    # ------------------------------------------------------------------
    # Infer occupancy from request structure category / type
    # ------------------------------------------------------------------
    # When the request specifies a structure type (e.g. shopping_mall) or
    # category (e.g. commercial), use the StructureExpectation table to
    # derive the expected occupancy and apply it to matched structures
    # that still have UNKNOWN occupancy.  This drives the occupancy-aware
    # floor-to-floor height used for story estimation.
    expectation = get_expectation(structure_type, structure_category)
    if expectation and structures:
        inferred_occ = expectation.expected_occupancy
        for st in structures:
            if st.occupancy == BuildingOccupancy.UNKNOWN:
                st.occupancy = inferred_occ
                # Re-sync estimated_stories with the new occupancy so
                # the floor-to-floor height ratio is correct.
                if st.height is not None:
                    st.height.estimated_stories = st.num_stories
        logger.info(
            f"inferred occupancy '{inferred_occ.value}' from request "
            f"structure type/category"
        )
        
    # ------------------------------------------------------------------
    # Apply Premium User-Provided Fields
    # ------------------------------------------------------------------
    if structures:
        for st in structures:
            if req_roof is not None:
                st.roof_type = req_roof.value if hasattr(req_roof, "value") else req_roof
            if req_wall is not None:
                st.wall_material = req_wall.value if hasattr(req_wall, "value") else req_wall
            if req_gfh is not None:
                st.ground_floor_height_m = float(req_gfh)
            if req_floors is not None:
                if st.height is None:
                    from src.core.models.asset import BuildingHeight
                    from src.core.models.enums import DataSource
                    # Estimate height from floor count rather than emitting a
                    # synthetic zero, which would fail downstream validators
                    # that enforce height_m > 0.  Use a conservative 3.5 m
                    # floor-to-floor ratio (SEA default; occupancy-aware
                    # refinement is applied later by StructuralCharacteristics).
                    _estimated_h = max(float(req_floors) * 3.5, 1.0)
                    st.height = BuildingHeight(
                        height_m=_estimated_h,
                        height_source=DataSource.OVERTURE_MAPS_BUILDINGS,
                        height_year=2023,
                        height_uncertainty_m=2.0,  # higher uncertainty for synthetic estimate
                        building_presence=1.0,
                    )
                st.height.num_floors = int(req_floors)
                st.height.estimated_stories = int(req_floors)
                
    # ------------------------------------------------------------------
    # Build cluster + elevation surfaces
    # ------------------------------------------------------------------
    tile_id = f"tile_{lat:.4f}_{lon:.4f}"

    cluster = BuildingCluster(
        tile_id=tile_id,
        bounds=bbox,
        buildings=structures
    )

    # 4. Create BuildingAdjustedSurface for each building (Gap S)
    # Use footprint-based median elevation when WKT polygon available,
    # fall back to centroid single-pixel sampling.

    async def _fetch_elev(building):
        centroid = building.footprint.centroid
        wkt = building.footprint.footprint_wkt
        try:
            if wkt and not wkt.startswith("{"):
                elev = await get_elevation_footprint(wkt)
            else:
                elev = await get_elevation(centroid.lat, centroid.lon)
        except Exception:
            elev = await get_elevation(centroid.lat, centroid.lon)
        return building.footprint.building_id, elev

    elev_results = await asyncio.gather(*[_fetch_elev(b) for b in structures])
    surfaces = {}
    for st, (bid, elev) in zip(structures, elev_results):
        surfaces[bid] = BuildingAdjustedSurface(
            building_id=bid,
            original_elevation_m=elev,
        )
        # Fix missing ground elevation fields on the structure
        st.ground_elevation_m = elev

    data["building_cluster"] = cluster
    data["building_surfaces"] = surfaces

    return data
