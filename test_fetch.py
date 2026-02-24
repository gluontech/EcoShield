import asyncio
import json
import os
import sys

# add src to path
sys.path.insert(0, os.path.abspath('.'))

from src.workflows.steps.asset_fetch import fetch_buildings_step

async def test_geocoding():
    with open("assess-request.json", "r") as f:
        req = json.load(f)
        
    data = {
        "lat": req["location"]["lat"],
        "lon": req["location"]["lon"],
        "name": "Sherwood",
        "building_radius_m": 500,
        "include_buildings": True,
        "city": req["city"]
    }
    
    print(f"Fetching buildings near lat={data['lat']}, lon={data['lon']}")
    result = await fetch_buildings_step(data)
    
    cluster = result.get("building_cluster")
    if cluster and cluster.buildings:
        print(f"Found {len(cluster.buildings)} buildings.")
        print("Top 5 closest buildings:")
        for b in cluster.buildings[:8]:
            dist = getattr(b, '_distance', 9999)
            name = getattr(b.footprint, 'name', '')
            wkt_snip = str(b.footprint.footprint_wkt)[:50]
            print(f"  ID: {b.footprint.building_id}, Area: {b.footprint.area_m2:.1f}, Dist: {dist:.1f}m, Name: '{name}', WKT: {wkt_snip}...")
    else:
        print("No buildings found in cluster.")

if __name__ == "__main__":
    asyncio.run(test_geocoding())
