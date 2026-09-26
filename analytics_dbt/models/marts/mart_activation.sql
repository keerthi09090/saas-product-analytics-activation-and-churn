-- Reporting-ready activation outcome at one row per account.

select
    account_id,
    is_activated,
    activation_date,
    days_to_activation
from {{ ref('int_account_activation') }}
