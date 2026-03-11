import json
import traceback
import asyncio
from unittest.mock import patch
from pydantic import ValidationError

from src.api.schemas.requests import AssessRequest
from src.core.models.response_models import RiskAssessmentReport
from src.api.routes.assess import assess_site

async def test():
    with open("request.json") as f:
        data = json.load(f)

    try:
        req = AssessRequest.model_validate(data)
    except Exception as e:
        print("Request validation failed:", e)
        return

    from src.core.models.asset import BuildingCluster, BuildingFootprint, StructuralCharacteristics, BuildingHeight, Location
    from src.core.models.enums import BuildingMaterial, BuildingOccupancy, VulnerabilityClass, DataSource

    mock_building = dict(
        id="mock_id_123",
        geometry_wkt="POLYGON((106.718 10.728, 106.719 10.728, 106.719 10.729, 106.718 10.729, 106.718 10.728))",
        area_m2=1000.0,
        centroid_lat=10.7285,
        centroid_lon=106.7187,
        height=15.0,
        num_floors=5,
        class_="commercial",
        subtype="shopping_mall",
        sources=[],
        names={"primary": "Crescent Mall"},
        mapped_occupancy=BuildingOccupancy.COMMERCIAL
    )

    class MockSource:
        def __init__(self, *args, **kwargs): pass
        def query_buildings(self, bbox, *args, **kwargs): return [mock_building]
        def enrich_with_osm_tags(self, b): return b
        def query_places(self, bbox, *args, **kwargs): return []
        def enrich_buildings_with_places(self, b, p, *args, **kwargs): return b
        def query_building_parts(self, bbox, *args, **kwargs): return []
        def to_structural_characteristics(self, b, *args, **kwargs):
            return [
                StructuralCharacteristics(
                    footprint=BuildingFootprint(
                        building_id="mock_id_123", source=DataSource.OVERTURE_MAPS_BUILDINGS.value,
                        centroid=Location(lat=10.7285, lon=106.7187), area_m2=1000.0,
                        footprint_wkt="POLYGON((106.718 10.728, 106.719 10.728, 106.719 10.729, 106.718 10.729, 106.718 10.728))",
                        confidence=0.8
                    ),
                    height=BuildingHeight(height_m=15.0, height_source=DataSource.OVERTURE_MAPS_BUILDINGS.value, num_floors=5),
                    material=BuildingMaterial.CONCRETE_REINFORCED,
                    occupancy=BuildingOccupancy.COMMERCIAL,
                    vulnerability_class=VulnerabilityClass.CLASS_IV_REINFORCED,
                    material_inferred=False, classification_source="osm_tags"
                )
            ]

    # Patch the OvertureBuildingsSource usage in asset_fetch
    with patch("src.data.overture_buildings.OvertureBuildingsSource", new=MockSource):
        print("\n--- Testing Response Validation (Mocked Pipeline) ---")
        try:
            res = await assess_site(req)
            print("Response validation passed!")
        except Exception as e:
            if isinstance(e, ValidationError):
                import sys
                print("Response validation failed:", file=sys.stderr)
                e_json = e.json()
                print(e_json, file=sys.stderr)
            else:
                import sys
                print("Other execution error:", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)

if __name__ == "__main__":
    asyncio.run(test())
