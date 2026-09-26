# Local monitoring

Start the existing stack plus FastAPI and Prometheus from the project root:

```bash
docker compose up -d --build
```

Open Prometheus at <http://localhost:9090>. The target page at
<http://localhost:9090/targets> should show `churn-api` as **UP**. FastAPI is
available at <http://localhost:8000>, and its raw Prometheus exposition is at
<http://localhost:8000/metrics>.

Useful PromQL:

```promql
# Request rate by endpoint
sum by (endpoint) (rate(http_requests_total[5m]))

# Error rate
sum(rate(http_errors_total[5m]))

# p50 request latency
histogram_quantile(0.50,
  sum by (le) (rate(http_request_duration_seconds_bucket[5m])))

# p95 request latency
histogram_quantile(0.95,
  sum by (le) (rate(http_request_duration_seconds_bucket[5m])))

# Kafka stream freshness; the local target is below 300 seconds
stream_freshness_seconds

# Analytics freshness and score update time
analytics_freshness_seconds
churn_scores_last_updated_timestamp_seconds

# Latest successful daily Airflow run
airflow_dag_last_success_timestamp_seconds{dag_id="daily_saas_pipeline"}
```

These are development-machine checks, not production SLAs. Stop everything
with `docker compose down`; add `-v` only when you intentionally want to erase
the local Prometheus and Airflow database volumes.
