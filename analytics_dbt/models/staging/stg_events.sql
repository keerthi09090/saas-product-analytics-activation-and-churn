-- One typed row per immutable product event from either ingestion path.
-- Kafka is at-least-once, so event_id is the logical deduplication key.

with combined_events as (
    select
        cast(event_id as varchar) as event_id,
        cast(account_id as varchar) as account_id,
        cast(user_id as varchar) as user_id,
        cast(event_name as varchar) as event_name,
        cast(event_timestamp as timestamptz) as event_timestamp,
        cast(event_version as integer) as event_version,
        1 as source_priority
    from read_parquet('{{ var("raw_data_path") }}/events.parquet')

    union all

    select
        cast(event_id as varchar) as event_id,
        cast(account_id as varchar) as account_id,
        cast(user_id as varchar) as user_id,
        cast(event_name as varchar) as event_name,
        cast(event_timestamp as timestamptz) as event_timestamp,
        cast(event_version as integer) as event_version,
        2 as source_priority
    from read_parquet(
        '{{ var("raw_data_path") }}/streaming/product_events/*.parquet',
        union_by_name = true
    )
),

deduplicated as (
    select *, row_number() over (
        partition by event_id
        order by source_priority, event_timestamp
    ) as event_id_occurrence
    from combined_events
)

select
    event_id,
    account_id,
    user_id,
    event_name,
    event_timestamp,
    event_version
from deduplicated
where event_id_occurrence = 1
