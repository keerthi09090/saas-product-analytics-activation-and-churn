-- Weekly signup-cohort retention. Week 0 represents cohort entry and is 100%;
-- later weeks require at least one meaningful product event in that week.

with account_cohorts as (
    select
        account_id,
        cast(date_trunc('week', trial_start_date) as date) as cohort_week
    from {{ ref('dim_account') }}
),

observation_window as (
    select cast(date_trunc('week', max(event_timestamp)) as date) as last_week
    from {{ ref('fact_product_events') }}
),

cohort_weeks as (
    select
        cohorts.cohort_week,
        cast(generated.activity_week as date) as activity_week
    from (
        select distinct cohort_week
        from account_cohorts
    ) as cohorts
    cross join observation_window
    cross join generate_series(
        cohorts.cohort_week,
        observation_window.last_week,
        interval 1 week
    ) as generated(activity_week)
),

meaningful_activity as (
    select distinct
        account_id,
        cast(date_trunc('week', event_timestamp) as date) as activity_week
    from {{ ref('fact_product_events') }}
    where event_name in (
        'user_login',
        'dashboard_viewed',
        'report_created',
        'report_exported',
        'integration_connected',
        'invite_sent'
    )
),

cohort_retention as (
    select
        cohort_weeks.cohort_week,
        date_diff(
            'week',
            cohort_weeks.cohort_week,
            cohort_weeks.activity_week
        ) as weeks_since_start,
        count(distinct account_cohorts.account_id) as cohort_size,
        count(distinct case
            when cohort_weeks.activity_week = cohort_weeks.cohort_week
                or meaningful_activity.account_id is not null
            then account_cohorts.account_id
        end) as retained_accounts
    from cohort_weeks
    inner join account_cohorts
        on cohort_weeks.cohort_week = account_cohorts.cohort_week
    left join meaningful_activity
        on account_cohorts.account_id = meaningful_activity.account_id
        and cohort_weeks.activity_week = meaningful_activity.activity_week
    group by
        cohort_weeks.cohort_week,
        cohort_weeks.activity_week
)

select
    cohort_week,
    weeks_since_start,
    cohort_size,
    retained_accounts,
    retained_accounts * 1.0 / nullif(cohort_size, 0) as retention_rate
from cohort_retention
order by
    cohort_week,
    weeks_since_start
