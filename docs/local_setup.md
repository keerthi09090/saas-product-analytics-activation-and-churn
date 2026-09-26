# Local Setup

This guide builds the reproducible batch analytics first, then adds optional
local services. Run commands from the repository root unless noted.

## Prerequisites

- Python 3.9 or newer
- Docker Desktop for Kafka, Airflow, the containerized API, and Prometheus
- Git

## 1. Clone and install

```bash
git clone https://github.com/keerthi09090/saas-product-analytics-activation-and-churn.git
cd saas-product-analytics-activation-and-churn
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

## 2. Generate data and build analytics

```bash
python -m simulator.generate

cd analytics_dbt
dbt debug --profiles-dir .
dbt run --profiles-dir .
dbt test --profiles-dir .
cd ..
```

This creates five raw Parquet datasets and
`analytics_dbt/analytics.duckdb`. Generated data and the local database are
ignored by Git.

## 3. Build the churn artifacts

```bash
python ml/build_dataset.py
python ml/train.py
python ml/evaluate.py
python ml/explain.py
python ml/score_accounts.py
```

To inspect experiment runs:

```bash
mlflow ui --backend-store-uri ./mlruns --port 5000
```

## 4. Run the API and dashboard directly

Use two terminals with the virtual environment active.

```bash
# Terminal 1
uvicorn api.main:app --reload
```

```bash
# Terminal 2
streamlit run dashboard/app.py
```

Open:

- Streamlit: <http://localhost:8501>
- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>

The Product Analytics and Retention & Churn pages read DuckDB. The Churn Risk
page calls FastAPI and degrades gracefully when the API is unavailable.

## 5. Start the local service stack

Docker Desktop must be running. `.env` is ignored; `.env.example` contains
placeholders only.

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

Open:

- Airflow: <http://localhost:8080>
- Prometheus: <http://localhost:9090>
- Prometheus targets: <http://localhost:9090/targets>
- Containerized FastAPI: <http://localhost:8000/health>

Use the local Airflow values you place in the ignored `.env` file. Do not
commit that file.

## 6. Demonstrate Kafka streaming

With the Docker stack running, use two more terminals:

```bash
# Consumer
source .venv/bin/activate
python -m streaming.consumer
```

```bash
# Producer
source .venv/bin/activate
python -m streaming.producer --events 100 --interval 1
```

For duplicate and invalid-event behavior:

```bash
python -m streaming.producer --events 10 --interval 0.1 \
  --duplicate-every 5 --send-invalid
```

Then rebuild dbt so materialized models include streamed events:

```bash
cd analytics_dbt
dbt run --profiles-dir .
dbt test --profiles-dir .
```

## 7. Run all quality checks

```bash
ruff check .
python -m pytest
cd analytics_dbt
dbt run --profiles-dir .
dbt test --profiles-dir .
```

## Shutdown

Stop direct Python processes with `Ctrl+C`. Stop containers while retaining
Airflow metadata:

```bash
docker compose down
```

Use `docker compose down -v` only when you intentionally want to remove the
local Airflow metadata volume.

## Common issues

- **dbt cannot find streaming Parquet:** run
  `python scripts/create_ci_stream_fixture.py` from the repository root.
- **Churn Risk says API unavailable:** build scores, then start Uvicorn.
- **`docker compose` is unavailable:** start/update Docker Desktop and verify
  with `docker info` and `docker compose version`.
- **Ports are already in use:** stop the older local process before starting
  another service on ports 8000, 8080, 8501, 9090, or 9092.
