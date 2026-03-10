import duckdb
import time

lat = 10.72855516845333
lon = 106.718741744509
radius_m = 500
delta_deg = radius_m / 111320.0
bbox = (lon - delta_deg, lat - delta_deg, lon + delta_deg, lat + delta_deg)

print("Starting duckdb query directly on Overture Maps...")
t0 = time.time()
try:
    conn = duckdb.connect()
    conn.execute("INSTALL spatial; LOAD spatial;")
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    conn.execute("SET s3_region='us-west-2';")
    
    # Try the raw SQL instead of the python library
    query = f"""
    SELECT id, geometry
    FROM read_parquet('s3://overturemaps-us-west-2/release/2024-12-11.0/theme=buildings/type=building/*', filename=true, hive_partitioning=1)
    WHERE bbox.minx > {bbox[0]} AND bbox.miny > {bbox[1]} 
      AND bbox.maxx < {bbox[2]} AND bbox.maxy < {bbox[3]}
    LIMIT 10;
    """
    res = conn.execute(query).fetchall()
    print(f"Success! Num rows: {len(res)}")
except Exception as e:
    print(f"Failed with exception: {e}")
print(f"Time taken: {time.time() - t0:.2f}s")
