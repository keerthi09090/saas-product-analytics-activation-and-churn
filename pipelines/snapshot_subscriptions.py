"""Create one logical-date subscription snapshot."""

from pipelines.cli import run_snapshot_cli


if __name__ == "__main__":
    run_snapshot_cli("subscriptions")
