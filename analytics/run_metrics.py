"""Run the Level 2 DuckDB analysis and print SaaS metrics."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYTICS_DIR = PROJECT_ROOT / "analytics"
DATA_DIR = PROJECT_ROOT / "data"
PARQUET_TABLES = ["accounts", "users", "subscriptions", "invoices", "events"]


def check_input_files() -> None:
    """Fail early with a helpful message when Level 1 has not been run."""

    missing = [
        DATA_DIR / f"{table}.parquet"
        for table in PARQUET_TABLES
        if not (DATA_DIR / f"{table}.parquet").exists()
    ]
    if missing:
        names = ", ".join(path.name for path in missing)
        raise FileNotFoundError(
            f"Missing Level 1 files: {names}. "
            "Run `python -m simulator.generate` first."
        )


def run_sql_file(connection: duckdb.DuckDBPyConnection, filename: str) -> None:
    """Read and execute one SQL file."""

    connection.execute((ANALYTICS_DIR / filename).read_text())


def validate_metrics(
    connection: duckdb.DuckDBPyConnection,
    activation_rate: float,
    conversion_rate: float,
    feature_rows: list[tuple],
) -> None:
    """Validate activation chronology and all rate bounds."""

    invalid_activation_rows = connection.execute(
        """
        SELECT COUNT(*)
        FROM account_activation
        WHERE activation_date < trial_start_date
           OR days_to_activation < 0
        """
    ).fetchone()[0]
    activation_rows, distinct_accounts = connection.execute(
        "SELECT COUNT(*), COUNT(DISTINCT account_id) FROM account_activation"
    ).fetchone()
    source_accounts = connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    inconsistent_nulls = connection.execute(
        """
        SELECT COUNT(*)
        FROM account_activation
        WHERE (activated AND (activation_date IS NULL OR days_to_activation IS NULL))
           OR (NOT activated AND (activation_date IS NOT NULL OR days_to_activation IS NOT NULL))
        """
    ).fetchone()[0]
    if activation_rows != source_accounts or distinct_accounts != source_accounts:
        raise AssertionError("Activation must contain exactly one row per account")
    if inconsistent_nulls:
        raise AssertionError("Activation flags and activation dates are inconsistent")
    if invalid_activation_rows:
        raise AssertionError("Activation dates or durations are invalid")
    if not 0 <= activation_rate <= 1:
        raise AssertionError("Activation rate must be between 0 and 1")
    if not 0 <= conversion_rate <= 1:
        raise AssertionError("Trial conversion rate must be between 0 and 1")
    if any(not 0 <= row[3] <= 1 for row in feature_rows):
        raise AssertionError("Feature adoption rates must be between 0 and 1")
    expected_features = {
        "invite_sent",
        "integration_connected",
        "report_created",
        "report_exported",
        "dashboard_viewed",
    }
    if {row[0] for row in feature_rows} != expected_features:
        raise AssertionError("Feature adoption is missing a required feature")


def format_days(value: float | None) -> str:
    if value is None:
        return "N/A"
    if float(value).is_integer():
        return f"{int(value)} days"
    return f"{value:.1f} days"


def main() -> None:
    check_input_files()

    # setup.sql uses simple relative paths, so execute it from the project root.
    original_directory = Path.cwd()
    os.chdir(PROJECT_ROOT)
    try:
        connection = duckdb.connect(database=":memory:")
        run_sql_file(connection, "setup.sql")
        run_sql_file(connection, "activation.sql")
        run_sql_file(connection, "usage_metrics.sql")

        total, activated, activation_rate, median_days = connection.execute(
            "SELECT * FROM activation_metrics"
        ).fetchone()
        _, converted, conversion_rate = connection.execute(
            "SELECT * FROM trial_conversion_metrics"
        ).fetchone()
        feature_rows = connection.execute("SELECT * FROM feature_adoption").fetchall()
        weekly_rows = connection.execute("SELECT * FROM weekly_active_accounts").fetchall()
        monthly_rows = connection.execute("SELECT * FROM monthly_active_accounts").fetchall()

        validate_metrics(
            connection,
            float(activation_rate),
            float(conversion_rate),
            feature_rows,
        )

        print("\nSaaS Metrics\n")
        print(f"Total Accounts: {total:,}")
        print(f"Activated Accounts: {activated:,}")
        print(f"Activation Rate: {activation_rate:.1%}")
        print(f"\nMedian Time to Activation: {format_days(median_days)}")
        print(f"\nConverted Trial Accounts: {converted:,}")
        print(f"Trial Conversion Rate: {conversion_rate:.1%}")

        print("\nFeature Adoption:")
        for feature_name, accounts_using, _, adoption_rate in feature_rows:
            print(f"{feature_name}: {adoption_rate:.1%} ({accounts_using:,} accounts)")

        print("\nWeekly Active Accounts:")
        for week_start, active_accounts in weekly_rows:
            print(f"{week_start}: {active_accounts:,}")

        print("\nMonthly Active Accounts:")
        for month_start, active_accounts in monthly_rows:
            print(f"{month_start}: {active_accounts:,}")

        print("\nValidation Checks: PASSED")
    finally:
        if "connection" in locals():
            connection.close()
        os.chdir(original_directory)


if __name__ == "__main__":
    main()
