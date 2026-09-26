-- Current account attributes enriched with subscription status and price.

select
    accounts.account_id,
    accounts.company_name,
    accounts.company_size,
    accounts.plan,
    accounts.seats_purchased,
    accounts.acquisition_channel,
    accounts.trial_start_date,
    accounts.account_created_at,
    accounts.engagement_level,
    subscriptions.subscription_status,
    subscriptions.subscription_start_date,
    subscriptions.cancellation_date,
    subscriptions.monthly_price
from {{ ref('stg_accounts') }} as accounts
left join {{ ref('stg_subscriptions') }} as subscriptions
    on accounts.account_id = subscriptions.account_id
