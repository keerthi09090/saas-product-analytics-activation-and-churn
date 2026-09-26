"""Publish realistic, finite-by-default synthetic SaaS events to Kafka."""

from __future__ import annotations

import argparse
import json
import random
import time
from datetime import datetime, timezone
from typing import Dict, Set
from uuid import uuid4

import pandas as pd

from streaming.config import (
    ACCOUNTS_PATH,
    BATCH_EVENTS_PATH,
    DEFAULT_BOOTSTRAP_SERVERS,
    PRODUCT_EVENTS_TOPIC,
    SUBSCRIPTIONS_PATH,
    USERS_PATH,
)
from streaming.schemas import ProductEvent


ENGAGEMENT_WEIGHTS = {"low": 1.0, "medium": 3.0, "high": 6.0}
EVENT_WEIGHTS = {
    "low": {
        "user_login": 55,
        "dashboard_viewed": 24,
        "report_created": 8,
        "report_exported": 3,
        "invite_sent": 6,
        "integration_connected": 4,
    },
    "medium": {
        "user_login": 42,
        "dashboard_viewed": 27,
        "report_created": 14,
        "report_exported": 7,
        "invite_sent": 6,
        "integration_connected": 4,
    },
    "high": {
        "user_login": 34,
        "dashboard_viewed": 28,
        "report_created": 18,
        "report_exported": 10,
        "invite_sent": 5,
        "integration_connected": 5,
    },
}


def load_reference_data() -> tuple[pd.DataFrame, pd.DataFrame, Set[str]]:
    accounts = pd.read_parquet(ACCOUNTS_PATH)
    subscriptions = pd.read_parquet(SUBSCRIPTIONS_PATH)
    eligible_ids = set(
        subscriptions.loc[
            subscriptions.subscription_status != "cancelled", "account_id"
        ]
    )
    accounts = accounts.loc[accounts.account_id.isin(eligible_ids)].reset_index(
        drop=True
    )
    users = pd.read_parquet(USERS_PATH)
    users = users.loc[users.account_id.isin(eligible_ids)].reset_index(drop=True)
    batch_events = pd.read_parquet(BATCH_EVENTS_PATH)
    accounts_with_reports = set(
        batch_events.loc[
            batch_events.event_name == "report_created", "account_id"
        ]
    )
    return accounts, users, accounts_with_reports


def generate_event(
    accounts: pd.DataFrame,
    users: pd.DataFrame,
    accounts_with_reports: Set[str],
    rng: random.Random,
    now: datetime | None = None,
) -> ProductEvent:
    """Create one relationship-valid event using Level 1 engagement state."""

    account_rows = accounts.to_dict("records")
    account = rng.choices(
        account_rows,
        weights=[ENGAGEMENT_WEIGHTS[row["engagement_level"]] for row in account_rows],
        k=1,
    )[0]
    account_users = users.loc[users.account_id == account["account_id"]]
    user = account_users.iloc[rng.randrange(len(account_users))]
    weights = EVENT_WEIGHTS[account["engagement_level"]]
    event_name = rng.choices(list(weights), weights=list(weights.values()), k=1)[0]

    # Preserve the report-created-before-export relationship across the stream.
    if event_name == "report_exported" and account["account_id"] not in accounts_with_reports:
        event_name = "report_created"
    if event_name == "report_created":
        accounts_with_reports.add(account["account_id"])

    version = 2 if rng.random() < 0.25 else 1
    payload = {
        "event_id": f"SEVT-{uuid4().hex}",
        "account_id": account["account_id"],
        "user_id": user.user_id,
        "event_name": event_name,
        "event_timestamp": now or datetime.now(timezone.utc),
        "event_version": version,
        "properties": {},
    }
    if version == 2:
        payload["source"] = rng.choices(
            ["web", "mobile", "api"], weights=[70, 20, 10], k=1
        )[0]
        device_choices: Dict[str, list[str]] = {
            "web": ["desktop", "tablet"],
            "mobile": ["mobile", "tablet"],
            "api": ["service"],
        }
        payload["device_type"] = rng.choice(device_choices[payload["source"]])
    return ProductEvent.model_validate(payload)


def serialize_event(event: ProductEvent) -> bytes:
    return event.model_dump_json(exclude_none=True).encode("utf-8")


def production_delay(base_interval: float, weekday: int) -> float:
    """Reduce weekend event volume by slowing the producer to one-third speed."""

    return base_interval * (3 if weekday >= 5 else 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish synthetic SaaS events")
    parser.add_argument("--events", type=int, default=100)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bootstrap-servers", default=DEFAULT_BOOTSTRAP_SERVERS)
    parser.add_argument(
        "--duplicate-every",
        type=int,
        default=0,
        help="Resend every Nth event to demonstrate event_id deduplication.",
    )
    parser.add_argument(
        "--send-invalid",
        action="store_true",
        help="Send one final event without event_id to demonstrate rejection.",
    )
    args = parser.parse_args()
    if args.events < 1 or args.interval < 0 or args.duplicate_every < 0:
        parser.error("events must be positive; interval and duplicate-every cannot be negative")

    from kafka import KafkaProducer

    accounts, users, accounts_with_reports = load_reference_data()
    rng = random.Random(args.seed)
    producer = KafkaProducer(
        bootstrap_servers=args.bootstrap_servers,
        acks="all",
        retries=5,
        value_serializer=lambda value: value,
    )
    sent = 0
    duplicates = 0
    try:
        for index in range(1, args.events + 1):
            event = generate_event(accounts, users, accounts_with_reports, rng)
            message = serialize_event(event)
            producer.send(
                PRODUCT_EVENTS_TOPIC,
                key=event.account_id.encode("utf-8"),
                value=message,
            ).get(timeout=10)
            sent += 1
            if args.duplicate_every and index % args.duplicate_every == 0:
                producer.send(
                    PRODUCT_EVENTS_TOPIC,
                    key=event.account_id.encode("utf-8"),
                    value=message,
                ).get(timeout=10)
                duplicates += 1
            print(
                f"Sent {index:>3}/{args.events}: {event.account_id} "
                f"{event.event_name} v{event.event_version}"
            )
            # Weekend production is deliberately slower, yielding weekday-heavy volume.
            delay = production_delay(args.interval, datetime.now().weekday())
            if delay:
                time.sleep(delay)
        if args.send_invalid:
            valid_event = generate_event(accounts, users, accounts_with_reports, rng)
            invalid_payload = valid_event.model_dump(mode="json", exclude_none=True)
            invalid_payload.pop("event_id")
            producer.send(
                PRODUCT_EVENTS_TOPIC,
                key=valid_event.account_id.encode("utf-8"),
                value=json.dumps(invalid_payload).encode("utf-8"),
            ).get(timeout=10)
            print("Sent invalid demonstration event: missing event_id")
    except KeyboardInterrupt:
        print("\nProducer stopped by user.")
    finally:
        producer.flush(timeout=10)
        producer.close()
    print(f"Published {sent} unique sends and {duplicates} deliberate duplicates.")


if __name__ == "__main__":
    main()
