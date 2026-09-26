"""Typed API response contracts."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from api.config import SCORE_DESCRIPTION


RiskBucket = Literal["Low", "Medium", "High"]


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ChurnPrediction(BaseModel):
    """A precomputed account risk score with human-readable context."""

    account_id: str = Field(description="Synthetic SaaS account identifier.")
    churn_score: float = Field(ge=0, le=1, description=SCORE_DESCRIPTION)
    risk_bucket: RiskBucket
    prediction_date: date
    monthly_revenue: float = Field(ge=0)
    top_reasons: list[str] = Field(
        description="Descriptive account signals; these are not causal claims."
    )


class ChurnAccountList(BaseModel):
    count: int = Field(ge=0)
    accounts: list[ChurnPrediction]


class ChurnSummary(BaseModel):
    scored_accounts: int = Field(ge=0)
    high_risk_accounts: int = Field(ge=0)
    medium_risk_accounts: int = Field(ge=0)
    low_risk_accounts: int = Field(ge=0)
    high_risk_monthly_revenue: float = Field(ge=0)
