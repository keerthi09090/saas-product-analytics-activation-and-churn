"""Permutation importance and human-readable account risk signals."""

from __future__ import annotations

import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.inspection import permutation_importance

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.utils import (
    FEATURE_COLUMNS,
    IMPORTANCE_PATH,
    MODEL_PATH,
    TARGET_COLUMN,
    load_training_dataset,
    temporal_split,
)


def calculate_feature_importance(
    model, features: pd.DataFrame, labels: pd.Series
) -> pd.DataFrame:
    """Measure original-column importance on the held-out future period."""

    result = permutation_importance(
        model,
        features[FEATURE_COLUMNS],
        labels,
        scoring="average_precision",
        n_repeats=20,
        random_state=42,
    )
    return pd.DataFrame(
        {
            "feature": FEATURE_COLUMNS,
            "importance_mean": result.importances_mean,
            "importance_std": result.importances_std,
        }
    ).sort_values("importance_mean", ascending=False, ignore_index=True)


def account_risk_reasons(row: pd.Series) -> list[str]:
    """Return up to three descriptive, non-causal signals for one account."""

    reasons: list[str] = []
    if row.get("event_change_pct", 0) <= -0.30:
        reasons.append(
            f"activity declined {abs(row['event_change_pct']):.0%} versus the prior 30 days"
        )
    if row.get("seat_utilization", 1) < 0.25:
        reasons.append(
            f"only {row['seat_utilization']:.0%} of purchased seats were active"
        )
    if row.get("days_since_last_activity", 0) >= 14:
        reasons.append(
            f"last product activity was {int(row['days_since_last_activity'])} days ago"
        )
    if row.get("reports_created_last_30d", 0) == 0:
        if pd.notna(row.get("days_since_last_report")):
            reasons.append(
                f"no recent reports; last report was {int(row['days_since_last_report'])} days ago"
            )
        else:
            reasons.append("no report has been created")
    if row.get("failed_payments_last_90d", 0) > 0:
        count = int(row["failed_payments_last_90d"])
        reasons.append(f"{count} failed payment{'s' if count != 1 else ''} in 90 days")
    if row.get("integrations_connected", 0) == 0:
        reasons.append("no integration was connected")
    if row.get("active_users_last_30d", 0) <= 1:
        reasons.append("one or fewer active users in the last 30 days")
    if not reasons:
        reasons.append("risk reflects the combined model pattern rather than one dominant signal")
    return reasons[:3]


def main() -> None:
    bundle = joblib.load(MODEL_PATH)
    frame = load_training_dataset()
    _, _, test, _ = temporal_split(frame)
    importance = calculate_feature_importance(
        bundle["pipeline"], test, test[TARGET_COLUMN]
    )
    importance.to_csv(IMPORTANCE_PATH, index=False)
    print("\nTop model features (permutation importance)\n")
    print(importance.head(10).to_string(index=False))
    print(f"\nSaved: {IMPORTANCE_PATH.relative_to(IMPORTANCE_PATH.parent.parent)}")


if __name__ == "__main__":
    main()
