"""Print a concise summary of locally persisted Kafka product events."""

from pathlib import Path

import duckdb

from streaming.config import EMPTY_STREAM_PATH, STREAMING_EVENTS_DIR


def summarize_streamed_events(directory: Path = STREAMING_EVENTS_DIR) -> dict:
    files = sorted(
        path for path in directory.glob("*.parquet") if path != EMPTY_STREAM_PATH
    )
    if not files:
        return {"file_count": 0, "total_rows": 0, "latest_event": None}

    file_list = ", ".join(
        "'" + str(path).replace("'", "''") + "'" for path in files
    )
    connection = duckdb.connect()
    try:
        total_rows, latest_event = connection.execute(
            "select count(*), max(event_timestamp) "
            f"from read_parquet([{file_list}], union_by_name=true)"
        ).fetchone()
    finally:
        connection.close()
    return {
        "file_count": len(files),
        "total_rows": int(total_rows),
        "latest_event": latest_event,
    }


def main() -> None:
    summary = summarize_streamed_events()
    print("Streaming Parquet Status")
    print(f"Files: {summary['file_count']}")
    print(f"Rows: {summary['total_rows']}")
    print(f"Latest event: {summary['latest_event'] or 'No events yet'}")


if __name__ == "__main__":
    main()
