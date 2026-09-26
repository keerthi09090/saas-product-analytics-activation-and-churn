"""Level 9 snapshot idempotency and orchestration safeguards."""

import pandas as pd
import pytest

from pipelines.snapshots import (
    PROJECT_ROOT,
    parse_logical_date,
    snapshot_path,
    write_snapshot,
)


@pytest.mark.parametrize("invalid", ["2026/09/25", "not-a-date", "2026-02-30"])
def test_invalid_snapshot_date_fails_clearly(invalid):
    with pytest.raises(ValueError, match="expected YYYY-MM-DD"):
        parse_logical_date(invalid)


def test_snapshot_path_uses_logical_date(tmp_path):
    logical_date = parse_logical_date("2026-09-25")
    assert snapshot_path("accounts", logical_date, tmp_path) == (
        tmp_path / "accounts" / "date=2026-09-25" / "accounts.parquet"
    )


@pytest.mark.parametrize(
    ("dataset", "primary_key"),
    [
        ("accounts", "account_id"),
        ("subscriptions", "subscription_id"),
        ("invoices", "invoice_id"),
    ],
)
def test_same_logical_date_is_idempotent_and_valid(
    tmp_path, dataset, primary_key
):
    first_path = write_snapshot(dataset, "2026-09-25", snapshot_root=tmp_path)
    first = pd.read_parquet(first_path).sort_values(primary_key).reset_index(drop=True)

    second_path = write_snapshot(dataset, "2026-09-25", snapshot_root=tmp_path)
    second = pd.read_parquet(second_path).sort_values(primary_key).reset_index(drop=True)

    assert first_path == second_path
    assert first_path.exists()
    assert first[primary_key].notna().all()
    assert first[primary_key].is_unique
    pd.testing.assert_frame_equal(first, second)
    assert len(list(first_path.parent.glob("*.parquet"))) == 1


def test_backfill_dates_create_separate_partitions(tmp_path):
    dates = ["2026-09-21", "2026-09-22", "2026-09-23"]
    paths = [write_snapshot("accounts", value, tmp_path) for value in dates]

    assert len(set(paths)) == len(dates)
    assert all(path.exists() for path in paths)
    assert {path.parent.name for path in paths} == {
        "date=2026-09-21",
        "date=2026-09-22",
        "date=2026-09-23",
    }


def test_dbt_test_is_a_required_gate_before_daily_scoring():
    dag_path = PROJECT_ROOT / "airflow" / "dags" / "daily_saas_pipeline.py"
    source = dag_path.read_text(encoding="utf-8")

    assert ">> dbt_run" in source
    assert ">> dbt_test" in source
    assert ">> refresh_churn_scores" in source
    assert source.index(">> dbt_run") < source.index(">> dbt_test")
    assert source.index(">> dbt_test") < source.index(">> refresh_churn_scores")
