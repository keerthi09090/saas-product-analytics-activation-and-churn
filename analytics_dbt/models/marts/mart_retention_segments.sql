-- Current paid-account retention by four business dimensions. Trials are
-- excluded so they are not incorrectly labelled as retained. Numeric company
-- size is bucketed to keep the comparison useful and readable.

with paid_accounts as (
    select
        account_id,
        plan,
        engagement_level,
        company_size,
        acquisition_channel,
        case
            when subscription_status = 'active' then 'retained'
            when subscription_status = 'cancelled' then 'churned'
        end as retention_status
    from {{ ref('dim_account') }}
    where subscription_start_date is not null
        and subscription_status in ('active', 'cancelled')
),

segments as (
    select
        account_id,
        retention_status,
        'plan' as segment_type,
        plan as segment_value
    from paid_accounts

    union all

    select
        account_id,
        retention_status,
        'engagement_level' as segment_type,
        engagement_level as segment_value
    from paid_accounts

    union all

    select
        account_id,
        retention_status,
        'company_size' as segment_type,
        case
            when company_size <= 50 then '1-50'
            when company_size <= 250 then '51-250'
            when company_size <= 1000 then '251-1000'
            else '1001+'
        end as segment_value
    from paid_accounts

    union all

    select
        account_id,
        retention_status,
        'acquisition_channel' as segment_type,
        acquisition_channel as segment_value
    from paid_accounts
)

select
    segment_type,
    segment_value,
    count(*) as total_accounts,
    count(*) filter (where retention_status = 'retained') as retained_accounts,
    count(*) filter (where retention_status = 'churned') as churned_accounts,
    count(*) filter (where retention_status = 'retained') * 1.0
        / nullif(count(*), 0) as retention_rate
from segments
group by
    segment_type,
    segment_value
order by
    segment_type,
    segment_value
