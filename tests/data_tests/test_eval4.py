import rasterio
from rasterio.mask import mask
import numpy as np
from shapely.wkt import loads as load_wkt

wkt = "POLYGON ((106.7194559 10.7288345, 106.7191344 10.7293515, 106.7191091 10.7293373, 106.7190814 10.7293764, 106.7190308 10.7294001, 106.718979 10.7294024, 106.7189164 10.7293847, 106.7188694 10.7293539, 106.7188297 10.7293054, 106.7188032 10.7292415, 106.7187273 10.729109, 106.7186214 10.7289504, 106.7185166 10.7288167, 106.7184275 10.7287197, 106.7183396 10.7286345, 106.7182047 10.7285138, 106.7181469 10.72847, 106.718124 10.7284369, 106.7181071 10.7283872, 106.718112 10.7283399, 106.7181373 10.7282997, 106.7181782 10.728276, 106.7182324 10.7282642, 106.7182902 10.7282772, 106.7183492 10.7281707, 106.7194559 10.7288345))"
poly = load_wkt(wkt)
src = rasterio.open('data/cache/copernicus-dem/Copernicus_DSM_COG_10_N10_00_E106_00_DEM.tif')
geojson = [poly.__geo_interface__]
out_image, _ = mask(src, geojson, crop=True, nodata=src.nodata)
valid = out_image.flatten()
print("original length:", len(valid))
if src.nodata is not None:
    valid = valid[valid != src.nodata]
print("after strip nodata:", len(valid))
valid = valid[valid > -1000]
print("after strip < -1000:", len(valid))
print("median:", np.median(valid), "mean:", np.mean(valid), "min:", np.min(valid), "max:", np.max(valid))
