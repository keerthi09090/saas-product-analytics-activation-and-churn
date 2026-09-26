-- Behavioral comparison of currently active and cancelled paid accounts.
-- Trial/non-converted accounts are excluded from both populations.

with paid_account_behavior as (
    select
        case
            when accounts.subscription_status = 'active' then 'retained'
            when accounts.subscription_status = 'cancelled' then 'churned'
        end as retention_status,
        activity.* exclude (account_id)
    from {{ ref('dim_account') }} as accounts
    inner join {{ ref('mart_account_activity') }} as activity
        on accounts.account_id = activity.account_id
    where accounts.subscription_start_date is not null
        and accounts.subscription_status in ('active', 'cancelled')
)

select
    retention_status,
    count(*) as total_accounts,
    avg(total_events) as avg_total_events,
    avg(active_users) as avg_active_users,
    avg(seat_utilization) as avg_seat_utilization,
    avg(report_created_count) as avg_reports_created,
    avg(report_exported_count) as avg_reports_exported,
    avg(integration_connected_count) as avg_integrations_connected,
    avg(dashboard_viewed_count) as avg_dashboards_viewed,
    avg(days_since_last_activity) as avg_days_since_last_activity,
    avg(events_last_7d) as avg_events_last_7d,
    avg(events_last_30d) as avg_events_last_30d,
    avg(active_users_last_30d) as avg_active_users_last_30d
from paid_account_behavior
group by retention_status
order by retention_status
