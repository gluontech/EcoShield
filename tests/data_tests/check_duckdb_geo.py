import duckdb
conn = duckdb.connect()
conn.execute("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
query = """
SELECT
    id,
    typeof(geometry) as geo_type,
    ST_AsText(geometry) as wkt,
    ST_Area_Spheroid(geometry) as area
FROM read_parquet('s3://overturemaps-us-west-2/release/2026-01-21.0/theme=buildings/type=building/*.parquet', hive_partitioning=1)
LIMIT 5
"""
res = conn.execute(query).fetchall()
for r in res:
    print(r)
