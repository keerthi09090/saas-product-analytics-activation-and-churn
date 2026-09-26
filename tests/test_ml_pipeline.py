"""Level 6 tests for snapshot integrity, leakage prevention, and scoring."""

from __future__ import annotations

import joblib
import numpy as np
import pandas as pd
import pytest

from ml.build_dataset import build_current_scoring_dataset
from ml.utils import (
    DATASET_PATH,
    FEATURE_COLUMNS,
    MODEL_PATH,
    PROJECT_ROOT,
    RISK_SCORES_PATH,
    TARGET_COLUMN,
    load_training_dataset,
    temporal_split,
)


@pytest.fixture(scope="module")
def snapshots() -> pd.DataFrame:
    assert DATASET_PATH.exists(), "Run python ml/build_dataset.py first"
    return load_training_dataset()


def test_snapshot_keys_and_ranges_are_valid(snapshots: pd.DataFrame):
    assert not snapshots.duplicated(["account_id", "prediction_date"]).any()
    assert snapshots.account_id.notna().all()
    assert snapshots.prediction_date.notna().all()
    assert snapshots[TARGET_COLUMN].isin([0, 1]).all()
    assert snapshots.seat_utilization.between(0, 1).all()

    count_columns = [
        column
        for column in FEATURE_COLUMNS
        if column.endswith("_30d")
        or column.endswith("_90d")
        or column in {"events_last_7d", "integrations_connected", "total_failed_payments"}
    ]
    # Change features may legitimately be negative; event/count inputs may not.
    count_columns = [column for column in count_columns if "change" not in column]
    assert (snapshots[count_columns] >= 0).all().all()


def test_features_never_look_past_prediction_date(snapshots: pd.DataFrame):
    cutoff = snapshots.prediction_date.dt.date
    event_date = pd.to_datetime(snapshots.latest_event_at, utc=True).dt.date
    invoice_date = pd.to_datetime(snapshots.latest_invoice_date).dt.date

    assert (event_date[event_date.notna()] <= cutoff[event_date.notna()]).all()
    assert (invoice_date[invoice_date.notna()] <= cutoff[invoice_date.notna()]).all()


def test_churn_label_is_exactly_the_next_30_days(snapshots: pd.DataFrame):
    subscriptions = pd.read_parquet(PROJECT_ROOT / "data" / "subscriptions.parquet")
    subscriptions["cancellation_date"] = pd.to_datetime(
        subscriptions.cancellation_date
    )
    checked = snapshots.merge(
        subscriptions[["account_id", "cancellation_date"]],
        on="account_id",
        how="left",
        validate="many_to_one",
    )
    expected = (
        checked.cancellation_date.notna()
        & (checked.cancellation_date > checked.prediction_date)
        & (
            checked.cancellation_date
            <= checked.prediction_date + pd.Timedelta(days=30)
        )
    ).astype(int)

    assert np.array_equal(checked[TARGET_COLUMN].to_numpy(), expected.to_numpy())
    assert not (
        checked.cancellation_date.notna()
        & (checked.prediction_date >= checked.cancellation_date)
    ).any()


def test_temporal_split_has_no_overlap_or_future_training(snapshots: pd.DataFrame):
    train, validation, test, _ = temporal_split(snapshots)
    train_keys = set(zip(train.account_id, train.prediction_date))
    validation_keys = set(zip(validation.account_id, validation.prediction_date))
    test_keys = set(zip(test.account_id, test.prediction_date))

    assert train_keys.isdisjoint(validation_keys)
    assert train_keys.isdisjoint(test_keys)
    assert validation_keys.isdisjoint(test_keys)
    assert train.prediction_date.max() < validation.prediction_date.min()
    assert validation.prediction_date.max() < test.prediction_date.min()


def test_target_and_post_outcome_fields_are_not_model_features():
    assert TARGET_COLUMN not in FEATURE_COLUMNS
    assert "cancellation_date" not in FEATURE_COLUMNS
    assert "subscription_status" not in FEATURE_COLUMNS


def test_saved_model_outputs_valid_probabilities(snapshots: pd.DataFrame):
    assert MODEL_PATH.exists(), "Run python ml/train.py first"
    _, _, test, _ = temporal_split(snapshots)
    bundle = joblib.load(MODEL_PATH)
    probabilities = bundle["pipeline"].predict_proba(test[FEATURE_COLUMNS])[:, 1]

    assert len(probabilities) == len(test)
    assert np.isfinite(probabilities).all()
    assert ((probabilities >= 0) & (probabilities <= 1)).all()


def test_current_scoring_data_contains_only_features_not_labels():
    scoring = build_current_scoring_dataset()
    subscriptions = pd.read_parquet(PROJECT_ROOT / "data" / "subscriptions.parquet")
    expected_active = set(
        subscriptions.loc[
            subscriptions.subscription_status == "active", "account_id"
        ]
    )

    assert set(scoring.account_id) == expected_active
    assert TARGET_COLUMN not in scoring.columns
    assert "cancellation_date" not in scoring.columns
    assert set(FEATURE_COLUMNS) <= set(scoring.columns)


def test_risk_score_artifact_has_valid_contract():
    assert RISK_SCORES_PATH.exists(), "Run python ml/score_accounts.py first"
    scores = pd.read_parquet(RISK_SCORES_PATH)
    expected_columns = {
        "account_id",
        "prediction_date",
        "churn_probability",
        "risk_bucket",
        "monthly_revenue",
        "top_reason_1",
        "top_reason_2",
        "top_reason_3",
    }
    assert expected_columns <= set(scores.columns)
    assert not scores.duplicated(["account_id", "prediction_date"]).any()
    assert scores.churn_probability.between(0, 1).all()
    assert scores.risk_bucket.isin(["Low", "Medium", "High"]).all()
