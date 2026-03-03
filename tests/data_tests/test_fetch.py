import sys
import asyncio
import json
import logging

logging.basicConfig(level=logging.INFO)

sys.path.append('/home/bim/code/EcoShield')
from src.workflows.steps.asset_fetch import fetch_buildings_step

with open('/home/bim/code/EcoShield/request.json', 'r') as f:
    req_data = json.load(f)

# The request.json has layout:
# { "location": { "lat": ..., "lon": ... } ... }
# Let's map it to what fetch_buildings_step expects
step_data = {
    "lat": req_data["location"]["lat"],
    "lon": req_data["location"]["lon"],
    "name": req_data["location"]["name"],
    "address": req_data["location"]["address"],
    "structure_category": req_data["location"]["structure_category"],
    "structure_type": req_data["location"]["structure_type"],
    "building_radius_m": 500
}

async def run():
    print("Running fetch_buildings_step...")
    res = await fetch_buildings_step(step_data)
    cluster = res.get("building_cluster")
    if cluster and cluster.buildings:
        best_bldg = cluster.buildings[0]
        print("Best match building:")
        print("  Confidence:", best_bldg.footprint.footprint_match_confidence)
        print("  Name:", best_bldg.footprint.name)
        print("  Ground Elevation:", best_bldg.ground_elevation_m)
        print("  Height M:", best_bldg.height.height_m if best_bldg.height else "None")
    else:
        print("No buildings returned.")

asyncio.run(run())
