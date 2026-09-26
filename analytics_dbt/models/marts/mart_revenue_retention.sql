-- Net revenue retention for the prior month's customer base. Ending MRR
-- excludes new accounts so NRR only reflects churn, contraction, and expansion.

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

account_changes as (
    select
        prior_month_accounts.month,
        prior_month_accounts.prior_mrr,
        coalesce(current_month.monthly_revenue, 0) as current_mrr
    from prior_month_accounts
    left join monthly_revenue as current_month
        on prior_month_accounts.account_id = current_month.account_id
        and prior_month_accounts.month = current_month.month
),

monthly_retention as (
    select
        month,
        sum(prior_mrr) as starting_mrr,
        sum(case when current_mrr = 0 then prior_mrr else 0 end) as churned_mrr,
        sum(case
            when current_mrr > 0 and current_mrr < prior_mrr
                then prior_mrr - current_mrr
            else 0
        end) as contraction_mrr,
        sum(case
            when current_mrr > prior_mrr then current_mrr - prior_mrr
            else 0
        end) as expansion_mrr,
        sum(current_mrr) as ending_mrr
    from account_changes
    group by month
)

select
    month,
    starting_mrr,
    churned_mrr,
    contraction_mrr,
    expansion_mrr,
    ending_mrr,
    ending_mrr * 1.0 / nullif(starting_mrr, 0) as nrr
from monthly_retention
where starting_mrr > 0
order by month
