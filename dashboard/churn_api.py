"""Small cached client for the Level 7 churn-risk API."""

from __future__ import annotations

import json
import os
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import streamlit as st


# Docker Desktop publishes the monitored API on localhost. The environment
# variable remains available for users who run the API elsewhere.
DEFAULT_API_BASE_URL = "http://localhost:8000"
API_BASE_URL = os.getenv("CHURN_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")
API_TIMEOUT_SECONDS = 2.0


class ChurnAPIError(RuntimeError):
    """Raised when the churn API cannot provide a valid response."""


def _request_json(path: str, params: Dict[str, Any] | None = None) -> dict:
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


@st.cache_data(ttl=15, show_spinner=False)
def load_api_health() -> dict:
    return _request_json("/health")


@st.cache_data(ttl=30, show_spinner=False)
def load_churn_summary() -> dict:
    return _request_json("/v1/churn/summary")


@st.cache_data(ttl=30, show_spinner=False)
def load_highest_risk_accounts(limit: int = 10) -> dict:
    return _request_json("/v1/churn", {"limit": limit})


@st.cache_data(ttl=30, show_spinner=False)
def load_account_churn_risk(account_id: str) -> dict:
    normalized = account_id.strip().upper()
    if not normalized:
        raise ChurnAPIError("Enter an account ID")
    return _request_json(f"/v1/churn/{normalized}")
