import overturemaps
import duckdb
bbox = (106.71, 10.72, 106.72, 10.73)
arrow_table = overturemaps.record_batch_reader("building", bbox).read_all()
conn = duckdb.connect()
conn.execute("INSTALL spatial; LOAD spatial;")
res = conn.execute("SELECT id, ST_AsText(ST_GeomFromWKB(geometry)) AS geometry_wkt FROM arrow_table LIMIT 1").fetchall()
print("Success:", res)
