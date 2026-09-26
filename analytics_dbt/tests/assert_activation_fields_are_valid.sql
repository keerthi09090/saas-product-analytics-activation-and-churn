-- A dbt data test fails when this query returns any invalid rows.

select *
from {{ ref('int_account_activation') }}
where activation_date < trial_start_date
   or days_to_activation < 0
   or days_to_activation >= 14
   or (
       is_activated
       and (
           workspace_created_at is null
           or first_invite_sent_at is null
           or first_integration_connected_at is null
           or activation_date is null
           or days_to_activation is null
       )
   )
   or (
       not is_activated
       and (activation_date is not null or days_to_activation is not null)
   )
