import overturemaps
import time
import os

os.environ["AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"] = ""
os.environ["AWS_EC2_METADATA_DISABLED"] = "true" 
os.environ["AWS_REGION"] = "us-west-2"

lat = 10.72855516845333
lon = 106.718741744509
radius_m = 500
delta_deg = radius_m / 111320.0
bbox = (lon - delta_deg, lat - delta_deg, lon + delta_deg, lat + delta_deg)

print("Starting Overture Maps read with pyarrow S3 configured for IPv4...")
t0 = time.time()
try:
    arrow_table = overturemaps.record_batch_reader("building", bbox).read_all()
    print(f"Success! Num rows: {arrow_table.num_rows}")
except Exception as e:
    print(f"Failed with exception: {e}")
print(f"Time taken: {time.time() - t0:.2f}s")
