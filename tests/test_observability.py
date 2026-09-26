"""Level 10 metrics, readiness, tracing, and safe-failure tests."""

import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

import api.observability as observability
from api.main import app, create_app
from streaming.metrics import load_stream_metrics, update_stream_metrics


def _sample(name, labels=None):
    return REGISTRY.get_sample_value(name, labels or {}) or 0.0


def test_health_ready_and_metrics_endpoints():
    with TestClient(app) as client:
        health = client.get("/health")
        ready = client.get("/ready")
        metrics = client.get("/metrics")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"ready": True}
    assert metrics.status_code == 200
    assert "http_requests_total" in metrics.text
    assert "http_request_duration_seconds_bucket" in metrics.text
    assert "http_errors_total" in metrics.text
    assert "stream_freshness_seconds" in metrics.text


def test_request_and_error_counters_increase():
    request_labels = {
        "method": "GET",
        "endpoint": "/v1/churn/{account_id}",
        "status": "200",
    }
    error_labels = {
        "method": "GET",
        "endpoint": "/v1/churn/{account_id}",
        "status": "404",
    }
    requests_before = _sample("http_requests_total", request_labels)
    errors_before = _sample("http_errors_total", error_labels)

    with TestClient(app) as client:
        valid = client.get("/v1/churn/A040")
        missing = client.get("/v1/churn/DOES_NOT_EXIST")

    assert valid.status_code == 200
    assert missing.status_code == 404
    assert _sample("http_requests_total", request_labels) == requests_before + 1
    assert _sample("http_errors_total", error_labels) == errors_before + 1


def test_invalid_request_is_counted_as_an_error():
    labels = {"method": "GET", "endpoint": "/v1/churn", "status": "422"}
    before = _sample("http_errors_total", labels)
    with TestClient(app) as client:
        response = client.get("/v1/churn", params={"limit": 0})
    assert response.status_code == 422
    assert _sample("http_errors_total", labels) == before + 1


def test_missing_score_artifact_is_safe_and_observable(tmp_path):
    unavailable_app = create_app(tmp_path / "missing.parquet")
    with TestClient(unavailable_app) as client:
        assert client.get("/health").status_code == 503
        assert client.get("/ready").status_code == 503
        assert client.get("/v1/churn").status_code == 503
        assert client.get("/metrics").status_code == 200


def test_stream_metrics_are_durable_and_freshness_is_non_negative(
    tmp_path, monkeypatch
):
    state_path = tmp_path / "metrics.json"
    event_time = datetime.now(timezone.utc) - timedelta(seconds=10)
    update_stream_metrics(
        received=3,
        persisted=1,
        rejected=1,
        duplicates=1,
        latest_event_timestamp=event_time,
        path=state_path,
    )
    state = load_stream_metrics(state_path)
    assert state["received"] == 3
    assert state["persisted"] == 1
    assert state["rejected"] == 1
    assert state["duplicates"] == 1

    monkeypatch.setattr(observability, "STREAM_METRICS_PATH", state_path)
    observability.refresh_stream_metrics(now=datetime.now(timezone.utc))
    assert _sample("stream_freshness_seconds") >= 0
    assert _sample("stream_events_rejected_total") == 1
    assert _sample("stream_duplicate_events_total") == 1


def test_stale_stream_data_is_reported_without_failure(tmp_path, monkeypatch):
    state_path = tmp_path / "metrics.json"
    old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    state_path.write_text(
        json.dumps({"latest_event_timestamp": old_time.isoformat()}),
        encoding="utf-8",
    )
    monkeypatch.setattr(observability, "STREAM_METRICS_PATH", state_path)
    observability.refresh_stream_metrics(now=datetime.now(timezone.utc))
    assert _sample("stream_freshness_seconds") >= 600


def test_metrics_do_not_expose_credentials_or_secrets():
    with TestClient(app) as client:
        body = client.get("/metrics").text.lower()
    assert "postgresql://" not in body
    assert "password=" not in body
    assert "local-level-9-demo-key" not in body


def test_trace_id_is_returned_for_api_requests():
    with TestClient(app) as client:
        response = client.get("/health")
    trace_id = response.headers.get("x-trace-id")
    assert trace_id is not None
    assert len(trace_id) == 32
    int(trace_id, 16)
