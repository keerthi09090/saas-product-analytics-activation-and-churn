-- Subscription-grain fact table: exactly one row per subscription.

select
    subscription_id,
    account_id,
    plan,
    trial_start_date,
    trial_end_date,
    subscription_start_date,
    cancellation_date,
    subscription_status,
    monthly_price
from {{ ref('stg_subscriptions') }}
