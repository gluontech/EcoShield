import asyncio
import time
from src.core.models.geometry import BoundingBox
from src.data.overture_buildings import OvertureBuildingsSource

async def main():
    lat = 10.72855516845333
    lon = 106.718741744509
    radius_m = 500
    delta_deg = radius_m / 111320.0
    bbox = BoundingBox(
        min_lat=lat - delta_deg,
        max_lat=lat + delta_deg,
        min_lon=lon - delta_deg,
        max_lon=lon + delta_deg
    )

    t0 = time.time()
    source = OvertureBuildingsSource()
    
    print("Testing Overture Maps Buildings Query...")
    buildings = source.query_buildings(bbox)
    t1 = time.time()
    print(f"query_buildings ({len(buildings)} results) took {t1 - t0:.2f} seconds")
    
    print("Testing Overture Maps Places Query...")
    places = source.query_places(bbox)
    t2 = time.time()
    print(f"query_places ({len(places)} results) took {t2 - t1:.2f} seconds")

    print("Testing Overture Maps Parts Query...")
    parts = source.query_building_parts(bbox)
    t3 = time.time()
    print(f"query_building_parts ({len(parts)} results) took {t3 - t2:.2f} seconds")

if __name__ == "__main__":
    asyncio.run(main())
