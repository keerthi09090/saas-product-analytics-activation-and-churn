-- Monthly, leakage-safe training snapshots for 30-day churn prediction.
-- prediction_date is an end-of-day cutoff: events through that calendar day
-- are features, while cancellation strictly after it belongs to the label.

with snapshot_bounds as (
    select
        cast(date_trunc('month', min(subscription_start_date)) + interval 1 month as date)
            as first_prediction_date,
        -- Billing snapshots establish the latest fully observed paid period.
        -- Live events may arrive beyond the current labeled training horizon.
        cast(date_trunc('month', max(invoice_date)) as date)
            as last_prediction_date
    from {{ ref('stg_subscriptions') }}
    cross join (select max(invoice_date) as invoice_date from {{ ref('stg_invoices') }})
    where subscription_start_date is not null
),

prediction_dates as (
    select cast(snapshot_date as date) as prediction_date
    from snapshot_bounds,
    unnest(generate_series(
        first_prediction_date,
        last_prediction_date,
        interval 1 month
    )) as dates(snapshot_date)
),

eligible_snapshots as (
    select
        subscriptions.account_id,
        prediction_dates.prediction_date,
        subscriptions.subscription_start_date,
        subscriptions.cancellation_date
    from {{ ref('stg_subscriptions') }} as subscriptions
    cross join prediction_dates
    where subscriptions.subscription_start_date <= prediction_dates.prediction_date
        and (
            subscriptions.cancellation_date is null
            or subscriptions.cancellation_date > prediction_dates.prediction_date
        )
),

event_features as (
    select
        snapshots.account_id,
        snapshots.prediction_date,
        max(events.event_timestamp) as latest_event_at,
        count(events.event_id) filter (
            where events.event_timestamp >= cast(snapshots.prediction_date + 1 as timestamptz) - interval 7 day
        ) as events_last_7d,
        count(events.event_id) filter (
            where events.event_timestamp >= cast(snapshots.prediction_date + 1 as timestamptz) - interval 30 day
        ) as events_last_30d,
        count(events.event_id) filter (
            where events.event_timestamp >= cast(snapshots.prediction_date + 1 as timestamptz) - interval 60 day
                and events.event_timestamp < cast(snapshots.prediction_date + 1 as timestamptz) - interval 30 day
        ) as events_previous_30d,
        count(distinct events.user_id) filter (
            where events.event_timestamp >= cast(snapshots.prediction_date + 1 as timestamptz) - interval 30 day
        ) as active_users_last_30d,
        count(distinct events.user_id) filter (
            where events.event_timestamp >= cast(snapshots.prediction_date + 1 as timestamptz) - interval 60 day
                and events.event_timestamp < cast(snapshots.prediction_date + 1 as timestamptz) - interval 30 day
        ) as active_users_previous_30d,
        count(events.event_id) filter (
            where events.event_name = 'report_created'
                and events.event_timestamp >= cast(snapshots.prediction_date + 1 as timestamptz) - interval 30 day
        ) as reports_created_last_30d,
        count(events.event_id) filter (
            where events.event_name = 'report_created'
                and events.event_timestamp >= cast(snapshots.prediction_date + 1 as timestamptz) - interval 60 day
                and events.event_timestamp < cast(snapshots.prediction_date + 1 as timestamptz) - interval 30 day
        ) as reports_created_previous_30d,
        count(events.event_id) filter (
            where events.event_name = 'report_exported'
                and events.event_timestamp >= cast(snapshots.prediction_date + 1 as timestamptz) - interval 30 day
        ) as reports_exported_last_30d,
        count(events.event_id) filter (
            where events.event_name = 'dashboard_viewed'
                and events.event_timestamp >= cast(snapshots.prediction_date + 1 as timestamptz) - interval 30 day
        ) as dashboard_views_last_30d,
        count(events.event_id) filter (
            where events.event_name = 'integration_connected'
        ) as integrations_connected,
        count(events.event_id) filter (
            where events.event_name = 'invite_sent'
                and events.event_timestamp >= cast(snapshots.prediction_date + 1 as timestamptz) - interval 30 day
        ) as invites_sent_last_30d,
        max(events.event_timestamp) filter (
            where events.event_name = 'report_created'
        ) as latest_report_at,
        max(events.event_timestamp) filter (
            where events.event_name = 'user_login'
        ) as latest_login_at
    from eligible_snapshots as snapshots
    left join {{ ref('stg_events') }} as events
        on snapshots.account_id = events.account_id
        and events.event_timestamp < cast(snapshots.prediction_date + 1 as timestamptz)
    group by snapshots.account_id, snapshots.prediction_date
),

