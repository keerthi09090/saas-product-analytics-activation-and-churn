"""Smoke tests for the dependency-light public portfolio dashboard."""

from __future__ import annotations

from pathlib import Path

import duckdb
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_DATABASE = PROJECT_ROOT / "data" / "demo" / "analytics_demo.duckdb"
DEMO_SCORES = PROJECT_ROOT / "data" / "demo" / "churn_risk_scores.parquet"
REQUIRED_DEMO_MODELS = {
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


def test_demo_bundle_contains_every_dashboard_model() -> None:
    assert DEMO_DATABASE.exists()
    assert DEMO_SCORES.exists()

    connection = duckdb.connect(str(DEMO_DATABASE), read_only=True)
    try:
        tables = {row[0] for row in connection.execute("show tables").fetchall()}
        assert REQUIRED_DEMO_MODELS <= tables
        assert connection.execute("select count(*) from dim_account").fetchone()[0] == 100
        assert connection.execute(
            "select count(*) from fact_product_events"
        ).fetchone()[0] > 0
    finally:
        connection.close()


def test_all_public_dashboard_pages_render_without_local_services(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_DATABASE_PATH", str(DEMO_DATABASE))
    monkeypatch.delenv("CHURN_API_URL", raising=False)
    monkeypatch.delenv("CHURN_API_BASE_URL", raising=False)

    app = AppTest.from_file(str(PROJECT_ROOT / "dashboard" / "app.py"))
    app.run(timeout=30)
    assert not app.exception
    assert any("Executive Overview" in header.value for header in app.header)

    navigation = app.sidebar.radio[0]
    navigation.set_value("Retention & Churn").run(timeout=30)
    assert not app.exception
    assert any("Retention & Churn" in header.value for header in app.header)

    navigation = app.sidebar.radio[0]
    navigation.set_value("Churn Risk").run(timeout=30)
    assert not app.exception
    assert any(title.value == "Churn Risk" for title in app.title)
    visible_text = " ".join(
        item.value for item in [*app.caption, *app.info, *app.sidebar.info]
    )
    assert "Demo Mode" in visible_text
    assert "localhost" not in visible_text
