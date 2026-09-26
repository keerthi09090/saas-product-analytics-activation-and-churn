-- Snapshot keys must be unique and feature cutoffs cannot cross prediction time.

with invalid_rows as (
    select account_id, prediction_date
    from {{ ref('mart_churn_features') }}
    where cast(latest_event_at as date) > prediction_date
        or latest_invoice_date > prediction_date
        or seat_utilization < 0
        or seat_utilization > 1
        or events_last_7d < 0
        or events_last_30d < 0
        or events_previous_30d < 0
        or active_users_last_30d < 0
        or reports_created_last_30d < 0
        or failed_payments_last_90d < 0
),

duplicate_rows as (
    select account_id, prediction_date
    from {{ ref('mart_churn_features') }}
    group by account_id, prediction_date
    having count(*) > 1
)

select * from invalid_rows
union all
select * from duplicate_rows
