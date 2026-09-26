"""Durable local counters written by the Kafka consumer."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from streaming.config import STREAMING_DATA_DIR


STREAM_METRICS_PATH = STREAMING_DATA_DIR / "metrics.json"
DEFAULT_STATE: dict[str, Any] = {
    "received": 0,
    "persisted": 0,
    "rejected": 0,
    "duplicates": 0,
    "latest_event_timestamp": None,
}


def load_stream_metrics(path: Path = STREAM_METRICS_PATH) -> dict[str, Any]:
    if not path.exists():
        return DEFAULT_STATE.copy()
    try:
        return {**DEFAULT_STATE, **json.loads(path.read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError, TypeError):
        return DEFAULT_STATE.copy()


def update_stream_metrics(
    *,
    received: int = 0,
    persisted: int = 0,
    rejected: int = 0,
    duplicates: int = 0,
    latest_event_timestamp: datetime | None = None,
    path: Path = STREAM_METRICS_PATH,
) -> dict[str, Any]:
    state = load_stream_metrics(path)
    state["received"] = int(state["received"]) + received
    state["persisted"] = int(state["persisted"]) + persisted
    state["rejected"] = int(state["rejected"]) + rejected
    state["duplicates"] = int(state["duplicates"]) + duplicates
    if latest_event_timestamp is not None:
        current = state.get("latest_event_timestamp")
        candidate = latest_event_timestamp.isoformat()
        if current is None or candidate > current:
            state["latest_event_timestamp"] = candidate
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(state, indent=2, sort_keys=True), encoding="utf-8"
    )
    temporary.replace(path)
    return state
