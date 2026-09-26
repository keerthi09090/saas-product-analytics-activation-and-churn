-- Roll product events up to one activity record per account. Recency windows
-- use the latest event date in the synthetic dataset, not the wall clock, so
-- results stay reproducible.

with observation_date as (
    select max(cast(event_timestamp as date)) as activity_as_of_date
    from {{ ref('stg_events') }}
),

event_activity as (
    select
        accounts.account_id,
        observation_date.activity_as_of_date,
        min(events.event_timestamp) as first_event_at,
        max(events.event_timestamp) as last_event_at,
        count(events.event_id) as total_events,
        count(distinct events.user_id) as number_of_active_users,
        count(events.event_id) filter (
            where events.event_name = 'report_created'
        ) as report_created_count,
        count(events.event_id) filter (
            where events.event_name = 'report_exported'
        ) as report_exported_count,
        count(events.event_id) filter (
            where events.event_name = 'dashboard_viewed'
        ) as dashboard_viewed_count,
        count(events.event_id) filter (
            where events.event_name = 'invite_sent'
        ) as invite_sent_count,
        count(events.event_id) filter (
            where events.event_name = 'integration_connected'
        ) as integration_connected_count,
        count(events.event_id) filter (
            where cast(events.event_timestamp as date)
                >= observation_date.activity_as_of_date - interval 6 day
        ) as events_last_7d,
        count(events.event_id) filter (
            where cast(events.event_timestamp as date)
                >= observation_date.activity_as_of_date - interval 29 day
        ) as events_last_30d,
        count(distinct events.user_id) filter (
            where cast(events.event_timestamp as date)
                >= observation_date.activity_as_of_date - interval 29 day
        ) as active_users_last_30d
    from {{ ref('stg_accounts') }} as accounts
    cross join observation_date
    left join {{ ref('stg_events') }} as events
        on accounts.account_id = events.account_id
    group by
        accounts.account_id,
        observation_date.activity_as_of_date
),

provisioned_users as (
    select
        account_id,
        count(*) as provisioned_users
    from {{ ref('stg_users') }}
    group by account_id
)

select
    event_activity.account_id,
    event_activity.first_event_at,
    event_activity.last_event_at,
    event_activity.total_events,
    event_activity.number_of_active_users,
    event_activity.report_created_count,
    event_activity.report_exported_count,
    event_activity.dashboard_viewed_count,
    event_activity.invite_sent_count,
    event_activity.integration_connected_count,
    accounts.seats_purchased,
    coalesce(provisioned_users.provisioned_users, 0) as provisioned_users,
    event_activity.number_of_active_users * 1.0
        / nullif(accounts.seats_purchased, 0) as seat_utilization,
    event_activity.activity_as_of_date,
    case
        when event_activity.last_event_at is not null then date_diff(
            'day',
            cast(event_activity.last_event_at as date),
            event_activity.activity_as_of_date
        )
    end as days_since_last_activity,
    event_activity.events_last_7d,
    event_activity.events_last_30d,
    event_activity.active_users_last_30d
from event_activity
inner join {{ ref('stg_accounts') }} as accounts
    on event_activity.account_id = accounts.account_id
left join provisioned_users
    on event_activity.account_id = provisioned_users.account_id
