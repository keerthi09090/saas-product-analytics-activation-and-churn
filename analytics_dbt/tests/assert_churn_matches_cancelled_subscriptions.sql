-- Every logo counted as churn must correspond to a cancellation in that month.

with expected as (
    select
        cast(date_trunc('month', cancellation_date) as date) as month,
        count(*) as expected_churned_accounts
    from {{ ref('fact_subscriptions') }}
    where cancellation_date is not null
    group by 1
)

select
    churn.month
from {{ ref('mart_logo_churn') }} as churn
left join expected
    on churn.month = expected.month
where churn.churned_accounts <> coalesce(expected.expected_churned_accounts, 0)
