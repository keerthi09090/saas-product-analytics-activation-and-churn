"""Shared command-line helpers for the three snapshot entry points."""

import argparse
import logging
from pathlib import Path
from typing import Optional, Sequence

from pipelines.snapshots import DEFAULT_SNAPSHOT_ROOT, write_snapshot


def run_snapshot_cli(dataset: str, argv: Optional[Sequence[str]] = None) -> Path:
    parser = argparse.ArgumentParser(description=f"Create the {dataset} snapshot")
    parser.add_argument("--snapshot-date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--snapshot-root",
        type=Path,
        default=DEFAULT_SNAPSHOT_ROOT,
        help="Optional output root used by tests or local demos.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        return write_snapshot(dataset, args.snapshot_date, args.snapshot_root)
    except ValueError as exc:
        parser.error(str(exc))
        raise
