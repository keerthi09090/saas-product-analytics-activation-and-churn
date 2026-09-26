-- Reporting-ready account activity and feature-use counts.

select
    account_id,
    total_events,
    number_of_active_users as active_users,
    first_event_at,
    last_event_at,
    report_created_count,
    report_exported_count,
    dashboard_viewed_count,
    invite_sent_count,
    integration_connected_count,
    seats_purchased,
    provisioned_users,
    seat_utilization,
    activity_as_of_date,
    days_since_last_activity,
    events_last_7d,
    events_last_30d,
    active_users_last_30d
from {{ ref('int_account_activity') }}
