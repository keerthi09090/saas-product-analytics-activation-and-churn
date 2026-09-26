"""Refresh Level 6 scores after the Airflow dbt quality gate passes."""

from __future__ import annotations

import argparse
import logging

from ml.score_accounts import score_current_accounts
from ml.utils import RISK_SCORES_PATH
from pipelines.snapshots import parse_logical_date


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh active-account churn scores")
    parser.add_argument("--logical-date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logical_date = parse_logical_date(args.logical_date)
    logging.info("Logical date: %s", logical_date)
    logging.info("Scoring input: analytics_dbt/analytics.duckdb")
    scores = score_current_accounts()
    logging.info("Accounts scored: %s", len(scores))
    logging.info("Output: %s", RISK_SCORES_PATH)
    logging.info("Churn score refresh succeeded")


if __name__ == "__main__":
    main()
