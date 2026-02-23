# EcoShield — Climate Risk Intelligence Platform

**EcoShield** is a structure-level climate risk intelligence platform for Southeast Asia. It delivers engineering-based climate risk analysis at the individual building level, modelling **8 hazards** — coastal, riverine, and pluvial flooding, subsidence, landslides, tropical cyclones, storm surge, and urban heat — using an async pipeline for deterministic orchestration.

**MVP target cities:** Ho Chi Minh City, Hanoi, Da Nang (Vietnam).

> **Resolution Transparency (v3.2):** Climate forcing comes from NEX-GDDP-CMIP6 at **0.25° (~25 km)**. Building-level differentiation is achieved by overlaying terrain data (GLO-30 DEM at 30 m, HAND at 30 m) onto sub-meter building footprints from Google Open Buildings and Overture Maps.

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│                 FastAPI  (port 8000)              │
│  /v1/assess  /v1/portfolio  /v1/buildings         │
└───────┬──────────────────────────────┬────────────┘
        │                              │
   ┌────▼────┐                    ┌────▼────┐
   │ Pipeline │                    │ Worker  │
   │ 6 Steps  │                    │ (async) │
   └────┬────┘                    └─────────┘
        │
  ┌─────┼─────────────────────────────────┐
  │     │  Hazard Assessment Pipeline     │
  │  Step 0  Asset Fetch (Buildings)      │
  │  Step 1  Chronic Hazards (‖)          │
  │  Step 2  Cyclone (Holland 2008)       │
  │  Step 3  Acute Hazards (‖ × Multi-RP) │
  │  Step 4  Structure Risk (EAL)         │
  │  Step 5  Composite Aggregation        │
  └───────────────────────────────────────┘
        │
  ┌─────▼─────────────────────────────────┐
  │           Data Sources                │
  │  PostGIS │ Redis │ MinIO │ S3/GEE    │
  └───────────────────────────────────────┘
```

### Source Modules

| Module | Purpose |
|--------|---------|
| `src/api/` | FastAPI routes, schemas, middleware, error handling |
| `src/workflows/` | 6-step async pipeline and step executors |
| `src/tools/` | Individual hazard assessment tools (8 hazards) |
| `src/data/` | Data access — DEM, InSAR, IBTrACS, NEX-GDDP, Google Open Buildings, Overture Maps |
| `src/core/` | Pydantic models — geometry, hazard, exposure, asset, results |
| `src/config/` | Settings, city hazard profiles, hazard weights |
| `src/agents/` | Agent/worker logic |

---

## Prerequisites

- **Docker** and **Docker Compose** v2+
- **Git LFS** (for large data files in `data/`)
- **(Optional)** Google Earth Engine service account key for building footprint data

---

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/gluontech/EcoShield.git
cd EcoShield
git lfs pull   # download large data files
```

### 2. Configure Environment

Copy the example environment file and edit as needed:

```bash
cp .env.example .env   # or edit .env directly
```

Key variables in `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_USER` | PostgreSQL username | `ecoshield` |
| `POSTGRES_PASSWORD` | PostgreSQL password | *(set your own)* |
| `POSTGRES_DB` | Database name | `ecoshield` |
| `REDIS_PORT` | Redis port | `6379` |
| `GEE_SERVICE_ACCOUNT` | Google Earth Engine service account | *(optional)* |
| `GEE_KEY_FILE` | Path to GEE JSON key inside container | `/app/secrets/earth-engine-key.json` |

> ⚠️ **Security:** Never commit real API keys or credentials. Use environment variables or Docker secrets.

### 3. Build and Run

```bash
docker compose up --build
```

This starts 5 services:

| Service | Port | Description |
|---------|------|-------------|
| **api** | `8000` | FastAPI application |
| **db** | `5432` | PostGIS 15 database |
| **redis** | `6379` | Redis 7 cache |
| **minio** | `9000` / `9001` | S3-compatible object store |
| **worker** | — | Background task worker |

### 4. Verify

```bash
# Health check
curl http://localhost:8000/health

# Swagger docs
open http://localhost:8000/docs
```

---

## API Usage

### `POST /v1/assess` — Single-Site Risk Assessment

Assess climate risk for a single location across multiple hazards.

**Request:**

```json
{
  "location": {
    "lat": 10.7962818,
    "lon": 106.67308139341037,
    "name": "Eastin Grand Hotel Saigon"
  },
  "hazards": ["flood", "heat", "cyclone", "surge", "subsidence", "pluvial"],
  "city": "hcmc",
  "scenario": "ssp245",
  "time_horizon": "2030-2040",
  "return_period": 10,
  "include_details": true
}
```

**Example:**

```bash
curl -X POST http://localhost:8000/v1/assess \
  -H "Content-Type: application/json" \
  -d @assess-request.json
```

**Response** includes per-hazard risk scores, building exposure data, and a composite risk profile. See `response.json` for a full example.

### Other Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/portfolio` | POST | Portfolio-level risk assessment |
| `/v1/buildings` | GET | Query building footprints by bounding box |
| `/v1/hazards` | GET | List available hazard types |
| `/health` | GET | Health check |
| `/docs` | GET | Swagger UI |
| `/redoc` | GET | ReDoc documentation |

---

## Running Without Docker

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (requires uv)
uv sync

# Start API
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

> **Note:** You still need PostgreSQL, Redis, and MinIO running locally or via their respective connection strings in `.env`.

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test module
pytest tests/models_tests/ -v
```

---

## Project Structure

```
EcoShield/
├── src/
│   ├── api/           # FastAPI routes & schemas
│   ├── workflows/     # 6-step async pipeline
│   ├── tools/         # 8 hazard assessment tools
│   ├── data/          # Data access layer
│   ├── core/          # Pydantic models
│   ├── config/        # Settings & city profiles
│   └── agents/        # Worker agents
├── tests/             # pytest test suite
├── data/              # Climate & geospatial datasets (Git LFS)
├── docker/            # Dockerfiles
├── docs/              # Architecture documentation
├── scripts/           # Data ingestion & utility scripts
├── docker-compose.yml
├── pyproject.toml
└── .env
```

---

## License

See [LICENSE](LICENSE) for details.
