-- Monthly customer-logo churn for converted accounts. Starting accounts are
-- those present at the opening boundary; cancellation_date is exclusive.

with paid_subscriptions as (
    select
        account_id,
        subscription_start_date,
        cancellation_date
    from {{ ref('fact_subscriptions') }}
    where subscription_start_date is not null
),

month_bounds as (
    select
        cast(date_trunc('month', min(subscription_start_date)) as date) as first_month,
        (
            select cast(date_trunc('month', max(event_timestamp)) as date)
            from {{ ref('fact_product_events') }}
        ) as last_month
    from paid_subscriptions
),

months as (
    select cast(generated.month as date) as month
    from month_bounds
    cross join generate_series(
        month_bounds.first_month,
        month_bounds.last_month,
        interval 1 month
    ) as generated(month)
),

monthly_counts as (
    select
        months.month,
        count(distinct case
            when paid_subscriptions.subscription_start_date < months.month
                and (
                    paid_subscriptions.cancellation_date is null
                    or paid_subscriptions.cancellation_date >= months.month
                )
            then paid_subscriptions.account_id
        end) as starting_accounts,
        count(distinct case
            when paid_subscriptions.subscription_start_date < months.month
                and paid_subscriptions.cancellation_date >= months.month
                and paid_subscriptions.cancellation_date
                    < months.month + interval 1 month
            then paid_subscriptions.account_id
        end) as churned_accounts,
        count(distinct case
            when paid_subscriptions.subscription_start_date
                    < months.month + interval 1 month
                and (
                    paid_subscriptions.cancellation_date is null
                    or paid_subscriptions.cancellation_date
                        >= months.month + interval 1 month
                )
            then paid_subscriptions.account_id
        end) as ending_accounts
    from months
    cross join paid_subscriptions
    group by months.month
)

select
    month,
    starting_accounts,
    churned_accounts,
    ending_accounts,
    coalesce(
        churned_accounts * 1.0 / nullif(starting_accounts, 0),
        0.0
    ) as logo_churn_rate
from monthly_counts
order by month
