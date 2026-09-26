-- Contracted monthly revenue at account-month grain. Failed and pending
-- invoices still represent contracted MRR; cash collection is a separate
-- metric. Historical invoice plan is used because accounts can change plans.

select
    invoices.account_id,
    cast(date_trunc('month', invoices.billing_period_start) as date) as month,
    arg_max(invoices.plan, invoices.billing_period_start) as plan,
    subscriptions.subscription_status,
    sum(invoices.amount) as monthly_revenue
from {{ ref('stg_invoices') }} as invoices
inner join {{ ref('stg_subscriptions') }} as subscriptions
    on invoices.subscription_id = subscriptions.subscription_id
group by
    invoices.account_id,
    cast(date_trunc('month', invoices.billing_period_start) as date),
    subscriptions.subscription_status
