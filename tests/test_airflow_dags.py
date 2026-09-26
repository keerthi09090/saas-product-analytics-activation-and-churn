"""Lightweight CI import checks for Level 9 DAG definitions.

Airflow itself is integration-tested by Docker locally. These tests provide
fast push/PR protection against syntax, import, DAG ID, and task-chain errors
without installing or launching the complete Airflow platform in basic CI.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path
from types import ModuleType

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeDAG:
    current = None

    def __init__(self, dag_id, **kwargs):
        self.dag_id = dag_id
        self.default_args = kwargs.get("default_args", {})
        self.task_ids = []

    def __enter__(self):
        FakeDAG.current = self
        return self

    def __exit__(self, *_args):
        FakeDAG.current = None


class FakeBashOperator:
    def __init__(self, task_id, **_kwargs):
        self.task_id = task_id
        if FakeDAG.current is not None:
            FakeDAG.current.task_ids.append(task_id)

    def __rshift__(self, other):
        return other


@pytest.fixture
def airflow_stubs(monkeypatch):
    airflow = ModuleType("airflow")
    airflow.DAG = FakeDAG
    operators = ModuleType("airflow.operators")
    bash = ModuleType("airflow.operators.bash")
    bash.BashOperator = FakeBashOperator
    monkeypatch.setitem(sys.modules, "airflow", airflow)
    monkeypatch.setitem(sys.modules, "airflow.operators", operators)
    monkeypatch.setitem(sys.modules, "airflow.operators.bash", bash)


@pytest.mark.parametrize(
    ("filename", "dag_id", "expected_tasks"),
    [
        (
            "daily_saas_pipeline.py",
            "daily_saas_pipeline",
            {
                "snapshot_accounts",
                "snapshot_subscriptions",
                "snapshot_invoices",
                "dbt_run",
                "dbt_test",
                "refresh_churn_scores",
            },
        ),
        (
            "backfill_saas_pipeline.py",
            "backfill_saas_pipeline",
            {
                "snapshot_accounts",
                "snapshot_subscriptions",
                "snapshot_invoices",
                "dbt_run",
                "dbt_test",
            },
        ),
    ],
)
def test_airflow_dag_imports_without_errors(
    airflow_stubs, filename, dag_id, expected_tasks
):
    namespace = runpy.run_path(str(PROJECT_ROOT / "airflow" / "dags" / filename))
    dag = namespace["dag"]
    assert dag.dag_id == dag_id
    assert set(dag.task_ids) == expected_tasks
    assert dag.default_args["retries"] == 2
