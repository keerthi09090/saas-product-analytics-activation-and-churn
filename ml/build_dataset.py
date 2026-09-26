"""Export the dbt churn feature mart and build a current scoring snapshot."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.utils import (
    ARTIFACT_DIR,
    DATASET_PATH,
    DB_PATH,
    PROJECT_ROOT,
    ensure_artifact_dir,
)


CURRENT_SCORING_SQL = """
with cutoff as (
    select cast(max(event_timestamp) as date) as prediction_date
    from fact_product_events
),
active_accounts as (
    select accounts.*, cutoff.prediction_date
    from dim_account as accounts
    cross join cutoff
    where accounts.subscription_status = 'active'
),
event_features as (
    select
        accounts.account_id,
        accounts.prediction_date,
        max(events.event_timestamp) as latest_event_at,
        count(events.event_id) filter (where events.event_timestamp >= cast(accounts.prediction_date + 1 as timestamptz) - interval 7 day) as events_last_7d,
        count(events.event_id) filter (where events.event_timestamp >= cast(accounts.prediction_date + 1 as timestamptz) - interval 30 day) as events_last_30d,
        count(events.event_id) filter (where events.event_timestamp >= cast(accounts.prediction_date + 1 as timestamptz) - interval 60 day and events.event_timestamp < cast(accounts.prediction_date + 1 as timestamptz) - interval 30 day) as events_previous_30d,
        count(distinct events.user_id) filter (where events.event_timestamp >= cast(accounts.prediction_date + 1 as timestamptz) - interval 30 day) as active_users_last_30d,
        count(distinct events.user_id) filter (where events.event_timestamp >= cast(accounts.prediction_date + 1 as timestamptz) - interval 60 day and events.event_timestamp < cast(accounts.prediction_date + 1 as timestamptz) - interval 30 day) as active_users_previous_30d,
        count(events.event_id) filter (where events.event_name = 'report_created' and events.event_timestamp >= cast(accounts.prediction_date + 1 as timestamptz) - interval 30 day) as reports_created_last_30d,
        count(events.event_id) filter (where events.event_name = 'report_created' and events.event_timestamp >= cast(accounts.prediction_date + 1 as timestamptz) - interval 60 day and events.event_timestamp < cast(accounts.prediction_date + 1 as timestamptz) - interval 30 day) as reports_created_previous_30d,
        count(events.event_id) filter (where events.event_name = 'report_exported' and events.event_timestamp >= cast(accounts.prediction_date + 1 as timestamptz) - interval 30 day) as reports_exported_last_30d,
        count(events.event_id) filter (where events.event_name = 'dashboard_viewed' and events.event_timestamp >= cast(accounts.prediction_date + 1 as timestamptz) - interval 30 day) as dashboard_views_last_30d,
        count(events.event_id) filter (where events.event_name = 'integration_connected') as integrations_connected,
        count(events.event_id) filter (where events.event_name = 'invite_sent' and events.event_timestamp >= cast(accounts.prediction_date + 1 as timestamptz) - interval 30 day) as invites_sent_last_30d,
        max(events.event_timestamp) filter (where events.event_name = 'report_created') as latest_report_at,
        max(events.event_timestamp) filter (where events.event_name = 'user_login') as latest_login_at
    from active_accounts as accounts
    left join fact_product_events as events
        on accounts.account_id = events.account_id
        and events.event_timestamp < cast(accounts.prediction_date + 1 as timestamptz)
    group by accounts.account_id, accounts.prediction_date
),
billing_features as (
    select
        accounts.account_id,
        accounts.prediction_date,
        max(invoices.invoice_date) as latest_invoice_date,
        arg_max(invoices.plan, invoices.billing_period_start) as historical_plan,
        arg_max(invoices.amount, invoices.billing_period_start) as monthly_revenue,
        count(invoices.invoice_id) filter (where invoices.payment_status = 'failed' and invoices.invoice_date >= accounts.prediction_date - 89) as failed_payments_last_90d,
        count(invoices.invoice_id) filter (where invoices.payment_status = 'failed') as total_failed_payments,
        cast(coalesce(arg_max(invoices.payment_status, invoices.billing_period_start) = 'failed', false) as integer) as recent_payment_failed
    from active_accounts as accounts
    left join current_invoices as invoices
        on accounts.account_id = invoices.account_id
        and invoices.invoice_date <= accounts.prediction_date
    group by accounts.account_id, accounts.prediction_date
)
select
    accounts.account_id,
    accounts.prediction_date,
    coalesce(billing.historical_plan, accounts.plan) as plan,
    accounts.company_size,
    accounts.seats_purchased,
    accounts.acquisition_channel,
    date_diff('day', cast(accounts.account_created_at as date), accounts.prediction_date) as account_age_days,
    events.events_last_7d,
    events.events_last_30d,
    events.events_previous_30d,
    events.active_users_last_30d,
    events.active_users_previous_30d,
    events.reports_created_last_30d,
    events.reports_created_previous_30d,
    events.reports_exported_last_30d,
    events.dashboard_views_last_30d,
    events.integrations_connected,
    events.invites_sent_last_30d,
    date_diff('day', cast(events.latest_event_at as date), accounts.prediction_date) as days_since_last_activity,
    date_diff('day', cast(events.latest_report_at as date), accounts.prediction_date) as days_since_last_report,
    date_diff('day', cast(events.latest_login_at as date), accounts.prediction_date) as days_since_last_login,
    events.events_last_30d - events.events_previous_30d as event_change_30d,
    case when events.events_previous_30d = 0 then case when events.events_last_30d = 0 then 0.0 else 1.0 end
         else (events.events_last_30d - events.events_previous_30d) * 1.0 / events.events_previous_30d end as event_change_pct,
    events.active_users_last_30d - events.active_users_previous_30d as active_user_change,
    events.reports_created_last_30d - events.reports_created_previous_30d as report_activity_change,
    events.active_users_last_30d * 1.0 / nullif(accounts.seats_purchased, 0) as seat_utilization,
    billing.failed_payments_last_90d,
    billing.total_failed_payments,
    billing.recent_payment_failed,
    coalesce(billing.monthly_revenue, 0) as monthly_revenue,
    cast(activation.is_activated and activation.activation_date <= accounts.prediction_date as integer) as is_activated,
    case when activation.activation_date <= accounts.prediction_date then activation.days_to_activation end as days_to_activation,
    events.latest_event_at,
    billing.latest_invoice_date
