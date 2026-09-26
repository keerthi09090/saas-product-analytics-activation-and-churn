-- Gross MRR lost when an account with revenue in the prior month has no
-- revenue in the current month. New-account revenue is not in the denominator.

with monthly_revenue as (
    select *
    from {{ ref('int_account_monthly_revenue') }}
),

last_observed_month as (
    select max(month) as month
    from monthly_revenue
),

prior_month_accounts as (
    select
        account_id,
        cast(monthly_revenue.month + interval 1 month as date) as month,
        monthly_revenue as prior_mrr
    from monthly_revenue
    cross join last_observed_month
    where monthly_revenue.month + interval 1 month
        <= last_observed_month.month
),

monthly_churn as (
    select
        prior_month_accounts.month,
        sum(prior_month_accounts.prior_mrr) as starting_mrr,
        sum(case
            when current_month.account_id is null
                then prior_month_accounts.prior_mrr
            else 0
        end) as churned_mrr
    from prior_month_accounts
    left join monthly_revenue as current_month
        on prior_month_accounts.account_id = current_month.account_id
        and prior_month_accounts.month = current_month.month
    group by prior_month_accounts.month
)

select
    month,
    starting_mrr,
    churned_mrr,
    churned_mrr * 1.0 / nullif(starting_mrr, 0) as revenue_churn_rate
from monthly_churn
where starting_mrr > 0
order by month
