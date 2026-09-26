"""Idempotent, logical-date-aware snapshots used by Airflow DAG tasks."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Callable
from uuid import uuid4

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_SNAPSHOT_ROOT = DATA_DIR / "snapshots"
LOGGER = logging.getLogger("pipelines.snapshots")


def parse_logical_date(value: str) -> date:
    """Parse an Airflow logical date and fail with a beginner-friendly message."""

    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid snapshot date {value!r}; expected YYYY-MM-DD."
        ) from exc


def snapshot_path(dataset: str, logical_date: date, root: Path) -> Path:
    return root / dataset / f"date={logical_date.isoformat()}" / f"{dataset}.parquet"


def _as_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.date


def _accounts_as_of(frame: pd.DataFrame, logical_date: date) -> pd.DataFrame:
    created = _as_date(frame["account_created_at"])
    return frame.loc[created <= logical_date].copy()


def _subscriptions_as_of(frame: pd.DataFrame, logical_date: date) -> pd.DataFrame:
    trial_start = _as_date(frame["trial_start_date"])
    subscription_start = _as_date(frame["subscription_start_date"])
    cancellation = _as_date(frame["cancellation_date"])
    snapshot = frame.loc[trial_start <= logical_date].copy()
    snapshot_subscription_start = subscription_start.loc[snapshot.index]
    snapshot_cancellation = cancellation.loc[snapshot.index]
    snapshot["subscription_status"] = "trial"
    snapshot.loc[
        snapshot_subscription_start.notna()
        & (snapshot_subscription_start <= logical_date),
        "subscription_status",
    ] = "active"
    snapshot.loc[
        snapshot_cancellation.notna() & (snapshot_cancellation <= logical_date),
        "subscription_status",
    ] = "cancelled"
    return snapshot


def _invoices_as_of(frame: pd.DataFrame, logical_date: date) -> pd.DataFrame:
    invoice_date = _as_date(frame["invoice_date"])
    return frame.loc[invoice_date <= logical_date].copy()


DATASET_CONFIG: dict[str, tuple[str, str, Callable[[pd.DataFrame, date], pd.DataFrame]]] = {
    "accounts": ("accounts.parquet", "account_id", _accounts_as_of),
    "subscriptions": (
        "subscriptions.parquet",
        "subscription_id",
        _subscriptions_as_of,
    ),
    "invoices": ("invoices.parquet", "invoice_id", _invoices_as_of),
}


def write_snapshot(
    dataset: str,
    logical_date_value: str,
    snapshot_root: Path = DEFAULT_SNAPSHOT_ROOT,
    data_dir: Path = DATA_DIR,
) -> Path:
    """Build and atomically overwrite one deterministic date partition."""

    if dataset not in DATASET_CONFIG:
        raise ValueError(f"Unsupported snapshot dataset: {dataset}")
    logical_date = parse_logical_date(logical_date_value)
    input_name, primary_key, transform = DATASET_CONFIG[dataset]
    input_path = data_dir / input_name
    output_path = snapshot_path(dataset, logical_date, snapshot_root)

    LOGGER.info("Snapshot date: %s", logical_date)
    LOGGER.info("Input: %s", input_path)
    frame = pd.read_parquet(input_path)
    snapshot = transform(frame, logical_date)
    snapshot["snapshot_date"] = logical_date
    if snapshot[primary_key].isna().any():
        raise ValueError(f"{dataset} snapshot contains null {primary_key}")
    if snapshot[primary_key].duplicated().any():
        raise ValueError(f"{dataset} snapshot contains duplicate {primary_key}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(
        f".{output_path.stem}.{uuid4().hex}.tmp.parquet"
    )
    snapshot.to_parquet(temporary_path, index=False)
    temporary_path.replace(output_path)
    LOGGER.info("%s written: %s", dataset.capitalize(), len(snapshot))
    LOGGER.info("Output: %s", output_path)
    LOGGER.info("Snapshot succeeded")
    return output_path
