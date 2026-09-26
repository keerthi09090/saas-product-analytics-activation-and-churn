"""Shared paths, features, temporal splitting, and evaluation helpers."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "analytics_dbt" / "analytics.duckdb"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts"
MLRUNS_DIR = PROJECT_ROOT / "mlruns"
DATASET_PATH = ARTIFACT_DIR / "churn_training_data.parquet"
MODEL_PATH = ARTIFACT_DIR / "churn_model.pkl"
BASELINE_MODEL_PATH = ARTIFACT_DIR / "logistic_model.pkl"
METRICS_PATH = ARTIFACT_DIR / "model_metrics.json"
IMPORTANCE_PATH = ARTIFACT_DIR / "feature_importance.csv"
RISK_SCORES_PATH = ARTIFACT_DIR / "churn_risk_scores.parquet"

CATEGORICAL_FEATURES = ["plan", "acquisition_channel"]
NUMERIC_FEATURES = [
    "company_size",
    "seats_purchased",
    "account_age_days",
    "events_last_7d",
    "events_last_30d",
    "events_previous_30d",
    "active_users_last_30d",
    "active_users_previous_30d",
    "reports_created_last_30d",
    "reports_created_previous_30d",
    "reports_exported_last_30d",
    "dashboard_views_last_30d",
    "integrations_connected",
    "invites_sent_last_30d",
    "days_since_last_activity",
    "days_since_last_report",
    "days_since_last_login",
    "event_change_30d",
    "event_change_pct",
    "active_user_change",
    "report_activity_change",
    "seat_utilization",
    "failed_payments_last_90d",
    "total_failed_payments",
    "recent_payment_failed",
    "monthly_revenue",
    "is_activated",
    "days_to_activation",
]
FEATURE_COLUMNS = CATEGORICAL_FEATURES + NUMERIC_FEATURES
TARGET_COLUMN = "churn_label"
NON_FEATURE_COLUMNS = {
    "account_id",
    "prediction_date",
    "latest_event_at",
    "latest_invoice_date",
    TARGET_COLUMN,
}


def ensure_artifact_dir() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def load_training_dataset(path: Path = DATASET_PATH) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    frame["prediction_date"] = pd.to_datetime(frame["prediction_date"])
    return frame.sort_values(["prediction_date", "account_id"]).reset_index(drop=True)


def temporal_split(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, list[str]]]:
    """Use all early months for train and reserve the latest two months."""

    dates = sorted(pd.to_datetime(frame.prediction_date).dt.normalize().unique())
    if len(dates) < 3:
        raise ValueError("At least three prediction dates are required")
    validation_date, test_date = dates[-2], dates[-1]
    train = frame[frame.prediction_date < validation_date].copy()
    validation = frame[frame.prediction_date == validation_date].copy()
    test = frame[frame.prediction_date == test_date].copy()
    periods = {
        "train": [pd.Timestamp(value).date().isoformat() for value in dates[:-2]],
        "validation": [pd.Timestamp(validation_date).date().isoformat()],
        "test": [pd.Timestamp(test_date).date().isoformat()],
    }
    return train, validation, test, periods


def top_decile_lift(y_true: pd.Series, probabilities: np.ndarray) -> float:
    """Return churn concentration in the top-scored 10% versus random."""

    labels = np.asarray(y_true, dtype=float)
    overall_rate = labels.mean()
    if len(labels) == 0 or overall_rate == 0:
        return 0.0
    top_count = max(1, math.ceil(len(labels) * 0.10))
    top_indices = np.argsort(probabilities)[::-1][:top_count]
    return float(labels[top_indices].mean() / overall_rate)


def evaluate_probabilities(
    y_true: pd.Series,
    probabilities: np.ndarray,
    threshold: float = 0.5,
) -> dict[str, object]:
    predictions = (probabilities >= threshold).astype(int)
    labels = np.asarray(y_true, dtype=int)
    matrix = confusion_matrix(labels, predictions, labels=[0, 1])
    roc_auc = (
        float(roc_auc_score(labels, probabilities))
        if len(np.unique(labels)) == 2
        else None
    )
    return {
        "pr_auc": float(average_precision_score(labels, probabilities)),
        "roc_auc": roc_auc,
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "top_10_pct_lift": top_decile_lift(labels, probabilities),
        "confusion_matrix": matrix.tolist(),
        "decision_threshold": threshold,
    }


def choose_validation_threshold(
    y_true: pd.Series, probabilities: np.ndarray
) -> float:
    """Choose a classification threshold on validation data only.

    PR-AUC and lift evaluate ranking and do not need a cutoff. Precision,
    recall, F1, and the confusion matrix do, so the cutoff is selected without
    looking at the future test month. Ties prefer the higher threshold to
    avoid needlessly broad retention outreach.
    """

    candidates = np.unique(np.concatenate(([0.0, 1.0], probabilities)))
    labels = np.asarray(y_true, dtype=int)
    scored = []
    for threshold in candidates:
        predictions = (probabilities >= threshold).astype(int)
        scored.append(
            (
                f1_score(labels, predictions, zero_division=0),
                precision_score(labels, predictions, zero_division=0),
                float(threshold),
            )
        )
    return max(scored)[2]


def metrics_for_mlflow(metrics: dict[str, object], prefix: str) -> dict[str, float]:
    result = {}
    for name, value in metrics.items():
        if isinstance(value, (int, float)) and value is not None and np.isfinite(value):
            result[f"{prefix}_{name}"] = float(value)
    return result


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
