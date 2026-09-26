"""Shared, project-relative streaming configuration."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
BATCH_EVENTS_PATH = DATA_DIR / "events.parquet"
ACCOUNTS_PATH = DATA_DIR / "accounts.parquet"
USERS_PATH = DATA_DIR / "users.parquet"
SUBSCRIPTIONS_PATH = DATA_DIR / "subscriptions.parquet"

STREAMING_DATA_DIR = DATA_DIR / "streaming"
STREAMING_EVENTS_DIR = STREAMING_DATA_DIR / "product_events"
REJECTED_EVENTS_DIR = STREAMING_DATA_DIR / "rejected"
EMPTY_STREAM_PATH = STREAMING_EVENTS_DIR / "_empty.parquet"

DEFAULT_BOOTSTRAP_SERVERS = "localhost:9092"
PRODUCT_EVENTS_TOPIC = "product-events"
CONSUMER_GROUP = "saas-analytics-raw-writer-v1"
DEFAULT_BATCH_SIZE = 25
DEFAULT_FLUSH_SECONDS = 10.0

EVENT_NAMES = (
    "workspace_created",
    "invite_sent",
    "integration_connected",
    "report_created",
    "report_exported",
    "dashboard_viewed",
    "user_login",
)
SUPPORTED_EVENT_VERSIONS = (1, 2)

STREAM_COLUMNS = [
    "event_id",
    "account_id",
    "user_id",
    "event_name",
    "event_timestamp",
    "event_version",
    "properties",
    "source",
    "device_type",
    "kafka_partition",
    "kafka_offset",
    "received_at",
]
