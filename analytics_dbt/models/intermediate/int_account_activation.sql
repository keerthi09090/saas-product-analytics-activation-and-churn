-- Reusable account-level activation logic.
-- The half-open window includes trial days 0-13 and excludes day 14.

with required_event_times as (
    select
        accounts.account_id,
        accounts.trial_start_date,
        min(events.event_timestamp) filter (
            where events.event_name = 'workspace_created'
        ) as workspace_created_at,
        min(events.event_timestamp) filter (
            where events.event_name = 'invite_sent'
        ) as first_invite_sent_at,
        min(events.event_timestamp) filter (
            where events.event_name = 'integration_connected'
        ) as first_integration_connected_at
    from {{ ref('stg_accounts') }} as accounts
    left join {{ ref('stg_events') }} as events
        on accounts.account_id = events.account_id
        and events.event_timestamp >= cast(accounts.trial_start_date as timestamptz)
        and events.event_timestamp
            < cast(accounts.trial_start_date as timestamptz) + interval 14 day
    group by
        accounts.account_id,
        accounts.trial_start_date
),

activation_status as (
    select
        *,
        workspace_created_at is not null
            and first_invite_sent_at is not null
            and first_integration_connected_at is not null as is_activated
    from required_event_times
)

select
    account_id,
    trial_start_date,
    workspace_created_at,
    first_invite_sent_at,
    first_integration_connected_at,
    case
        when is_activated then cast(
            greatest(
                workspace_created_at,
                first_invite_sent_at,
                first_integration_connected_at
            ) as date
        )
    end as activation_date,
    is_activated,
    case
        when is_activated then date_diff(
            'day',
            trial_start_date,
            cast(
                greatest(
                    workspace_created_at,
                    first_invite_sent_at,
                    first_integration_connected_at
                ) as date
            )
        )
    end as days_to_activation
from activation_status
