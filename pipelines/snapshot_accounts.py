"""Create one logical-date account snapshot."""

from pipelines.cli import run_snapshot_cli


if __name__ == "__main__":
    run_snapshot_cli("accounts")
