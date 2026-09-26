"""Create one logical-date invoice snapshot."""

from pipelines.cli import run_snapshot_cli


if __name__ == "__main__":
    run_snapshot_cli("invoices")
