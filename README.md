# SaaS Product Analytics, Activation, and Churn — Levels 1–11

[![CI](https://github.com/keerthi09090/saas-product-analytics-activation-and-churn/actions/workflows/ci.yml/badge.svg)](https://github.com/keerthi09090/saas-product-analytics-activation-and-churn/actions/workflows/ci.yml)

This project creates realistic fake SaaS data, analyzes it with DuckDB and SQL,
organizes the analytics layer with dbt-duckdb, presents activation, retention,
churn, and revenue results in Streamlit, and demonstrates leakage-safe churn
risk modeling. It also includes a FastAPI serving layer, Kafka streaming,
Airflow orchestration, Prometheus/OpenTelemetry observability, and GitHub
Actions quality gates for a complete local portfolio system.

The generator creates approximately 100 fictional customer accounts and five related Parquet tables. A fixed random seed makes every run reproducible.

## Project structure

```text
saas-product-analytics/
├── README.md
├── requirements.txt
├── data/
│   ├── accounts.parquet
│   ├── users.parquet
│   ├── subscriptions.parquet
│   ├── invoices.parquet
│   └── events.parquet
├── simulator/
│   ├── __init__.py
│   └── generate.py
├── tests/
│   └── test_generator.py
├── analytics/
│   ├── setup.sql
│   ├── activation.sql
│   ├── usage_metrics.sql
│   └── run_metrics.py
├── analytics_dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── models/
│   │   ├── staging/
│   │   ├── intermediate/
│   │   └── marts/
│   └── tests/
├── dashboard/
│   ├── app.py
│   ├── data_loader.py
│   └── metrics.py
├── ml/
│   ├── build_dataset.py
│   ├── train.py
│   ├── evaluate.py
│   ├── explain.py
│   ├── score_accounts.py
│   └── utils.py
├── artifacts/
│   ├── churn_training_data.parquet
│   ├── churn_model.pkl
│   ├── logistic_model.pkl
│   ├── model_metrics.json
│   ├── feature_importance.csv
│   └── churn_risk_scores.parquet
└── docs/
    ├── retention_analysis.md
    └── churn_model_card.md
```

## Install and run

Create a virtual environment and install the small dependency set:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Generate the data:

```bash
python -m simulator.generate
```

The default run uses 100 accounts and seed `42`. Optional arguments are available:

```bash
python -m simulator.generate --accounts 100 --seed 42 --output data
```

Run the tests:

```bash
pytest
```

## Level 2: analyze the Parquet files with DuckDB

After generating the Level 1 data, run:

```bash
python analytics/run_metrics.py
```

DuckDB reads the five Parquet files directly and prints activation rate, median time to activation, trial conversion, weekly active accounts, monthly active accounts, and feature adoption.

Activation requires `workspace_created`, `invite_sent`, and `integration_connected` during the half-open 14-day window beginning on `trial_start_date`. The activation date is when the last of those three requirements occurs.

The Level 2 files have separate responsibilities:

- `analytics/setup.sql` creates five DuckDB views over the Parquet files.
- `analytics/activation.sql` produces one activation row per account and the activation summary.
- `analytics/usage_metrics.sql` calculates conversion, weekly/monthly activity, and adoption.
- `analytics/run_metrics.py` executes the SQL, validates the results, and prints the report.

## Level 3: organize analytics with dbt and DuckDB

The dbt project reads the same Level 1 Parquet files and builds typed staging
views, reusable intermediate views, dimensions, fact tables, and analytics
marts. It preserves the Level 2 activation definition exactly.

Run it from the dbt project directory:

```bash
cd analytics_dbt
source ../.venv/bin/activate
dbt debug
dbt run
dbt test
```

The resulting local database is `analytics_dbt/analytics.duckdb`. Example
queries are documented in `analytics_dbt/README.md`.

## Level 4: Streamlit product analytics dashboard

Run the dashboard from the project root after `dbt run`:

```bash
source .venv/bin/activate
streamlit run dashboard/app.py
```

The dashboard reads only materialized dbt models from
`analytics_dbt/analytics.duckdb`; it does not copy the Parquet data. It includes
executive KPIs, an activation funnel, feature adoption, weekly and monthly
active-account trends, a sortable account-activity table, account filters, and
calculated descriptive insights.

Model ownership is intentionally simple:

- `dim_account` supplies account totals, filter attributes, and cohort context.
- `fact_subscriptions` supplies trial-conversion status.
- `mart_activation` supplies activation results.
- `mart_feature_adoption` supplies unfiltered feature adoption.
- `fact_product_events` supplies funnel milestones, filtered adoption, and activity trends.
- `mart_account_activity` supplies the account-level activity table.

## Level 5: retention, churn, and revenue

Level 5 adds weekly retention cohorts, monthly logo churn, account-month MRR,
revenue churn, expansion, contraction, NRR, segment comparisons, seat
utilization, and recency metrics. The Streamlit sidebar now includes a
**Retention & Churn** page with a cohort heatmap and the Level 5 trends.

Rebuild and validate the complete project from the repository root:

```bash
python -m simulator.generate
cd analytics_dbt
dbt run --profiles-dir .
dbt test --profiles-dir .
cd ..
streamlit run dashboard/app.py
```

The concise findings for the reproducible seed-42 dataset are in
`docs/retention_analysis.md`.

## Level 6: time-based churn prediction

Level 6 predicts whether an active paid account will cancel in the next 30
days. Monthly snapshots use only events and invoices known on their prediction
date. Training, validation, and testing are separated chronologically.

Build and validate the dbt feature mart first, then run the ML workflow from
the project root:

```bash
cd analytics_dbt
dbt run --profiles-dir .
dbt test --profiles-dir .
cd ..

python ml/build_dataset.py
python ml/train.py
python ml/evaluate.py
python ml/explain.py
python ml/score_accounts.py
python -m pytest
```

The workflow compares a logistic-regression baseline with histogram gradient
boosting, tracks both experiments in local MLflow, writes reproducible files to
`artifacts/`, and produces a retention-team ranking with descriptive account
reasons. Open MLflow locally with:

```bash
mlflow ui --backend-store-uri ./mlruns --port 5000
```

See `docs/churn_model_card.md` for the label definition, split dates, held-out
metrics, interpretation, limitations, and responsible-use guidance.

## Level 7: churn-risk API

Level 7 serves the latest Level 6 risk-score artifact through a separate,
read-only FastAPI application. It loads the Parquet file once at startup; it
does not retrain the model or trigger customer actions.

Start it from the project root:

```bash
source .venv/bin/activate
uvicorn api.main:app --reload
```

Interactive documentation is available at `http://127.0.0.1:8000/docs` and
ReDoc at `http://127.0.0.1:8000/redoc`. See `docs/api.md` for endpoints, sample
responses, interpretation, and the local load-test command.

## Level 8: continuous product events with Kafka

Level 8 adds a parallel streaming path without replacing the reproducible
batch generator:

```text
                           ┌─> Batch Parquet ───────────┐
Synthetic SaaS activity ───┤                            ├─> DuckDB/dbt ─> Dashboard
                           └─> Kafka ─> Consumer ─> Streaming Parquet ─┘
```

Kafka is used only for continuously arriving product events. Account, billing,
and subscription snapshots remain batch inputs and can be orchestrated in a
later level.

The producer is finite by default, emits valid account/user relationships,
supports event contract versions 1 and 2, favors high-engagement accounts, and
slows its emission rate on weekends. The consumer validates messages, rejects
bad records without stopping, deduplicates `event_id`, and writes buffered,
append-friendly Parquet files. See `docs/event_contract.md` for the contract.

### Level 8 demo

Docker Desktop must be installed and running. From the project root, use three
terminals. The consumer prints every valid v1/v2 message, duplicate, rejection,
and Parquet flush so the complete path is visible during the demo.

Terminal 1 — start the single KRaft Kafka broker and create `product-events`:

```bash
docker compose up -d
docker compose ps
```

Terminal 2 — start the buffered raw-event writer:

```bash
source .venv/bin/activate
python -m streaming.consumer
```

Terminal 3 — send 100 events, including deliberate duplicate deliveries:

```bash
source .venv/bin/activate
python -m streaming.producer --events 100 --interval 1
```

For a short duplicate and invalid-message demonstration, run this after the
consumer is connected:

```bash
python -m streaming.producer --events 10 --interval 0.1 \
  --duplicate-every 5 --send-invalid
```

The duplicate deliveries are printed by the consumer but are not persisted a
second time. The invalid message is logged under `data/streaming/rejected/`,
and the consumer continues running. Batches flush every 25 valid events or 10
seconds, whichever happens first. Inspect the persisted files and summary with:

```bash
ls -lh data/streaming/product_events/
python -m streaming.status
```

Stop the consumer with Ctrl+C, then make the events available to materialized
dbt models:

```bash
cd analytics_dbt
dbt run --profiles-dir .
dbt test --profiles-dir .
cd ..
```

Start or refresh Streamlit and inspect the compact **Streaming Status** block
on Product Analytics:

```bash
streamlit run dashboard/app.py
```

The local target is raw dashboard freshness under five minutes. It is a
development target, not a production SLA. Stop Kafka with:

```bash
docker compose down
```

## Level 9: scheduled batch orchestration with Airflow

Level 9 keeps the real-time and scheduled paths deliberately separate:

```text
Kafka   -> continuous product events -> streaming Parquet
Airflow -> dated account/subscription/invoice snapshots -> dbt -> tests -> scoring
```

Airflow never starts or schedules the Kafka producer or consumer. It handles
daily snapshots, transformations, data-quality gates, safe historical
backfills, and an optional refresh using the already-trained churn model.

### Start Airflow locally

Docker Desktop must be running. Copy the local Airflow UID setting once, then
build and start the simple Postgres + scheduler + webserver stack:

```bash
cp .env.example .env
docker compose up -d
docker compose ps
```

The first build downloads Airflow and installs the project data dependencies,
so it takes longer than later starts. Open `http://localhost:8080` and sign in
with the local values from `AIRFLOW_ADMIN_USER` and `AIRFLOW_ADMIN_PASSWORD` in
your ignored `.env` file. `.env.example` contains placeholders only.

The `daily_saas_pipeline` DAG is intentionally paused when first created. In
the UI, unpause it and press **Trigger DAG**, or use:

```bash
docker compose exec airflow-webserver airflow dags unpause daily_saas_pipeline
docker compose exec airflow-webserver airflow dags trigger \
  --exec-date 2026-09-25 daily_saas_pipeline
```

Its intended schedule is once per day. Tasks run in this strict order:

```text
snapshot_accounts
  -> snapshot_subscriptions
  -> snapshot_invoices
  -> dbt_run
  -> dbt_test
  -> refresh_churn_scores
```

Because normal Airflow dependencies require success, a failed `dbt_test`
prevents churn scoring. Scoring uses the existing model and does not retrain it.
Disable scoring when desired with:

```bash
docker compose exec airflow-webserver airflow variables set \
  enable_churn_scoring false
```

Each task has two retries with a two-minute delay and a 15-minute execution
timeout. Task logs show the logical date, input, output, row count, and result;
inspect them by selecting a DAG run and task in the Airflow Grid view.

### Snapshot idempotency

The three snapshot scripts use Airflow's `{{ ds }}` logical date, never the
container clock. They atomically overwrite one deterministic partition:

```text
data/snapshots/accounts/date=2026-09-25/accounts.parquet
data/snapshots/subscriptions/date=2026-09-25/subscriptions.parquet
data/snapshots/invoices/date=2026-09-25/invoices.parquet
```

Primary keys are checked before writing. Repeating the same date replaces the
same file, so row counts do not double. You can demonstrate this without the UI:

```bash
python -m pipelines.snapshot_accounts --snapshot-date 2026-09-25
python -m pipelines.snapshot_accounts --snapshot-date 2026-09-25
```

### Historical backfill

The separate `backfill_saas_pipeline` uses the same idempotent scripts. Run a
date range with Airflow logical dates:

```bash
docker compose exec airflow-webserver airflow dags backfill \
  backfill_saas_pipeline \
  --start-date 2026-09-21 \
  --end-date 2026-09-23
```

To deliberately rebuild an already-run range, add `--reset-dagruns`. Each day
creates or replaces its own `date=...` partition. Inspect outputs with:

```bash
find data/snapshots -name '*.parquet' -print | sort
```

Stop Airflow and Kafka while retaining the Airflow metadata volume with:

```bash
docker compose down
```

Use `docker compose down -v` only when you intentionally want to delete local
Airflow metadata and run history.

## Level 10: local observability

Level 10 adds Prometheus metrics and OpenTelemetry request traces without
changing the existing Kafka or Airflow responsibilities. Start the complete
local stack with:

```bash
docker compose up -d --build
```

FastAPI runs at `http://localhost:8000`, Prometheus at
`http://localhost:9090`, and the Prometheus targets page is
`http://localhost:9090/targets`. See `docs/observability.md` and
`monitoring/README.md` for monitored signals, PromQL examples, and local
verification commands.

## Level 11: GitHub Actions quality gates

Level 11 adds two GitHub Actions workflows for pushes and pull requests to
`main`. `CI` runs Ruff, deterministic data/model preparation, and all Python
tests. `Data Quality` runs `dbt debug`, `dbt run`, `dbt test`, and focused data
contract and pipeline checks. See `docs/ci_cd.md` for workflow behavior, failure
interpretation, and a safe red-to-green demonstration.

## What each table represents

### `accounts.parquet`

One row per fictional customer company. It contains company size, plan, purchased seats, acquisition channel, signup timing, and a hidden synthetic engagement level used to drive behavior.

### `users.parquet`

Provisioned product users belonging to the accounts. Larger companies and higher plans generally have more users, but user counts never exceed purchased seats. Invited users are created after their invitation.

### `subscriptions.parquet`

One subscription per account, including trial dates, paid start date when applicable, cancellation date, current status, current plan, and monthly price. Most accounts are active or still in trial; only a small fraction are cancelled.

### `invoices.parquet`

Calendar-aligned billing periods for active or cancelled paid subscriptions. Each invoice preserves the historical plan and price, making upgrades and downgrades auditable. Trial-only accounts do not receive invoices.

### `events.parquet`

Chronological product behavior. Workspaces are created first, invitations and integrations follow, and reports must be created before exports. High-engagement accounts create more events, and weekday activity is much higher than weekend activity.

## Inspect the first five rows

Run this from the project root:

```python
from pathlib import Path
import pandas as pd

for path in sorted(Path("data").glob("*.parquet")):
    print(f"\n{path.name}")
    print(pd.read_parquet(path).head())
```

Or inspect one table:

```python
import pandas as pd

accounts = pd.read_parquet("data/accounts.parquet")
print(accounts.head())
```

## Assumptions

- The simulated observation date is fixed at December 31, 2025 so results do not change with the real calendar.
- Trials last 14 days.
- Monthly prices are `$49` for Starter, `$249` for Growth, and `$999` for Enterprise.
- Company size and seat ranges grow by plan.
- User utilization and event volume depend on the account's synthetic engagement level.
- Only Admin users connect integrations or send the initial invitations in this Level 1 model.
- Managers and Analysts can create and export reports; Members mainly log in and view dashboards.
- Weekend activity is intentionally much lower than weekday activity.
- Cancelled accounts stop generating activity and invoices at their simulated cancellation date.
- Invoice periods follow calendar-month renewals from each paid start date.
- Plan changes move one adjacent tier at a renewal; engagement influences the probability of expansion or contraction.

## Validation performed

The generator checks IDs, foreign keys, event actors, nonnegative values, user creation times, workspace chronology, report creation/export order, seat limits, and invoice eligibility before writing any files. The test suite also checks weekday seasonality, plan/seat relationships, engagement-driven activity, and same-seed reproducibility.
