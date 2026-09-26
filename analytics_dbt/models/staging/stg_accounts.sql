-- One typed row per raw SaaS account. Business logic belongs downstream.

select
    cast(account_id as varchar) as account_id,
    cast(company_name as varchar) as company_name,
    cast(company_size as integer) as company_size,
    cast(plan as varchar) as plan,
    cast(seats_purchased as integer) as seats_purchased,
    cast(acquisition_channel as varchar) as acquisition_channel,
    cast(trial_start_date as date) as trial_start_date,
    cast(account_created_at as timestamptz) as account_created_at,
    cast(engagement_level as varchar) as engagement_level
from read_parquet('{{ var("raw_data_path") }}/accounts.parquet')
