"""Load Level 6 scores once and provide read-only lookup operations."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from api.schemas import ChurnPrediction, ChurnSummary, RiskBucket


REQUIRED_COLUMNS = {
    "account_id",
    "prediction_date",
    "churn_probability",
    "risk_bucket",
    "monthly_revenue",
    "top_reason_1",
    "top_reason_2",
    "top_reason_3",
}


class ChurnScoreService:
    """In-memory view of a single completed Level 6 scoring run."""

    def __init__(self, scores: pd.DataFrame):
        missing = REQUIRED_COLUMNS - set(scores.columns)
        if missing:
            raise ValueError(
                "Churn score artifact is missing columns: "
                + ", ".join(sorted(missing))
            )
        if scores.empty:
            raise ValueError("Churn score artifact contains no accounts")
        if scores.account_id.duplicated().any():
            raise ValueError("Churn score artifact contains duplicate account IDs")
        if not scores.churn_probability.between(0, 1).all():
            raise ValueError("Churn scores must be between 0 and 1")
        if not set(scores.risk_bucket).issubset({"Low", "Medium", "High"}):
            raise ValueError("Risk buckets must be Low, Medium, or High")

        prepared = scores.copy()
        prepared["account_id"] = prepared.account_id.astype(str)
        prepared["prediction_date"] = pd.to_datetime(
            prepared.prediction_date
        ).dt.date
        self._scores = prepared.sort_values(
            ["churn_probability", "monthly_revenue"],
            ascending=[False, False],
        ).reset_index(drop=True)
        self._by_account = self._scores.set_index("account_id", drop=False)

    @classmethod
    def load(cls, path: Path) -> "ChurnScoreService":
        if not path.exists():
            raise FileNotFoundError(
                f"Churn score artifact not found at {path}. "
                "Run python ml/score_accounts.py before starting the API."
            )
        return cls(pd.read_parquet(path))

    @staticmethod
    def _to_prediction(row: pd.Series) -> ChurnPrediction:
        reasons = []
        for column in ["top_reason_1", "top_reason_2", "top_reason_3"]:
            value = row[column]
            if pd.notna(value) and str(value).strip():
                reasons.append(str(value).strip())
        return ChurnPrediction(
            account_id=str(row.account_id),
            churn_score=float(row.churn_probability),
            risk_bucket=str(row.risk_bucket),
            prediction_date=row.prediction_date,
            monthly_revenue=float(row.monthly_revenue),
            top_reasons=reasons,
        )

    def get_account(self, account_id: str) -> Optional[ChurnPrediction]:
        normalized = account_id.strip().upper()
        if normalized not in self._by_account.index:
            return None
        return self._to_prediction(self._by_account.loc[normalized])

    def list_accounts(
        self, risk_bucket: Optional[RiskBucket], limit: int
    ) -> list[ChurnPrediction]:
        selected = self._scores
        if risk_bucket is not None:
            selected = selected[selected.risk_bucket == risk_bucket]
        return [
            self._to_prediction(row)
            for _, row in selected.head(limit).iterrows()
        ]

    def summary(self) -> ChurnSummary:
        buckets = self._scores.risk_bucket.value_counts()
        high_risk = self._scores[self._scores.risk_bucket == "High"]
        return ChurnSummary(
            scored_accounts=len(self._scores),
            high_risk_accounts=int(buckets.get("High", 0)),
            medium_risk_accounts=int(buckets.get("Medium", 0)),
            low_risk_accounts=int(buckets.get("Low", 0)),
            high_risk_monthly_revenue=float(high_risk.monthly_revenue.sum()),
        )
