"""Local Prometheus metrics and OpenTelemetry setup for the API service."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prometheus_client import Counter, Gauge, Histogram


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STREAM_METRICS_PATH = PROJECT_ROOT / "data" / "streaming" / "metrics.json"
STREAM_EVENTS_DIR = PROJECT_ROOT / "data" / "streaming" / "product_events"
DBT_RESULTS_PATH = PROJECT_ROOT / "analytics_dbt" / "target" / "run_results.json"
ANALYTICS_DB_PATH = PROJECT_ROOT / "analytics_dbt" / "analytics.duckdb"
CHURN_SCORES_PATH = PROJECT_ROOT / "artifacts" / "churn_risk_scores.parquet"

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests handled by FastAPI.",
    ["method", "endpoint", "status"],
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "FastAPI request duration in seconds.",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0, 2.5),
)
HTTP_ERRORS = Counter(
    "http_errors_total",
    "Total HTTP responses with a 4xx or 5xx status.",
    ["method", "endpoint", "status"],
)

STREAM_RECEIVED = Gauge(
    "stream_events_received_total", "Kafka messages received by the consumer."
)
STREAM_PERSISTED = Gauge(
    "stream_events_persisted_total", "Valid stream events written to Parquet."
)
STREAM_REJECTED = Gauge(
    "stream_events_rejected_total", "Invalid Kafka messages rejected."
)
STREAM_DUPLICATES = Gauge(
    "stream_duplicate_events_total", "Duplicate Kafka event IDs detected."
)
STREAM_LATEST = Gauge(
    "stream_latest_event_timestamp_seconds",
    "Unix timestamp of the latest valid streamed event.",
)
STREAM_FRESHNESS = Gauge(
    "stream_freshness_seconds",
    "Age in seconds of the latest valid streamed event.",
)

DBT_LAST_SUCCESS = Gauge(
    "dbt_last_success_timestamp_seconds",
    "Unix timestamp of the latest successful dbt invocation.",
)
ANALYTICS_FRESHNESS = Gauge(
    "analytics_freshness_seconds", "Age in seconds of the DuckDB analytics file."
)
CHURN_SCORES_UPDATED = Gauge(
    "churn_scores_last_updated_timestamp_seconds",
    "Unix timestamp when churn scores were last updated.",
)

AIRFLOW_LAST_SUCCESS = Gauge(
    "airflow_dag_last_success_timestamp_seconds",
    "Latest successful Airflow DAG completion.",
    ["dag_id"],
)
AIRFLOW_LAST_FAILURE = Gauge(
    "airflow_dag_last_failure_timestamp_seconds",
    "Latest failed Airflow DAG completion, or zero when none is recorded.",
    ["dag_id"],
)
AIRFLOW_LAST_COMPLETION = Gauge(
    "airflow_dag_last_completion_timestamp_seconds",
    "Latest Airflow DAG completion in any terminal state.",
    ["dag_id"],
)
SERVICE_HEALTH = Gauge(
    "service_health", "Local service health: 1 is healthy and 0 is unavailable.", ["service"]
)


def _timestamp(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _load_stream_state() -> dict[str, Any]:
    if not STREAM_METRICS_PATH.exists():
        return {}
    try:
        return json.loads(STREAM_METRICS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _fallback_latest_stream_event() -> float:
    """Use actual Parquet data when the state file predates Level 10."""

    files = [
        path
        for path in STREAM_EVENTS_DIR.glob("*.parquet")
        if path.name != "_empty.parquet"
    ]
    if not files:
        return 0.0
    try:
        import pandas as pd

        latest = max(
            pd.read_parquet(path, columns=["event_timestamp"])[
                "event_timestamp"
            ].max()
            for path in files
        )
        return float(pd.Timestamp(latest).timestamp())
    except (OSError, ValueError, KeyError):
        return 0.0


def refresh_stream_metrics(now: datetime | None = None) -> None:
    state = _load_stream_state()
    STREAM_RECEIVED.set(float(state.get("received", 0)))
    STREAM_PERSISTED.set(float(state.get("persisted", 0)))
    STREAM_REJECTED.set(float(state.get("rejected", 0)))
    STREAM_DUPLICATES.set(float(state.get("duplicates", 0)))
    latest = _timestamp(state.get("latest_event_timestamp")) or _fallback_latest_stream_event()
    STREAM_LATEST.set(latest)
    current = (now or datetime.now(timezone.utc)).timestamp()
    STREAM_FRESHNESS.set(max(0.0, current - latest) if latest else 0.0)


def refresh_data_metrics(now: datetime | None = None) -> None:
    current = (now or datetime.now(timezone.utc)).timestamp()
    dbt_success = 0.0
    if DBT_RESULTS_PATH.exists():
        try:
            results = json.loads(DBT_RESULTS_PATH.read_text(encoding="utf-8"))
            statuses = {
                str(item.get("status", "")).lower()
                for item in results.get("results", [])
            }
            if statuses and statuses <= {"success", "pass", "warn", "skipped"}:
                dbt_success = _timestamp(
                    results.get("metadata", {}).get("generated_at")
                )
        except (OSError, json.JSONDecodeError, ValueError):
            dbt_success = 0.0
    DBT_LAST_SUCCESS.set(dbt_success)

    if ANALYTICS_DB_PATH.exists():
        ANALYTICS_FRESHNESS.set(
            max(0.0, current - ANALYTICS_DB_PATH.stat().st_mtime)
        )
    else:
        ANALYTICS_FRESHNESS.set(0.0)
    CHURN_SCORES_UPDATED.set(
        CHURN_SCORES_PATH.stat().st_mtime if CHURN_SCORES_PATH.exists() else 0.0
    )


def refresh_airflow_metrics() -> None:
    dag_ids = ("daily_saas_pipeline", "backfill_saas_pipeline")
    for dag_id in dag_ids:
        AIRFLOW_LAST_SUCCESS.labels(dag_id).set(0)
        AIRFLOW_LAST_FAILURE.labels(dag_id).set(0)
        AIRFLOW_LAST_COMPLETION.labels(dag_id).set(0)
    dsn = os.getenv("AIRFLOW_METRICS_DATABASE_URL")
    if not dsn:
        SERVICE_HEALTH.labels("airflow_metadata").set(0)
        return
    try:
        import psycopg2

        with psycopg2.connect(dsn, connect_timeout=2) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select dag_id, state, max(end_date)
                    from dag_run
                    where dag_id in (%s, %s)
                      and state in ('success', 'failed')
                      and end_date is not null
                    group by dag_id, state
                    """,
                    dag_ids,
                )
                rows = cursor.fetchall()
        completions: dict[str, list[float]] = {dag_id: [] for dag_id in dag_ids}
        for dag_id, state, ended_at in rows:
            timestamp = _timestamp(ended_at)
            completions[dag_id].append(timestamp)
            if state == "success":
                AIRFLOW_LAST_SUCCESS.labels(dag_id).set(timestamp)
            elif state == "failed":
                AIRFLOW_LAST_FAILURE.labels(dag_id).set(timestamp)
        for dag_id, timestamps in completions.items():
            AIRFLOW_LAST_COMPLETION.labels(dag_id).set(
                max(timestamps, default=0.0)
            )
        SERVICE_HEALTH.labels("airflow_metadata").set(1)
    except Exception:
        # Monitoring must never take down the application it observes.
        SERVICE_HEALTH.labels("airflow_metadata").set(0)


def refresh_observability_metrics(api_ready: bool) -> None:
    refresh_stream_metrics()
    refresh_data_metrics()
    refresh_airflow_metrics()
    SERVICE_HEALTH.labels("churn_api").set(int(api_ready))


def configure_opentelemetry(application: Any) -> None:
    """Instrument FastAPI; optionally print spans with the console exporter."""

    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider

    provider = TracerProvider(
        resource=Resource.create({"service.name": "saas-churn-api"})
    )
    if os.getenv("OTEL_TRACES_EXPORTER", "none").lower() == "console":
        from opentelemetry.sdk.trace.export import (
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )

        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(application)
