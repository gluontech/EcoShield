import asyncio
import json
import os
import sys

# add src to path
sys.path.insert(0, os.path.abspath('.'))

from src.workflows.steps.asset_fetch import fetch_buildings_step
from shapely.wkt import loads as load_wkt
from shapely.geometry import Point, shape
import ast

async def test_geocoding():
    with open("assess-request.json", "r") as f:
        req = json.load(f)
        
    lat = req["location"]["lat"]
    lon = req["location"]["lon"]
    data = {"lat": lat, "lon": lon, "building_radius_m": 100, "city": req["city"]}
    
    print(f"Query point: {lon}, {lat}")
    query_point = Point(lon, lat)
    
    result = await fetch_buildings_step(data)
    cluster = result.get("building_cluster")
    
    if cluster and cluster.buildings:
        # Sort by area
        buildings_sorted_by_area = sorted(cluster.buildings, key=lambda b: getattr(b.footprint, 'area_m2', 0), reverse=True)
        print(f"Total buildings unfiltered: {len(cluster.buildings)}")
        print("Top 10 buildings by area:")
        for b in buildings_sorted_by_area[:10]:
            dist = getattr(b, '_distance', 9999)
            print(f"ID: {b.footprint.building_id}, Area: {b.footprint.area_m2:.1f} m2, Conf: {b.footprint.confidence:.2f}, Dist to centroid: {dist:.1f}m")
            wkt_data = b.footprint.footprint_wkt
            try:
                if wkt_data.startswith("{"):
                    poly = shape(ast.literal_eval(wkt_data))
                else:
                    poly = load_wkt(wkt_data)
                contains = poly.contains(query_point)
                dist_to_poly = poly.distance(query_point)
                print(f"  Contains point? {contains}, Distance to poly: {dist_to_poly} degrees")
            except Exception as e:
                print(f"  Error parsing geometry: {e}")
                    
if __name__ == "__main__":
    asyncio.run(test_geocoding())
