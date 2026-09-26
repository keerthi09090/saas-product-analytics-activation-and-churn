-- A dbt singular test passes when this query returns no rows.

select
    'cohort_retention' as metric,
    cast(cohort_week as varchar) as period
from {{ ref('mart_retention_cohorts') }}
where cohort_size <= 0
    or retained_accounts < 0
    or retained_accounts > cohort_size
    or retention_rate < 0
    or retention_rate > 1
    or (weeks_since_start = 0 and retention_rate <> 1)

union all

select
    'logo_churn' as metric,
    cast(month as varchar) as period
from {{ ref('mart_logo_churn') }}
where starting_accounts < 0
    or churned_accounts < 0
    or ending_accounts < 0
    or churned_accounts > starting_accounts
    or logo_churn_rate < 0
    or logo_churn_rate > 1
