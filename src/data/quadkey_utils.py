import math

def latlon_to_tile(lat, lon, zoom):
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile

def tile_to_quadkey(xtile, ytile, zoom):
    quadkey = ""
    for i in range(zoom, 0, -1):
        digit = 0
        mask = 1 << (i - 1)
        if (xtile & mask) != 0:
            digit += 1
        if (ytile & mask) != 0:
            digit += 2
        quadkey += str(digit)
    return quadkey

def get_quadkeys_for_bbox(min_lat, max_lat, min_lon, max_lon, zoom=8):
    min_x, max_y = latlon_to_tile(min_lat, min_lon, zoom)
    max_x, min_y = latlon_to_tile(max_lat, max_lon, zoom)
    
    # Ensure min/max are correct in case of wrap-around or negative 
    start_x = min(min_x, max_x)
    end_x = max(min_x, max_x)
    start_y = min(min_y, max_y)
    end_y = max(min_y, max_y)
    
    quadkeys = []
    for x in range(start_x, end_x + 1):
        for y in range(start_y, end_y + 1):
            quadkeys.append(tile_to_quadkey(x, y, zoom))
    return quadkeys

print(get_quadkeys_for_bbox(10.72, 10.73, 106.71, 106.72, zoom=8))
