"""Backfill-safe SaaS snapshots and dbt validation for historical dates."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from airflow import DAG
from airflow.operators.bash import BashOperator


PROJECT_ROOT = Path("/opt/airflow/project")
DEFAULT_ARGS = {
    "owner": "saas-analytics",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "execution_timeout": timedelta(minutes=15),
}


with DAG(
    dag_id="backfill_saas_pipeline",
    description="Safely rebuild date-partitioned SaaS snapshots",
    start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["saas", "backfill", "level-9"],
) as dag:
    snapshot_accounts = BashOperator(
        task_id="snapshot_accounts",
        cwd=PROJECT_ROOT,
        bash_command="python -m pipelines.snapshot_accounts --snapshot-date {{ ds }}",
    )
    snapshot_subscriptions = BashOperator(
        task_id="snapshot_subscriptions",
        cwd=PROJECT_ROOT,
        bash_command=(
            "python -m pipelines.snapshot_subscriptions --snapshot-date {{ ds }}"
        ),
    )
    snapshot_invoices = BashOperator(
        task_id="snapshot_invoices",
        cwd=PROJECT_ROOT,
        bash_command="python -m pipelines.snapshot_invoices --snapshot-date {{ ds }}",
    )
    dbt_run = BashOperator(
        task_id="dbt_run",
        cwd=PROJECT_ROOT / "analytics_dbt",
        bash_command="dbt run --profiles-dir .",
    )
    dbt_test = BashOperator(
        task_id="dbt_test",
        cwd=PROJECT_ROOT / "analytics_dbt",
        bash_command="dbt test --profiles-dir .",
    )

    (
        snapshot_accounts
        >> snapshot_subscriptions
        >> snapshot_invoices
        >> dbt_run
        >> dbt_test
    )
