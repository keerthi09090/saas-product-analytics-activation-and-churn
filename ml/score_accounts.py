"""Score currently active paid accounts and attach retention-team reasons."""

from __future__ import annotations

import sys
from pathlib import Path

import joblib
import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.build_dataset import build_current_scoring_dataset
from ml.explain import account_risk_reasons
from ml.utils import FEATURE_COLUMNS, MODEL_PATH, RISK_SCORES_PATH, ensure_artifact_dir


def risk_bucket(probability: float, high: float = 0.60, medium: float = 0.30) -> str:
    if probability >= high:
        return "High"
    if probability >= medium:
        return "Medium"
    return "Low"


def score_current_accounts() -> pd.DataFrame:
    ensure_artifact_dir()
    bundle = joblib.load(MODEL_PATH)
    frame = build_current_scoring_dataset()
    probabilities = bundle["pipeline"].predict_proba(frame[FEATURE_COLUMNS])[:, 1]
    thresholds = bundle["risk_thresholds"]
    rows = []
    for (_, account), probability in zip(frame.iterrows(), probabilities):
        reasons = account_risk_reasons(account)
        rows.append(
            {
                "account_id": account.account_id,
                "prediction_date": account.prediction_date,
                "churn_probability": float(probability),
                "risk_bucket": risk_bucket(
                    probability,
                    high=thresholds["high"],
                    medium=thresholds["medium"],
                ),
                "top_reason_1": reasons[0] if len(reasons) > 0 else None,
                "top_reason_2": reasons[1] if len(reasons) > 1 else None,
                "top_reason_3": reasons[2] if len(reasons) > 2 else None,
                "monthly_revenue": float(account.monthly_revenue),
            }
        )
    scores = pd.DataFrame(rows).sort_values(
        ["churn_probability", "monthly_revenue"], ascending=[False, False]
    ).reset_index(drop=True)
    scores.to_parquet(RISK_SCORES_PATH, index=False)
    return scores


def main() -> None:
    scores = score_current_accounts()
    high_risk = scores[scores.risk_bucket == "High"]
    print("\nCurrent Active-Account Churn Risk\n")
    print(f"Scored accounts: {len(scores):,}")
    print(f"High-risk accounts: {len(high_risk):,}")
    print(f"High-risk monthly revenue: ${high_risk.monthly_revenue.sum():,.0f}")
    print("\nHighest-risk accounts\n")
    print(
        scores[
            [
                "account_id",
                "churn_probability",
                "risk_bucket",
                "top_reason_1",
                "monthly_revenue",
            ]
        ]
        .head(10)
        .to_string(index=False)
    )
    print(f"\nSaved: {RISK_SCORES_PATH.relative_to(RISK_SCORES_PATH.parent.parent)}")
    print("Probabilities are ranking scores and are not claimed to be calibrated.")


if __name__ == "__main__":
    main()
