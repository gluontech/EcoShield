import sys
import json
import logging

logging.basicConfig(level=logging.INFO)
sys.path.append('/home/bim/code/EcoShield')

from src.data.overture_buildings import OvertureBuildingsSource
from src.core.models.geometry import BoundingBox
import math
from shapely.wkt import loads as load_wkt
from shapely.geometry import Point

src = OvertureBuildingsSource()

lat = 10.72567492110698
lon = 106.72417564681965

bbox = BoundingBox(
    min_lat=lat - 0.005,
    max_lat=lat + 0.005,
    min_lon=lon - 0.005,
    max_lon=lon + 0.005
)

buildings = src.query_buildings(bbox)
places = src.query_places(bbox)

buildings_enriched = src.enrich_buildings_with_places(buildings, places)
buildings_enriched = src.enrich_with_osm_tags(buildings_enriched)

query_pt = Point(lon, lat)

for b in buildings_enriched:
    wkt = b.get('geometry_wkt')
    name = b.get('name_primary')
    
    contains = False
    dist_to_poly = -1
    if wkt:
        try:
            poly = load_wkt(wkt)
            contains = poly.contains(query_pt)
            dist_to_poly = poly.distance(query_pt) * 111320.0
        except Exception:
            pass
            
    if name == 'Midtown Premium Apartments' or contains:
        print(f"[{b.get('id')}] {name}")
        print(f"  Contains pt: {contains}, Dist to boundary: {dist_to_poly:.1f}")