from active_accounts as accounts
inner join event_features as events using (account_id, prediction_date)
inner join billing_features as billing using (account_id, prediction_date)
left join mart_activation as activation using (account_id)
order by accounts.account_id
"""


def build_training_dataset() -> pd.DataFrame:
    ensure_artifact_dir()
    with duckdb.connect(str(DB_PATH), read_only=True) as connection:
        frame = connection.execute(
            "select * from mart_churn_features order by prediction_date, account_id"
        ).fetchdf()
    frame.to_parquet(DATASET_PATH, index=False)
    return frame


def build_current_scoring_dataset() -> pd.DataFrame:
    # Register the immutable Parquet input with an absolute path.  The dbt
    # staging view intentionally uses a project-relative path, which only
    # resolves while dbt is running from analytics_dbt/.  Registration keeps
    # this command reliable from any working directory without copying data.
    invoices = pd.read_parquet(PROJECT_ROOT / "data" / "invoices.parquet")
    for column in ["invoice_date", "billing_period_start", "billing_period_end"]:
        invoices[column] = pd.to_datetime(invoices[column])
    with duckdb.connect(str(DB_PATH), read_only=True) as connection:
        connection.register("current_invoices", invoices)
        return connection.execute(CURRENT_SCORING_SQL).fetchdf()


def main() -> None:
    frame = build_training_dataset()
    churn_rows = int(frame.churn_label.sum())
    print("\nChurn Training Dataset\n")
    print(f"Training observations: {len(frame):,}")
    print(f"Churn observations: {churn_rows:,}")
    print(f"Non-churn observations: {len(frame) - churn_rows:,}")
    print(f"Churn rate: {frame.churn_label.mean():.1%}")
    print(f"Prediction dates: {frame.prediction_date.min()} to {frame.prediction_date.max()}")
    print(f"Saved: {DATASET_PATH.relative_to(ARTIFACT_DIR.parent)}")


if __name__ == "__main__":
    main()
