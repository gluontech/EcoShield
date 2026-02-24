geom = {'type': 'Polygon', 'coordinates': [[[106.6895707424978, 10.786816760815604], [106.68953646432837, 10.786836848994337], [106.689522339205, 10.786813196386982], [106.68955661737222, 10.786793108217688], [106.6895707424978, 10.786816760815604]]]}
try:
    coords = geom['coordinates'][0] 
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    clon = sum(lons) / len(lons)
    clat = sum(lats) / len(lats)
    print(clon, clat)
except Exception as e:
    print("Error:", e)
