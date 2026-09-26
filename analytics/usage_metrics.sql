-- A non-null subscription start means the trial converted to a paid plan.
CREATE OR REPLACE VIEW trial_conversion_metrics AS
SELECT
    COUNT(*) AS total_trial_accounts,
    COUNT(*) FILTER (WHERE subscription_start_date IS NOT NULL) AS converted_accounts,
    COUNT(*) FILTER (WHERE subscription_start_date IS NOT NULL) * 1.0
        / NULLIF(COUNT(*), 0) AS trial_conversion_rate
FROM subscriptions;

-- Unique accounts producing at least one event in each calendar week.
CREATE OR REPLACE VIEW weekly_active_accounts AS
SELECT
    CAST(DATE_TRUNC('week', event_timestamp) AS DATE) AS week_start,
    COUNT(DISTINCT account_id) AS active_accounts
FROM events
GROUP BY 1
ORDER BY 1;

-- Unique accounts producing at least one event in each calendar month.
CREATE OR REPLACE VIEW monthly_active_accounts AS
SELECT
    CAST(DATE_TRUNC('month', event_timestamp) AS DATE) AS month_start,
    COUNT(DISTINCT account_id) AS active_accounts
FROM events
GROUP BY 1
ORDER BY 1;

-- Feature adoption uses all accounts as the denominator. The feature list
-- ensures a feature still appears when its usage count is zero.
CREATE OR REPLACE VIEW feature_adoption AS
WITH feature_list(feature_name) AS (
    VALUES
        ('invite_sent'),
        ('integration_connected'),
        ('report_created'),
        ('report_exported'),
        ('dashboard_viewed')
), feature_usage AS (
    SELECT
        event_name AS feature_name,
        COUNT(DISTINCT account_id) AS accounts_using_feature
    FROM events
    WHERE event_name IN (
        'invite_sent',
        'integration_connected',
        'report_created',
        'report_exported',
        'dashboard_viewed'
    )
    GROUP BY event_name
), totals AS (
    SELECT COUNT(*) AS total_accounts FROM accounts
)
SELECT
    f.feature_name,
    COALESCE(u.accounts_using_feature, 0) AS accounts_using_feature,
    t.total_accounts,
    COALESCE(u.accounts_using_feature, 0) * 1.0
        / NULLIF(t.total_accounts, 0) AS adoption_rate
FROM feature_list AS f
LEFT JOIN feature_usage AS u USING (feature_name)
CROSS JOIN totals AS t
ORDER BY CASE f.feature_name
    WHEN 'invite_sent' THEN 1
    WHEN 'integration_connected' THEN 2
    WHEN 'report_created' THEN 3
    WHEN 'report_exported' THEN 4
    WHEN 'dashboard_viewed' THEN 5
END;
