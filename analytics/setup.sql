-- Create five DuckDB views that read the Level 1 Parquet files directly.

SET TimeZone = 'UTC';

CREATE OR REPLACE VIEW accounts AS
SELECT * FROM read_parquet('data/accounts.parquet');

CREATE OR REPLACE VIEW users AS
SELECT * FROM read_parquet('data/users.parquet');

CREATE OR REPLACE VIEW subscriptions AS
SELECT * FROM read_parquet('data/subscriptions.parquet');

CREATE OR REPLACE VIEW invoices AS
SELECT * FROM read_parquet('data/invoices.parquet');

CREATE OR REPLACE VIEW events AS
SELECT
    event_id,
    account_id,
    user_id,
    event_name,
    CAST(event_timestamp AS TIMESTAMPTZ) AS event_timestamp,
    event_version
FROM read_parquet('data/events.parquet');
