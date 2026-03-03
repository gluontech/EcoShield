print("Step 1")
from src.data.ingestion.nex_gddp_ingest import CITY_BBOXES
print("Step 2", CITY_BBOXES)
from src.data.ingestion.dem_ingest import ingest
print("Step 3")
ingest(['hcmc'], dry_run=True)
print("Step 4")
