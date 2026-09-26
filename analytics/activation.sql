-- An account activates when all three required events occur during its first
-- 14 trial days. Activation happens on the last required event's date.

CREATE OR REPLACE VIEW activation_events AS
SELECT
    a.account_id,
    CAST(a.trial_start_date AS DATE) AS trial_start_date,
    MIN(CASE WHEN e.event_name = 'workspace_created'
             THEN CAST(e.event_timestamp AS DATE) END) AS workspace_created_date,
    MIN(CASE WHEN e.event_name = 'invite_sent'
             THEN CAST(e.event_timestamp AS DATE) END) AS first_invite_date,
    MIN(CASE WHEN e.event_name = 'integration_connected'
             THEN CAST(e.event_timestamp AS DATE) END) AS integration_connected_date
FROM accounts AS a
LEFT JOIN events AS e
    ON a.account_id = e.account_id
   AND e.event_timestamp >= CAST(a.trial_start_date AS TIMESTAMPTZ)
   AND e.event_timestamp < CAST(a.trial_start_date AS TIMESTAMPTZ) + INTERVAL 14 DAY
GROUP BY a.account_id, a.trial_start_date;

CREATE OR REPLACE VIEW account_activation AS
SELECT
    account_id,
    trial_start_date,
    CASE
        WHEN workspace_created_date IS NOT NULL
         AND first_invite_date IS NOT NULL
         AND integration_connected_date IS NOT NULL
        THEN GREATEST(
            workspace_created_date,
            first_invite_date,
            integration_connected_date
        )
        ELSE NULL
    END AS activation_date,
    workspace_created_date IS NOT NULL
        AND first_invite_date IS NOT NULL
        AND integration_connected_date IS NOT NULL AS activated,
    CASE
        WHEN workspace_created_date IS NOT NULL
         AND first_invite_date IS NOT NULL
         AND integration_connected_date IS NOT NULL
        THEN DATE_DIFF(
            'day',
            trial_start_date,
            GREATEST(
                workspace_created_date,
                first_invite_date,
                integration_connected_date
            )
        )
        ELSE NULL
    END AS days_to_activation
FROM activation_events;

CREATE OR REPLACE VIEW activation_metrics AS
SELECT
    COUNT(*) AS total_accounts,
    COUNT(*) FILTER (WHERE activated) AS activated_accounts,
    COUNT(*) FILTER (WHERE activated) * 1.0 / NULLIF(COUNT(*), 0) AS activation_rate,
    MEDIAN(days_to_activation) FILTER (WHERE activated) AS median_days_to_activation
FROM account_activation;
