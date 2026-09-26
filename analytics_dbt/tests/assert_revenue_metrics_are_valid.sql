-- Revenue movement fields must be nonnegative and reconcile to NRR.

with invalid_revenue_churn as (
    select
        'revenue_churn' as metric,
        cast(month as varchar) as period
    from {{ ref('mart_revenue_churn') }}
    where starting_mrr < 0
        or churned_mrr < 0
        or churned_mrr > starting_mrr
        or revenue_churn_rate < 0
        or revenue_churn_rate > 1
),

invalid_nrr as (
    select
        'net_revenue_retention' as metric,
        cast(month as varchar) as period
    from {{ ref('mart_revenue_retention') }}
    where starting_mrr <= 0
        or churned_mrr < 0
        or contraction_mrr < 0
        or expansion_mrr < 0
        or ending_mrr < 0
        or abs(
            ending_mrr
            - (
                starting_mrr
                - churned_mrr
                - contraction_mrr
                + expansion_mrr
            )
        ) > 0.01
        or abs(nrr - ending_mrr / starting_mrr) > 0.000001
),

inconsistent_churn as (
    select
        'churn_reconciliation' as metric,
        cast(retention.month as varchar) as period
    from {{ ref('mart_revenue_retention') }} as retention
    inner join {{ ref('mart_revenue_churn') }} as churn
        on retention.month = churn.month
    where abs(retention.starting_mrr - churn.starting_mrr) > 0.01
        or abs(retention.churned_mrr - churn.churned_mrr) > 0.01
)

select * from invalid_revenue_churn
union all
select * from invalid_nrr
union all
select * from inconsistent_churn
