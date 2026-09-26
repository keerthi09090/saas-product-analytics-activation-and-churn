"""Validate Kafka product events and write append-friendly Parquet batches."""

from __future__ import annotations

import argparse
import json
import logging
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set
from uuid import uuid4

import pandas as pd
from pydantic import ValidationError

from streaming.config import (
    ACCOUNTS_PATH,
    CONSUMER_GROUP,
    DEFAULT_BATCH_SIZE,
    DEFAULT_BOOTSTRAP_SERVERS,
    DEFAULT_FLUSH_SECONDS,
    EMPTY_STREAM_PATH,
    PRODUCT_EVENTS_TOPIC,
    REJECTED_EVENTS_DIR,
    STREAM_COLUMNS,
    STREAMING_EVENTS_DIR,
    USERS_PATH,
)
from streaming.metrics import update_stream_metrics
from streaming.schemas import ProductEvent


LOGGER = logging.getLogger("streaming.consumer")


def ensure_streaming_storage() -> None:
    """Create directories and a zero-row Parquet file for a stable dbt glob."""

    STREAMING_EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    REJECTED_EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    if not any(STREAMING_EVENTS_DIR.glob("*.parquet")):
        empty = pd.DataFrame(
            {
                "event_id": pd.Series(dtype="string"),
                "account_id": pd.Series(dtype="string"),
                "user_id": pd.Series(dtype="string"),
                "event_name": pd.Series(dtype="string"),
                "event_timestamp": pd.Series(dtype="datetime64[ns, UTC]"),
                "event_version": pd.Series(dtype="int64"),
                "properties": pd.Series(dtype="string"),
                "source": pd.Series(dtype="string"),
                "device_type": pd.Series(dtype="string"),
                "kafka_partition": pd.Series(dtype="int64"),
                "kafka_offset": pd.Series(dtype="int64"),
                "received_at": pd.Series(dtype="datetime64[ns, UTC]"),
            }
        )
        empty.to_parquet(EMPTY_STREAM_PATH, index=False)


def load_reference_keys() -> tuple[Set[str], Dict[str, str]]:
    accounts = pd.read_parquet(ACCOUNTS_PATH, columns=["account_id"])
    users = pd.read_parquet(USERS_PATH, columns=["user_id", "account_id"])
    return set(accounts.account_id), dict(zip(users.user_id, users.account_id))


def load_seen_event_ids(output_dir: Path = STREAMING_EVENTS_DIR) -> Set[str]:
    ensure_streaming_storage()
    seen: Set[str] = set()
    for path in output_dir.glob("*.parquet"):
        frame = pd.read_parquet(path, columns=["event_id"])
        seen.update(frame.event_id.dropna().astype(str))
    return seen


