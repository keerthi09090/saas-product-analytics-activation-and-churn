-- Seat use and recency metrics must stay within logical bounds.

select account_id
from {{ ref('mart_account_activity') }}
where seat_utilization < 0
    or seat_utilization > 1
    or days_since_last_activity < 0
    or events_last_7d < 0
    or events_last_30d < 0
    or active_users_last_30d < 0
    or events_last_7d > events_last_30d
