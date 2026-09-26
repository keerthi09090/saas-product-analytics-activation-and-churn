"""Level 8 contract, realism, deduplication, and Parquet tests."""

import json
import random
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import duckdb
import pandas as pd
import pytest
import streaming.consumer as consumer_module

from streaming.config import ACCOUNTS_PATH, USERS_PATH
from streaming.consumer import (
    deduplicate_rows,
    event_to_row,
    parse_and_validate_event,
    write_event_batch,
    write_rejected_event,
)
from streaming.producer import generate_event, production_delay, serialize_event
from streaming.schemas import ProductEvent
from streaming.status import summarize_streamed_events


@pytest.fixture(scope="module")
def references():
    accounts = pd.read_parquet(ACCOUNTS_PATH)
    users = pd.read_parquet(USERS_PATH)
    valid_accounts = set(accounts.account_id)
    user_accounts = dict(zip(users.user_id, users.account_id))
    return accounts, users, valid_accounts, user_accounts


def event_payload(references, version=1):
    _, users, _, _ = references
    user = users.iloc[0]
    payload = {
        "event_id": f"TEST-V{version}",
        "account_id": user.account_id,
        "user_id": user.user_id,
        "event_name": "user_login",
        "event_timestamp": "2026-09-25T19:00:00Z",
        "event_version": version,
        "properties": {},
    }
    if version == 2:
        payload.update({"source": "web", "device_type": "desktop"})
    return payload


def test_producer_creates_relationship_valid_events(references):
    accounts, users, valid_accounts, user_accounts = references
    reports = set()
    event = generate_event(
        accounts,
        users,
        reports,
        random.Random(42),
        now=datetime(2026, 9, 25, 19, 0, tzinfo=timezone.utc),
    )
    assert set(
        [
            "event_id",
            "account_id",
            "user_id",
            "event_name",
            "event_timestamp",
            "event_version",
        ]
    ) <= set(event.model_dump())
    assert event.account_id in valid_accounts
    assert user_accounts[event.user_id] == event.account_id
    assert event.event_timestamp.tzinfo is not None
    assert event.event_version in {1, 2}


def test_event_versions_one_and_two_are_supported(references):
    _, _, valid_accounts, user_accounts = references
    for version in [1, 2]:
        raw = json.dumps(event_payload(references, version)).encode()
        event = parse_and_validate_event(raw, valid_accounts, user_accounts)
        assert event.event_version == version
    assert ProductEvent.model_validate(event_payload(references, 1)).source is None
    assert ProductEvent.model_validate(event_payload(references, 2)).source == "web"
    assert b'"source"' not in serialize_event(
        ProductEvent.model_validate(event_payload(references, 1))
    )


def test_weekend_production_is_slower():
    assert production_delay(0.5, weekday=5) == 1.5
    assert production_delay(0.5, weekday=1) == 0.5


def test_invalid_events_are_rejected(references):
    _, _, valid_accounts, user_accounts = references
    invalid_payloads = []
    missing_id = event_payload(references)
    missing_id.pop("event_id")
    invalid_payloads.append(missing_id)
    invalid_name = event_payload(references)
    invalid_name["event_name"] = "unknown_action"
    invalid_payloads.append(invalid_name)
    invalid_version = event_payload(references)
    invalid_version["event_version"] = 99
    invalid_payloads.append(invalid_version)
    invalid_timestamp = event_payload(references)
    invalid_timestamp["event_timestamp"] = "not-a-time"
    invalid_payloads.append(invalid_timestamp)

    for payload in invalid_payloads:
        with pytest.raises(ValueError):
            parse_and_validate_event(
                json.dumps(payload).encode(), valid_accounts, user_accounts
            )


def test_invalid_event_is_saved_without_crashing(tmp_path):
    path = write_rejected_event(
        b'{"account_id":"A001"}',
        "missing event_id",
        output_dir=tmp_path,
    )
    saved = json.loads(path.read_text().strip())
    assert saved["reason"] == "missing event_id"
    assert saved["raw_message"] == '{"account_id":"A001"}'


