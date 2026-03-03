import numpy as np
lat_min, lat_max, lon_min, lon_max = (10.3, 11.2, 106.3, 107.1)
print(list(range(int(np.floor(lat_min)), int(np.ceil(lat_max)))))
print(list(range(int(np.floor(lon_min)), int(np.ceil(lon_max)))))
