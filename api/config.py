"""Project-relative API configuration."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RISK_SCORES_PATH = PROJECT_ROOT / "artifacts" / "churn_risk_scores.parquet"

API_TITLE = "SaaS Churn Risk API"
API_VERSION = "1.0.0"
DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100

SCORE_DESCRIPTION = (
    "A model-generated churn risk score used for ranking accounts. "
    "It is not claimed to be a calibrated probability."
)
