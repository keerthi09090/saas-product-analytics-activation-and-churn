-- One typed row per raw subscription.

select
    cast(subscription_id as varchar) as subscription_id,
    cast(account_id as varchar) as account_id,
    cast(plan as varchar) as plan,
    cast(trial_start_date as date) as trial_start_date,
    cast(trial_end_date as date) as trial_end_date,
    cast(subscription_start_date as date) as subscription_start_date,
    cast(cancellation_date as date) as cancellation_date,
    cast(subscription_status as varchar) as subscription_status,
    cast(monthly_price as decimal(12, 2)) as monthly_price
from read_parquet('{{ var("raw_data_path") }}/subscriptions.parquet')