def test_consumer_rejects_missing_event_id_without_writing_valid_parquet(
    tmp_path, references, monkeypatch
):
    """One invalid Kafka message is logged while the consumer exits cleanly."""

    _, _, valid_accounts, user_accounts = references
    invalid = event_payload(references)
    invalid.pop("event_id")
    raw_message = json.dumps(invalid).encode()
    valid_output = tmp_path / "product_events"
    rejected_output = tmp_path / "rejected"
    consumer_instances = []

    class FakeKafkaConsumer:
        def __init__(self, *_args, **_kwargs):
            self.closed = False
            self.polled = False
            consumer_instances.append(self)

        def poll(self, **_kwargs):
            if self.polled:
                return {}
            self.polled = True
            message = SimpleNamespace(value=raw_message, offset=1, partition=0)
            return {"product-events": [message]}

        def commit(self):
            pass

        def close(self):
            self.closed = True

    original_rejection_writer = write_rejected_event
    monkeypatch.setattr("kafka.KafkaConsumer", FakeKafkaConsumer)
    monkeypatch.setattr(consumer_module, "ensure_streaming_storage", lambda: None)
    monkeypatch.setattr(
        consumer_module,
        "load_reference_keys",
        lambda: (valid_accounts, user_accounts),
    )
    monkeypatch.setattr(consumer_module, "load_seen_event_ids", lambda: set())
    monkeypatch.setattr(consumer_module, "update_stream_metrics", lambda **_kwargs: {})
    monkeypatch.setattr(
        consumer_module,
        "write_rejected_event",
        lambda raw, reason: original_rejection_writer(
            raw, reason, output_dir=rejected_output
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["streaming.consumer", "--max-messages", "1"],
    )

    # main() returning normally proves the rejected message did not crash the
    # consumer. Its max-message option makes this a finite test.
    consumer_module.main()

    assert consumer_instances[0].closed is True
    assert list(valid_output.glob("*.parquet")) == []
    rejection_files = list(rejected_output.glob("*.jsonl"))
    assert len(rejection_files) == 1
    rejection = json.loads(rejection_files[0].read_text().strip())
    assert "event_id" in rejection["reason"]
    assert rejection["raw_message"] == raw_message.decode()


def test_unknown_account_and_mismatched_user_are_rejected(references):
    _, users, valid_accounts, user_accounts = references
    unknown = event_payload(references)
    unknown["account_id"] = "DOES_NOT_EXIST"
    with pytest.raises(ValueError, match="unknown account_id"):
        parse_and_validate_event(
            json.dumps(unknown).encode(), valid_accounts, user_accounts
        )

    mismatch = event_payload(references)
    different_user = users.loc[users.account_id != mismatch["account_id"]].iloc[0]
    mismatch["user_id"] = different_user.user_id
    with pytest.raises(ValueError, match="does not belong"):
        parse_and_validate_event(
            json.dumps(mismatch).encode(), valid_accounts, user_accounts
        )


def test_duplicate_event_ids_are_one_logical_event(references):
    event = ProductEvent.model_validate(event_payload(references))
    row = event_to_row(event)
    seen = set()
    unique = deduplicate_rows([row, row.copy()], seen)
    assert len(unique) == 1
    assert seen == {event.event_id}


def test_consumer_parquet_is_readable_by_duckdb(tmp_path, references):
    first = ProductEvent.model_validate(event_payload(references, 1))
    second_payload = event_payload(references, 2)
    second_payload["event_id"] = "TEST-V2-SECOND"
    second = ProductEvent.model_validate(second_payload)
    path = write_event_batch(
        [event_to_row(first), event_to_row(second)], output_dir=tmp_path
    )

    assert path is not None and path.exists()
    result = duckdb.sql(
        "select count(*), count(distinct event_id), min(event_version), "
        f"max(event_version) from read_parquet('{path}')"
    ).fetchone()
    assert result == (2, 2, 1, 2)

    summary = summarize_streamed_events(tmp_path)
    assert summary["file_count"] == 1
    assert summary["total_rows"] == 2
    assert summary["latest_event"] is not None