def parse_and_validate_event(
    raw_value: bytes,
    valid_accounts: Set[str],
    user_accounts: Dict[str, str],
) -> ProductEvent:
    try:
        payload = json.loads(raw_value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("message is not valid UTF-8 JSON") from exc
    try:
        event = ProductEvent.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    if event.account_id not in valid_accounts:
        raise ValueError(f"unknown account_id: {event.account_id}")
    if event.user_id not in user_accounts:
        raise ValueError(f"unknown user_id: {event.user_id}")
    if user_accounts[event.user_id] != event.account_id:
        raise ValueError("user_id does not belong to account_id")
    return event


def event_to_row(
    event: ProductEvent,
    kafka_partition: Optional[int] = None,
    kafka_offset: Optional[int] = None,
    received_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    return {
        "event_id": event.event_id,
        "account_id": event.account_id,
        "user_id": event.user_id,
        "event_name": event.event_name,
        "event_timestamp": event.event_timestamp,
        "event_version": event.event_version,
        "properties": json.dumps(event.properties, sort_keys=True),
        "source": event.source,
        "device_type": event.device_type,
        "kafka_partition": kafka_partition,
        "kafka_offset": kafka_offset,
        "received_at": received_at or datetime.now(timezone.utc),
    }


def deduplicate_rows(
    rows: Iterable[Dict[str, Any]], seen_event_ids: Set[str]
) -> list[Dict[str, Any]]:
    unique = []
    for row in rows:
        event_id = str(row["event_id"])
        if event_id in seen_event_ids:
            continue
        seen_event_ids.add(event_id)
        unique.append(row)
    return unique


def write_event_batch(
    rows: list[Dict[str, Any]], output_dir: Path = STREAMING_EVENTS_DIR
) -> Optional[Path]:
    if not rows:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    final_path = output_dir / f"events_{timestamp}_{uuid4().hex[:8]}.parquet"
    temporary_path = final_path.with_suffix(".parquet.tmp")
    frame = pd.DataFrame(rows, columns=STREAM_COLUMNS)
    frame["event_timestamp"] = pd.to_datetime(frame.event_timestamp, utc=True)
    frame["received_at"] = pd.to_datetime(frame.received_at, utc=True)
    frame.to_parquet(temporary_path, index=False)
    temporary_path.replace(final_path)
    return final_path


def write_rejected_event(
    raw_value: bytes,
    reason: str,
    output_dir: Path = REJECTED_EVENTS_DIR,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = output_dir / f"rejected_{timestamp}.jsonl"
    record = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "raw_message": raw_value.decode("utf-8", errors="replace"),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Persist Kafka events to Parquet")
    parser.add_argument("--bootstrap-servers", default=DEFAULT_BOOTSTRAP_SERVERS)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--flush-seconds", type=float, default=DEFAULT_FLUSH_SECONDS)
    parser.add_argument(
        "--max-messages",
        type=int,
        default=0,
        help="Stop after this many Kafka messages; 0 keeps consuming until Ctrl+C.",
    )
    args = parser.parse_args()
    if args.batch_size < 1 or args.flush_seconds <= 0 or args.max_messages < 0:
        parser.error("batch-size and flush-seconds must be positive")

    from kafka import KafkaConsumer

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("kafka").setLevel(logging.WARNING)
    ensure_streaming_storage()
    valid_accounts, user_accounts = load_reference_keys()
    seen_ids = load_seen_event_ids()
    consumer = KafkaConsumer(
        PRODUCT_EVENTS_TOPIC,
        bootstrap_servers=args.bootstrap_servers,
        group_id=CONSUMER_GROUP,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda value: value,
    )
    print(
        f"Connected to Kafka topic: {PRODUCT_EVENTS_TOPIC} "
        f"({args.bootstrap_servers})",
        flush=True,
    )
    print(
        f"Buffering up to {args.batch_size} events or "
        f"{args.flush_seconds:g} seconds per Parquet file.",
        flush=True,
    )
    running = True

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    buffer: list[Dict[str, Any]] = []
    received = duplicates = rejected = persisted = 0
    last_flush = time.monotonic()

    def flush() -> None:
        nonlocal buffer, persisted, last_flush
        path = write_event_batch(buffer)
        if path is not None:
            print(f"Buffered {len(buffer)} events", flush=True)
            persisted += len(buffer)
            update_stream_metrics(persisted=len(buffer))
            print(f"Wrote:\n{path}", flush=True)
            buffer = []
        consumer.commit()
        last_flush = time.monotonic()

    try:
        while running:
            records = consumer.poll(timeout_ms=500, max_records=args.batch_size)
            for messages in records.values():
                for message in messages:
                    received += 1
                    update_stream_metrics(received=1)
                    reached_limit = bool(
                        args.max_messages and received >= args.max_messages
                    )
                    try:
                        event = parse_and_validate_event(
                            message.value, valid_accounts, user_accounts
                        )
                    except ValueError as exc:
                        rejected += 1
                        update_stream_metrics(rejected=1)
                        rejected_path = write_rejected_event(message.value, str(exc))
                        print(
                            f"Rejected offset {message.offset}: {exc}\n"
                            f"Saved rejection: {rejected_path}",
                            flush=True,
                        )
                        LOGGER.warning("Rejected event at offset %s: %s", message.offset, exc)
                        if reached_limit:
                            running = False
                            break
                        continue
                    print(
                        f"Received: {event.account_id} | {event.event_name} | "
                        f"v{event.event_version}",
                        flush=True,
                    )
                    if event.event_id in seen_ids:
                        duplicates += 1
                        update_stream_metrics(
                            duplicates=1,
                            latest_event_timestamp=event.event_timestamp,
                        )
                        print(
                            f"Skipped duplicate event_id: {event.event_id}",
                            flush=True,
                        )
                        if reached_limit:
                            running = False
                            break
                        continue
                    seen_ids.add(event.event_id)
                    update_stream_metrics(
                        latest_event_timestamp=event.event_timestamp
                    )
                    buffer.append(
                        event_to_row(
                            event,
                            kafka_partition=message.partition,
                            kafka_offset=message.offset,
                        )
                    )
                    if reached_limit:
                        running = False
                        break
                if not running:
                    break
            if buffer and (
                len(buffer) >= args.batch_size
                or time.monotonic() - last_flush >= args.flush_seconds
                or not running
            ):
                flush()
            elif not buffer and time.monotonic() - last_flush >= args.flush_seconds:
                consumer.commit()
                last_flush = time.monotonic()
    finally:
        if buffer:
            flush()
        consumer.close()
    print(
        f"Consumer stopped. Received={received}, persisted={persisted}, "
        f"duplicates={duplicates}, rejected={rejected}"
    )


if __name__ == "__main__":
    main()
