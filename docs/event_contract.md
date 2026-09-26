# Product Event Contract

Level 8 publishes JSON messages to the Kafka topic `product-events`. Every
message represents one immutable product action. `event_id` is the logical
unique key because Kafka delivery may be at least once.

## Required fields

| Field | Type | Rules |
|---|---|---|
| `event_id` | string | Required, non-empty, unique logical identifier |
| `account_id` | string | Must reference an existing account |
| `user_id` | string | Must reference a user belonging to the account |
| `event_name` | string | One of the accepted product actions below |
| `event_timestamp` | ISO-8601 timestamp | Must contain an explicit timezone |
| `event_version` | integer | Supported values are 1 and 2 |
| `properties` | JSON object | Optional event-specific context; defaults to `{}` |

Accepted actions are `workspace_created`, `invite_sent`,
`integration_connected`, `report_created`, `report_exported`,
`dashboard_viewed`, and `user_login`.

## Version 1

```json
{
  "event_id": "SEVT-785e9b70",
  "account_id": "A040",
  "user_id": "U000123",
  "event_name": "report_created",
  "event_timestamp": "2026-09-25T19:15:30Z",
  "event_version": 1,
  "properties": {}
}
```

## Version 2

Version 2 retains every V1 field and adds required producer context. Existing
V1 events remain valid.

```json
{
  "event_id": "SEVT-79d67f93",
  "account_id": "A040",
  "user_id": "U000123",
  "event_name": "dashboard_viewed",
  "event_timestamp": "2026-09-25T19:16:02Z",
  "event_version": 2,
  "properties": {},
  "source": "web",
  "device_type": "desktop"
}
```

`source` accepts `web`, `mobile`, or `api`. `device_type` accepts `desktop`,
`mobile`, `tablet`, or `service`.

## Validation and delivery behavior

- The consumer rejects malformed JSON, missing fields, unsupported names or
  versions, timezone-free timestamps, unknown accounts/users, and account/user
  mismatches.
- Rejected records are written to `data/streaming/rejected/*.jsonl` with the
  validation reason. One bad message does not stop the consumer.
- The consumer keeps a set of previously persisted `event_id` values and drops
  repeat deliveries before writing a Parquet batch.
- dbt applies a second `event_id` deduplication guard when combining the batch
  and streaming inputs.
- A report export is generated only for an account with a prior report creation
  in the batch history or current producer session.