billing_features as (
    select
        snapshots.account_id,
        snapshots.prediction_date,
        max(invoices.invoice_date) as latest_invoice_date,
        arg_max(invoices.plan, invoices.billing_period_start) as historical_plan,
        arg_max(invoices.amount, invoices.billing_period_start) as monthly_revenue,
        count(invoices.invoice_id) filter (
            where invoices.payment_status = 'failed'
                and invoices.invoice_date >= snapshots.prediction_date - 89
        ) as failed_payments_last_90d,
        count(invoices.invoice_id) filter (
            where invoices.payment_status = 'failed'
        ) as total_failed_payments,
        cast(
            coalesce(arg_max(invoices.payment_status, invoices.billing_period_start) = 'failed', false)
            as integer
        ) as recent_payment_failed
    from eligible_snapshots as snapshots
    left join {{ ref('stg_invoices') }} as invoices
        on snapshots.account_id = invoices.account_id
        and invoices.invoice_date <= snapshots.prediction_date
    group by snapshots.account_id, snapshots.prediction_date
),

assembled as (
    select
        snapshots.account_id,
        snapshots.prediction_date,
        coalesce(billing.historical_plan, accounts.plan) as plan,
        accounts.company_size,
        accounts.seats_purchased,
        accounts.acquisition_channel,
        date_diff('day', cast(accounts.account_created_at as date), snapshots.prediction_date)
            as account_age_days,
        events.events_last_7d,
        events.events_last_30d,
        events.events_previous_30d,
        events.active_users_last_30d,
        events.active_users_previous_30d,
        events.reports_created_last_30d,
        events.reports_created_previous_30d,
        events.reports_exported_last_30d,
        events.dashboard_views_last_30d,
        events.integrations_connected,
        events.invites_sent_last_30d,
        date_diff('day', cast(events.latest_event_at as date), snapshots.prediction_date)
            as days_since_last_activity,
        date_diff('day', cast(events.latest_report_at as date), snapshots.prediction_date)
            as days_since_last_report,
        date_diff('day', cast(events.latest_login_at as date), snapshots.prediction_date)
            as days_since_last_login,
        events.events_last_30d - events.events_previous_30d as event_change_30d,
        case
            when events.events_previous_30d = 0 then
                case when events.events_last_30d = 0 then 0.0 else 1.0 end
            else (events.events_last_30d - events.events_previous_30d) * 1.0
                / events.events_previous_30d
        end as event_change_pct,
        events.active_users_last_30d - events.active_users_previous_30d
            as active_user_change,
        events.reports_created_last_30d - events.reports_created_previous_30d
            as report_activity_change,
        events.active_users_last_30d * 1.0 / nullif(accounts.seats_purchased, 0)
            as seat_utilization,
        billing.failed_payments_last_90d,
        billing.total_failed_payments,
        billing.recent_payment_failed,
        coalesce(billing.monthly_revenue, 0) as monthly_revenue,
        cast(
            activation.is_activated
            and activation.activation_date <= snapshots.prediction_date
            as integer
        ) as is_activated,
        case
            when activation.activation_date <= snapshots.prediction_date
                then activation.days_to_activation
        end as days_to_activation,
        events.latest_event_at,
        billing.latest_invoice_date,
        cast(
            coalesce(
                snapshots.cancellation_date > snapshots.prediction_date
                and snapshots.cancellation_date <= snapshots.prediction_date + 30,
                false
            )
            as integer
        ) as churn_label
    from eligible_snapshots as snapshots
    inner join {{ ref('stg_accounts') }} as accounts using (account_id)
    inner join event_features as events using (account_id, prediction_date)
    inner join billing_features as billing using (account_id, prediction_date)
    left join {{ ref('int_account_activation') }} as activation using (account_id)
)

select * from assembled
