import sys
import json
import logging

logging.basicConfig(level=logging.INFO)
sys.path.append('/home/bim/code/EcoShield')

from src.data.overture_buildings import OvertureBuildingsSource
from src.core.models.geometry import BoundingBox
import math

src = OvertureBuildingsSource()

# Location
lat = 10.72567492110698
lon = 106.72417564681965

# 1000m roughly
bbox = BoundingBox(
    min_lat=lat - 0.01,
    max_lat=lat + 0.01,
    min_lon=lon - 0.01,
    max_lon=lon + 0.01
)

buildings = src.query_buildings(bbox, limit=10000)
places = src.query_places(bbox, limit=10000)

for p in places:
    # check string for waterfront
    pstr = str(p).lower()
    if 'waterfront' in pstr:
        print("FOUND POI:", p)

for b in buildings:
    bstr = str(b).lower()
    if 'waterfront' in bstr:
        print("FOUND BUILDING:", b)
