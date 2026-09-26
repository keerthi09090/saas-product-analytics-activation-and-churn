"""Load dashboard data from the materialized dbt models in DuckDB.

The dashboard deliberately reads only dbt tables. It does not read the raw
Parquet files or copy them into a second dashboard-specific data store.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Tuple

import duckdb
import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_DATABASE_PATH = PROJECT_ROOT / "analytics_dbt" / "analytics.duckdb"
DEMO_DATABASE_PATH = PROJECT_ROOT / "data" / "demo" / "analytics_demo.duckdb"
_configured_database = os.getenv("DASHBOARD_DATABASE_PATH")
DEFAULT_DATABASE_PATH = (
    Path(_configured_database).expanduser()
    if _configured_database
    else LOCAL_DATABASE_PATH if LOCAL_DATABASE_PATH.exists() else DEMO_DATABASE_PATH
)
USING_DEMO_DATABASE = DEFAULT_DATABASE_PATH.resolve() == DEMO_DATABASE_PATH.resolve()
DEFAULT_STREAMING_EVENTS_PATH = (
    PROJECT_ROOT / "data" / "streaming" / "product_events"
)

MODEL_QUERIES = {
    "accounts": """
        select *
        from dim_account
        order by account_id
    """,
    "subscriptions": """
        select *
        from fact_subscriptions
        order by subscription_id
    """,
    "activation": """
        select *
        from mart_activation
        order by account_id
    """,
    "feature_adoption": """
        select *
        from mart_feature_adoption
        order by case feature_name
            when 'invite_sent' then 1
            when 'integration_connected' then 2
            when 'report_created' then 3
            when 'report_exported' then 4
            when 'dashboard_viewed' then 5
        end
    """,
    "account_activity": """
        select *
        from mart_account_activity
        order by account_id
    """,
    "events": """
        select
            event_id,
            account_id,
            user_id,
            event_name,
            event_timestamp,
            event_version
        from fact_product_events
        order by event_timestamp, event_id
    """,
    "retention_cohorts": """
        select *
        from mart_retention_cohorts
        order by cohort_week, weeks_since_start
    """,
    "logo_churn": """
        select *
        from mart_logo_churn
        order by month
    """,
    "revenue_churn": """
        select *
        from mart_revenue_churn
        order by month
    """,
    "revenue_retention": """
        select *
        from mart_revenue_retention
        order by month
    """,
    "retention_segments": """
        select *
        from mart_retention_segments
        order by segment_type, segment_value
    """,
    "retention_behavior": """
        select *
        from mart_retention_behavior
        order by retention_status
    """,
}

REQUIRED_MODELS = {
    "dim_account",
    "fact_subscriptions",
    "fact_product_events",
    "mart_activation",
    "mart_feature_adoption",
    "mart_account_activity",
    "mart_retention_cohorts",
    "mart_logo_churn",
    "mart_revenue_churn",
    "mart_revenue_retention",
    "mart_retention_segments",
    "mart_retention_behavior",
}


class DashboardDataError(RuntimeError):
    """Raised when the dashboard database cannot provide its required models."""


def streaming_signature(
    streaming_path: Path = DEFAULT_STREAMING_EVENTS_PATH,
) -> Tuple[str, int, int]:
    """Return a cache key that changes whenever a streamed Parquet file changes."""

    resolved_path = streaming_path.resolve()
    files = list(resolved_path.glob("*.parquet")) if resolved_path.exists() else []
    latest_mtime_ns = max((path.stat().st_mtime_ns for path in files), default=0)
    return str(resolved_path), len(files), latest_mtime_ns


@st.cache_data(ttl=5, show_spinner=False)
def load_streaming_status(
    streaming_path: str,
    file_count: int,
    latest_mtime_ns: int,
) -> Dict[str, object]:
    """Measure raw Kafka-event volume and freshness without altering dbt data."""

    _ = latest_mtime_ns
    if file_count == 0:
        return {
            "events_received": 0,
            "latest_event_timestamp": None,
            "seconds_since_last_event": None,
        }
    glob_path = str(Path(streaming_path) / "*.parquet").replace("'", "''")
    try:
        result = duckdb.sql(
            "select count(distinct event_id), max(event_timestamp) "
            f"from read_parquet('{glob_path}', union_by_name=true)"
        ).fetchone()
    except duckdb.Error as exc:
        raise DashboardDataError(f"Could not read streamed events: {exc}") from exc
    latest = result[1]
    seconds_since = None
    if latest is not None:
        latest_utc = pd.Timestamp(latest)
        if latest_utc.tzinfo is None:
            latest_utc = latest_utc.tz_localize("UTC")
        else:
            latest_utc = latest_utc.tz_convert("UTC")
        seconds_since = max(
            0.0,
            (pd.Timestamp.now(tz="UTC") - latest_utc).total_seconds(),
        )
    return {
        "events_received": int(result[0]),
        "latest_event_timestamp": latest,
        "seconds_since_last_event": seconds_since,
    }


def database_signature(
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> Tuple[str, int]:
    """Return the absolute path and modification time used by the cache key."""

    resolved_path = database_path.resolve()
    if not resolved_path.exists():
        raise DashboardDataError(
            "Dashboard data is unavailable. Run `dbt run` locally or use the "
            "bundled portfolio demo database."
        )
    return str(resolved_path), resolved_path.stat().st_mtime_ns


@st.cache_data(ttl=300, show_spinner=False)
def load_dashboard_data(
    database_path: str,
    database_mtime_ns: int,
) -> Dict[str, pd.DataFrame]:
    """Load all dashboard inputs through one short-lived read-only connection.

    ``database_mtime_ns`` is intentionally part of the function signature. A
    new dbt build updates the database file and therefore invalidates this
    cached result immediately, even before the five-minute TTL expires.
    """

    # Referencing the value makes its role explicit while Streamlit uses it as
    # part of the cache key.
    _ = database_mtime_ns

    try:
        connection = duckdb.connect(database_path, read_only=True)
    except duckdb.Error as exc:
        raise DashboardDataError(f"Could not open DuckDB: {exc}") from exc

    try:
        available_models = {
            row[0] for row in connection.execute("show tables").fetchall()
        }
        missing_models = sorted(REQUIRED_MODELS - available_models)
        if missing_models:
            missing_text = ", ".join(missing_models)
            raise DashboardDataError(
                f"Required dbt models are missing: {missing_text}. "
                "Run `dbt run` inside analytics_dbt."
            )

        return {
            name: connection.execute(query).fetchdf()
            for name, query in MODEL_QUERIES.items()
        }
    except duckdb.Error as exc:
        raise DashboardDataError(f"DuckDB query failed: {exc}") from exc
    finally:
        connection.close()
