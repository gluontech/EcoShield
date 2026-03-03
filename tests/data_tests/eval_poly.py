import json
from shapely.geometry import Point, shape
import ast

with open('response.json', 'r') as f:
    data = json.load(f)

# Input coordinate
lat = data['location']['lat']
lon = data['location']['lon']
pt = Point(lon, lat)

bldg = data['hazards'][0]['details']['exposure']['structure']['footprint']
wkt_str = bldg['footprint_wkt']

# Parse WKT string. It is stringified dict
poly_dict = ast.literal_eval(wkt_str)
poly = shape(poly_dict)

print(f"Query point: {lon}, {lat}")
print(f"Building ID picked: {bldg['building_id']}")
print(f"Building area: {bldg['area_m2']}")
print(f"Contains point? {poly.contains(pt)}")
print(f"Distance to polygon: {poly.distance(pt)} degrees")
print(f"Polygon centroid: {poly.centroid.x}, {poly.centroid.y}")

print("---")
# Also load assess-request
with open('assess-request.json', 'r') as f:
    req = json.load(f)
req_lat = req['location']['lat']
req_lon = req['location']['lon']
print(f"Original Request point: {req_lon}, {req_lat}")
req_pt = Point(req_lon, req_lat)
print(f"Distance from req_pt to this poly: {poly.distance(req_pt)} degrees")

