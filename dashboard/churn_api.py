"""Churn-risk data access for the API-backed and public-demo dashboard modes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import streamlit as st
import pandas as pd


# The hosted portfolio demo deliberately has no API dependency. Setting
# CHURN_API_URL switches the page to the Level 7 FastAPI service. The older
# CHURN_API_BASE_URL name remains supported for local backwards compatibility.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_SCORES_PATH = PROJECT_ROOT / "data" / "demo" / "churn_risk_scores.parquet"
API_BASE_URL = (
    os.getenv("CHURN_API_URL") or os.getenv("CHURN_API_BASE_URL") or ""
).rstrip("/")
USING_DEMO_SCORES = not bool(API_BASE_URL)
CHURN_SOURCE_LABEL = (
    "Level 7 FastAPI" if API_BASE_URL else "Demo Mode · saved Level 6 scores"
)
API_TIMEOUT_SECONDS = 2.0


class ChurnAPIError(RuntimeError):
    """Raised when the churn API cannot provide a valid response."""


def _request_json(path: str, params: Dict[str, Any] | None = None) -> dict:
    if not API_BASE_URL:
        raise ChurnAPIError("No churn API URL is configured")
    query = f"?{urlencode(params)}" if params else ""
    url = f"{API_BASE_URL}{path}{query}"
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            raise ChurnAPIError("Account not found") from exc
        raise ChurnAPIError(
            f"Churn API returned HTTP {exc.code}."
        ) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ChurnAPIError("Churn API is unavailable") from exc


@st.cache_data(show_spinner=False)
def _load_demo_scores() -> pd.DataFrame:
    """Load the real saved Level 6 scoring artifact for public demo mode."""

    if not DEMO_SCORES_PATH.exists():
        raise ChurnAPIError("The bundled churn-risk demo data is unavailable")
    try:
        scores = pd.read_parquet(DEMO_SCORES_PATH)
    except (OSError, ValueError) as exc:
        raise ChurnAPIError("The bundled churn-risk demo data is unavailable") from exc

    required = {
        "account_id",
        "prediction_date",
        "churn_probability",
        "risk_bucket",
        "monthly_revenue",
        "top_reason_1",
    }
    missing = sorted(required - set(scores.columns))
    if missing:
        raise ChurnAPIError("The bundled churn-risk demo data is invalid")
    return scores


def _demo_account(row: pd.Series) -> dict:
    reasons = [
        str(row[column])
        for column in ("top_reason_1", "top_reason_2", "top_reason_3")
        if column in row.index and pd.notna(row[column]) and str(row[column]).strip()
    ]
    prediction_date = pd.Timestamp(row["prediction_date"])
    return {
        "account_id": str(row["account_id"]),
        "prediction_date": prediction_date.date().isoformat(),
        "churn_score": float(row["churn_probability"]),
        "risk_bucket": str(row["risk_bucket"]),
        "monthly_revenue": float(row["monthly_revenue"]),
        "top_reasons": reasons,
    }


@st.cache_data(ttl=15, show_spinner=False)
def load_api_health() -> dict:
    if USING_DEMO_SCORES:
        _load_demo_scores()
        return {"status": "ok", "mode": "demo"}
    return _request_json("/health")


@st.cache_data(ttl=30, show_spinner=False)
def load_churn_summary() -> dict:
    if USING_DEMO_SCORES:
        scores = _load_demo_scores()
        buckets = scores["risk_bucket"].str.lower()
        high = buckets.eq("high")
        return {
            "scored_accounts": int(len(scores)),
            "high_risk_accounts": int(high.sum()),
            "medium_risk_accounts": int(buckets.eq("medium").sum()),
            "low_risk_accounts": int(buckets.eq("low").sum()),
            "high_risk_monthly_revenue": float(
                scores.loc[high, "monthly_revenue"].sum()
            ),
        }
    return _request_json("/v1/churn/summary")


@st.cache_data(ttl=30, show_spinner=False)
def load_highest_risk_accounts(limit: int = 10) -> dict:
    if USING_DEMO_SCORES:
        scores = _load_demo_scores().sort_values(
            ["churn_probability", "account_id"], ascending=[False, True]
        )
        accounts = [_demo_account(row) for _, row in scores.head(limit).iterrows()]
        return {"count": len(accounts), "accounts": accounts}
    return _request_json("/v1/churn", {"limit": limit})


@st.cache_data(ttl=30, show_spinner=False)
def load_account_churn_risk(account_id: str) -> dict:
    normalized = account_id.strip().upper()
    if not normalized:
        raise ChurnAPIError("Enter an account ID")
    if USING_DEMO_SCORES:
        scores = _load_demo_scores()
        match = scores.loc[scores["account_id"].str.upper().eq(normalized)]
        if match.empty:
            raise ChurnAPIError("Account not found")
        return _demo_account(match.iloc[0])
    return _request_json(f"/v1/churn/{normalized}")
