-- Account adoption for the five portfolio features. A fixed feature list keeps
-- unused features in the output with a zero numerator.

with features(feature_name, display_order) as (
    values
        ('invite_sent', 1),
        ('integration_connected', 2),
        ('report_created', 3),
        ('report_exported', 4),
        ('dashboard_viewed', 5)
),

feature_usage as (
    select
        event_name as feature_name,
        count(distinct account_id) as accounts_using_feature
    from {{ ref('fact_product_events') }}
    where event_name in (
        'invite_sent',
        'integration_connected',
        'report_created',
        'report_exported',
        'dashboard_viewed'
    )
    group by event_name
),

account_total as (
    select count(*) as total_accounts
    from {{ ref('dim_account') }}
)

select
    features.feature_name,
    coalesce(feature_usage.accounts_using_feature, 0) as accounts_using_feature,
    account_total.total_accounts,
    coalesce(feature_usage.accounts_using_feature, 0) * 1.0
        / nullif(account_total.total_accounts, 0) as adoption_rate
from features
left join feature_usage
    on features.feature_name = feature_usage.feature_name
cross join account_total
order by features.display_order
