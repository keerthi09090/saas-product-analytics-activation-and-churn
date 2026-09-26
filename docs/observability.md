# Level 10 observability

Level 10 adds local, portfolio-friendly health signals without changing the
analytics, machine-learning, streaming, or orchestration definitions.

## What is monitored

### FastAPI

- `http_requests_total` counts requests by method, normalized endpoint, and
  response status.
- `http_request_duration_seconds` is a histogram used for p50 and p95 latency.
- `http_errors_total` counts 4xx and 5xx responses.
- `/health` confirms the risk artifact loaded; `/ready` is suitable for a
  readiness check; `/metrics` is scraped by Prometheus.
- OpenTelemetry creates one request trace with endpoint, method, status, and
  duration. The local Docker service uses the console span exporter. Successful
  responses also carry `X-Trace-ID` for correlation.

Account IDs are represented by the route template `/v1/churn/{account_id}` in
metric labels. This avoids an unbounded label for every customer.

### Kafka streaming

The consumer updates `data/streaming/metrics.json` atomically. Prometheus
surfaces:

- `stream_events_received_total`
- `stream_events_persisted_total`
- `stream_events_rejected_total`
- `stream_duplicate_events_total`
- `stream_latest_event_timestamp_seconds`
- `stream_freshness_seconds`

The freshness value is calculated from the actual latest valid event, never a
hard-coded timestamp. The local demonstration target is under five minutes.

### Data and model artifacts

- `dbt_last_success_timestamp_seconds` reads dbt's real `run_results.json` and
  is set only when the invocation has no failing result.
- `analytics_freshness_seconds` uses the DuckDB file modification time.
- `churn_scores_last_updated_timestamp_seconds` uses the risk-score Parquet
  modification time.

### Airflow

The metrics endpoint reads the existing Airflow metadata database with a
read-only query and exposes the latest success, failure, and completion time
for `daily_saas_pipeline` and `backfill_saas_pipeline`. It does not rebuild or
replace Airflow monitoring.

## Tool responsibilities

- **Prometheus** stores and queries numeric time-series metrics.
- **OpenTelemetry** instruments requests and creates traces.
- **Airflow** schedules and records batch workflow execution.
- **Kafka** transports continuously produced product events.

They are complementary: Kafka and Airflow run work, while OpenTelemetry and
Prometheus explain whether that work and the API are healthy.

## Local verification

```bash
docker compose up -d --build
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
python tests/load_test.py --requests 200
```

Then open <http://localhost:9090/targets> and confirm `churn-api` is **UP**.
PromQL examples, including p50 and p95 latency, are in
`monitoring/README.md`. The latency target is a documented local target of p95
below 200 ms, not a production SLA.

The API handles a missing risk-score artifact safely: startup remains alive,
`/health` and `/ready` return 503, and churn routes return a clear 503. Unknown
accounts return 404 and increase the HTTP error metric.

## Documented local load-test run

On September 25, 2026, the existing sequential development load test sent 200
measured requests after 10 warm-up requests to `/v1/churn/A040`:

| Result | Value |
|---|---:|
| Measured requests | 200 |
| Errors for valid requests | 0 (0%) |
| p50 latency | 1.89 ms |
| p95 latency | 2.64 ms |

Prometheus observed all 210 measured-plus-warm-up requests. Its five-minute
histogram query returned a p95 of about 75 ms across all API endpoints during
the same local session. Both measurements are below the portfolio target, but
they describe one local machine and are not a production performance claim.
