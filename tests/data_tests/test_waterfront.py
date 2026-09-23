import sys
import asyncio
import json
import logging

logging.basicConfig(level=logging.INFO)

sys.path.append('/home/bim/code/EcoShield')
from src.workflows.steps.asset_fetch import fetch_buildings_step

from pathlib import Path

req_file = Path('/home/bim/code/EcoShield/request.json')
if req_file.exists():
    with open(req_file, 'r') as f:
        req_data = json.load(f)

    step_data = {
        "lat": req_data["location"]["lat"],
        "lon": req_data["location"]["lon"],
        "name": req_data["location"]["name"],
        "address": req_data["location"]["address"],
        "structure_category": req_data["location"]["structure_category"],
        "structure_type": req_data["location"]["structure_type"],
        "building_radius_m": 500
    }
else:
    step_data = {}

async def run():
    print("Running fetch_buildings_step for Waterfront...")
    res = await fetch_buildings_step(step_data)
    cluster = res.get("building_cluster")
    if cluster and cluster.buildings:
        for b in cluster.buildings:
            print("Confidence:", b.footprint.footprint_match_confidence, "Name:", b.footprint.name, "ID:", b.footprint.building_id, "Dist (approx):")
    else:
        print("No buildings returned.")

if __name__ == "__main__":
    asyncio.run(run())

