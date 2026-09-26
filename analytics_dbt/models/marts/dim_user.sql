-- One row per user, suitable for joins from product events.

select
    user_id,
    account_id,
    role,
    created_at,
    is_admin
from {{ ref('stg_users') }}
