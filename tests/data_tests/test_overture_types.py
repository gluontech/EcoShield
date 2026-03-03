import overturemaps
bbox = (106.71, 10.72, 106.72, 10.73)
for t in ["building_part", "place"]:
    try:
        table = overturemaps.record_batch_reader(t, bbox).read_all()
        print(t, table.num_rows)
    except Exception as e:
        print(t, "Error:", e)
