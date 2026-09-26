-- One typed row per raw product user.

select
    cast(user_id as varchar) as user_id,
    cast(account_id as varchar) as account_id,
    cast(role as varchar) as role,
    cast(created_at as timestamptz) as created_at,
    cast(is_admin as boolean) as is_admin
from read_parquet('{{ var("raw_data_path") }}/users.parquet')
