"""Small local latency check for a running Level 7 API.

This is deliberately a development-machine test, not a production benchmark.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def percentile(values: list[float], percent: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * percent)))
    return ordered[index]


def request_once(url: str, timeout: float) -> tuple[float, bool]:
    started = time.perf_counter()
    try:
        with urlopen(url, timeout=timeout) as response:
            response.read()
            success = response.status == 200
    except (HTTPError, URLError, TimeoutError):
        success = False
    return (time.perf_counter() - started) * 1_000, success


def run_load_test(
    url: str, request_count: int, warmup_count: int, timeout: float
) -> dict[str, float | int | str]:
    for _ in range(warmup_count):
        request_once(url, timeout)

    latencies = []
    errors = 0
    for _ in range(request_count):
        latency, success = request_once(url, timeout)
        latencies.append(latency)
        errors += int(not success)

    return {
        "url": url,
        "request_count": request_count,
        "errors": errors,
        "average_ms": statistics.fmean(latencies),
        "p50_ms": percentile(latencies, 0.50),
        "p95_ms": percentile(latencies, 0.95),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Local churn API latency test")
    parser.add_argument(
        "--url", default="http://127.0.0.1:8000/v1/churn/A040"
    )
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()
    if args.requests < 1 or args.warmup < 0:
        parser.error("--requests must be positive and --warmup cannot be negative")

    result = run_load_test(args.url, args.requests, args.warmup, args.timeout)
    print(json.dumps(result, indent=2))
    print("Latency target: local p95 < 200 ms")
    if result["errors"] or result["p95_ms"] >= 200:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
