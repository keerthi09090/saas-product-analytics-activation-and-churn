"""Package the small, deterministic data used by the public Streamlit demo.

Run this after a clean ``dbt run``. The script copies only the twelve models
read by the dashboard plus the existing Level 6 churn-score artifact. It never
duplicates raw event files or retrains a model.
"""

from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_MODELS = (
    "dim_account",
    "fact_subscriptions",
    "fact_product_events",
    "mart_activation",
    "mart_feature_adoption",
    "mart_account_activity",
    "mart_retention_cohorts",
    "mart_logo_churn",
    "mart_revenue_churn",
    "mart_revenue_retention",
    "mart_retention_segments",
    "mart_retention_behavior",
)


def create_demo_data(
    source_database: Path,
    source_scores: Path,
    output_directory: Path,
) -> None:
    """Create a compact DuckDB file and copy the real saved scoring artifact."""

    source_database = source_database.resolve()
    source_scores = source_scores.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)

    if not source_database.exists():
        raise FileNotFoundError(f"Source DuckDB file not found: {source_database}")
    if not source_scores.exists():
        raise FileNotFoundError(f"Score artifact not found: {source_scores}")

    with tempfile.TemporaryDirectory(dir=output_directory) as temporary_directory:
        temporary_database = Path(temporary_directory) / "analytics_demo.duckdb"
        connection = duckdb.connect(str(temporary_database))
        try:
            escaped_source = str(source_database).replace("'", "''")
            connection.execute(f"attach '{escaped_source}' as source (read_only)")
            available = {
                row[0]
                for row in connection.execute(
                    "select table_name from duckdb_tables() "
                    "where database_name = 'source' and schema_name = 'main'"
                ).fetchall()
            }
            missing = sorted(set(REQUIRED_MODELS) - available)
            if missing:
                raise RuntimeError(
                    "Source DuckDB is missing required models: " + ", ".join(missing)
                )
            for model in REQUIRED_MODELS:
                connection.execute(
                    f"create table main.{model} as select * from source.main.{model}"
                )
            connection.execute("checkpoint")
        finally:
            connection.close()

        shutil.copyfile(temporary_database, output_directory / "analytics_demo.duckdb")

    shutil.copyfile(source_scores, output_directory / "churn_risk_scores.parquet")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-database",
        type=Path,
        default=PROJECT_ROOT / "analytics_dbt" / "analytics.duckdb",
    )
    parser.add_argument(
        "--source-scores",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "churn_risk_scores.parquet",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=PROJECT_ROOT / "data" / "demo",
    )
    arguments = parser.parse_args()
    create_demo_data(
        arguments.source_database,
        arguments.source_scores,
        arguments.output_directory,
    )
    print(f"Created portfolio demo data in {arguments.output_directory}")


if __name__ == "__main__":
    main()
