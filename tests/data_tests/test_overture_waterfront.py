import sys
import json
import logging

logging.basicConfig(level=logging.INFO)
sys.path.append('/home/bim/code/EcoShield')

from src.data.overture_buildings import OvertureBuildingsSource
from src.core.models.geometry import BoundingBox
import math

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

def _haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

for b in buildings_enriched:
    blat = b.get('centroid_lat', 0)
    blon = b.get('centroid_lon', 0)
    dist = _haversine(lat, lon, blat, blon)

    if dist < 150:
        area = b.get('area_m2', 0)
        num_floors = b.get('num_stories', 0)
        primary_name = b.get('name_primary')
        print(f"[{b.get('id')}] {primary_name} ({area:.1f}m2, {num_floors}fl) - dist: {dist:.1f}m")
