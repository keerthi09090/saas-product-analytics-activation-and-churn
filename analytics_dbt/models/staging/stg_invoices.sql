-- One typed row per raw invoice.

select
    cast(invoice_id as varchar) as invoice_id,
    cast(account_id as varchar) as account_id,
    cast(subscription_id as varchar) as subscription_id,
    cast(invoice_date as date) as invoice_date,
    cast(billing_period_start as date) as billing_period_start,
    cast(billing_period_end as date) as billing_period_end,
    cast(plan as varchar) as plan,
    cast(amount as decimal(12, 2)) as amount,
    cast(payment_status as varchar) as payment_status
from read_parquet('{{ var("raw_data_path") }}/invoices.parquet')
