"""Create the zero-row streaming event fixture required by dbt in CI."""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "streaming" / "product_events" / "_empty.parquet"

STREAM_EVENT_SCHEMA = pa.schema(
    [
        pa.field("event_id", pa.string()),
        pa.field("account_id", pa.string()),
        pa.field("user_id", pa.string()),
        pa.field("event_name", pa.string()),
        pa.field("event_timestamp", pa.timestamp("us", tz="UTC")),
        pa.field("event_version", pa.int64()),
        pa.field("properties", pa.string()),
        pa.field("source", pa.string()),
        pa.field("device_type", pa.string()),
        pa.field("kafka_partition", pa.int64()),
        pa.field("kafka_offset", pa.int64()),
        pa.field("received_at", pa.timestamp("us", tz="UTC")),
    ]
)


def create_empty_stream_fixture(output_path: Path = OUTPUT_PATH) -> Path:
    """Write an empty, schema-correct Parquet file and return its path."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    empty_table = pa.Table.from_pylist([], schema=STREAM_EVENT_SCHEMA)
    pq.write_table(empty_table, output_path)
    return output_path


if __name__ == "__main__":
    path = create_empty_stream_fixture()
    print(f"Created zero-row streaming fixture: {path}")
