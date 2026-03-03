import duckdb
conn = duckdb.connect()
conn.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
print(conn.execute("SELECT * FROM glob('s3://overturemaps-us-west-2/release/2026-01-21.0/theme=buildings/type=*/*') LIMIT 5").fetchall())
