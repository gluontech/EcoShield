import overturemaps
import time

bbox = (106.71, 10.72, 106.72, 10.73)
start = time.time()
try:
    table = overturemaps.record_batch_reader("building", bbox).read_all()
    print("Found rows:", table.num_rows)
except Exception as e:
    print("Error:", e)
print(f"Time: {time.time() - start:.2f}s")
