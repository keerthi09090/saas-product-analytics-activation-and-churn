-- Event-grain fact table: exactly one row per product event.

select
    event_id,
    account_id,
    user_id,
    event_name,
    event_timestamp,
    event_version
from {{ ref('stg_events') }}
