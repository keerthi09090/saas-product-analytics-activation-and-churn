from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from simulator.generate import (
    EVENT_NAMES,
    calculate_cancellation_probability,
    generate_datasets,
    save_datasets,
)


EXPECTED_COLUMNS = {
    "accounts": [
        "account_id",
        "company_name",
        "company_size",
        "plan",
        "seats_purchased",
        "acquisition_channel",
        "trial_start_date",
        "account_created_at",
        "engagement_level",
    ],
    "users": ["user_id", "account_id", "role", "created_at", "is_admin"],
    "subscriptions": [
        "subscription_id",
        "account_id",
        "plan",
        "trial_start_date",
        "trial_end_date",
        "subscription_start_date",
        "cancellation_date",
        "subscription_status",
        "monthly_price",
    ],
    "invoices": [
        "invoice_id",
        "account_id",
        "subscription_id",
        "invoice_date",
        "billing_period_start",
        "billing_period_end",
        "plan",
        "amount",
        "payment_status",
    ],
    "events": [
        "event_id",
        "account_id",
        "user_id",
        "event_name",
        "event_timestamp",
        "event_version",
    ],
}


def test_required_files_columns_and_relationships(tmp_path: Path):
    datasets = generate_datasets(account_count=100, seed=42)
    save_datasets(datasets, tmp_path)

    for name, expected_columns in EXPECTED_COLUMNS.items():
        path = tmp_path / f"{name}.parquet"
        assert path.exists()
        assert list(pd.read_parquet(path).columns) == expected_columns

    accounts = datasets["accounts"]
    users = datasets["users"]
    subscriptions = datasets["subscriptions"]
    invoices = datasets["invoices"]
    events = datasets["events"]

    assert accounts.account_id.is_unique
    assert users.user_id.is_unique
    assert subscriptions.subscription_id.is_unique
    assert invoices.invoice_id.is_unique
    assert events.event_id.is_unique
    assert set(users.account_id) <= set(accounts.account_id)
    assert set(subscriptions.account_id) <= set(accounts.account_id)
    assert set(invoices.account_id) <= set(accounts.account_id)
    assert set(events.account_id) <= set(accounts.account_id)
    assert set(events.user_id) <= set(users.user_id)
    assert (accounts.seats_purchased >= 0).all()
    assert (invoices.amount >= 0).all()


def test_events_follow_users_workspace_and_reports():
    datasets = generate_datasets(account_count=100, seed=42)
    users = datasets["users"]
    events = datasets["events"].assign(
        event_time=lambda frame: pd.to_datetime(frame.event_timestamp, utc=True)
    )

    joined = events.merge(
        users.assign(user_created=lambda frame: pd.to_datetime(frame.created_at, utc=True)),
        on="user_id",
        suffixes=("_event", "_user"),
    )
    assert (joined.account_id_event == joined.account_id_user).all()
    assert (joined.event_time >= joined.user_created).all()

    workspace = (
        events[events.event_name == "workspace_created"]
        .set_index("account_id")
        .event_time
    )
    later_activity = events[events.event_name != "workspace_created"]
    assert (
        later_activity.event_time > later_activity.account_id.map(workspace)
    ).mean() >= 0.95

    for account_id, history in events.groupby("account_id"):
        created = history[history.event_name == "report_created"].event_time
        exported = history[history.event_name == "report_exported"].event_time
        if not exported.empty:
            assert not created.empty
            assert created.min() < exported.min(), account_id


def test_data_has_expected_business_patterns():
    datasets = generate_datasets(account_count=100, seed=42)
    accounts = datasets["accounts"]
    users = datasets["users"]
    events = datasets["events"].copy()

    median_seats = accounts.groupby("plan").seats_purchased.median()
    assert median_seats["Enterprise"] > median_seats["Growth"] > median_seats["Starter"]

    users_per_account = users.groupby("account_id").size().rename("user_count")
    account_sizes = accounts.set_index("account_id").join(users_per_account)
    assert account_sizes[["company_size", "user_count"]].corr().iloc[0, 1] > 0.25
    assert (account_sizes.user_count <= account_sizes.seats_purchased).all()

    event_counts = events.groupby("account_id").size().rename("event_count")
    engagement_activity = accounts.set_index("account_id").join(event_counts).groupby(
        "engagement_level"
    ).event_count.mean()
    assert engagement_activity["high"] > engagement_activity["medium"] > engagement_activity["low"]

    event_weekday = pd.to_datetime(events.event_timestamp, utc=True).dt.weekday
    assert (event_weekday < 5).mean() > 0.75
    assert set(events.event_name) == set(EVENT_NAMES)

    subscriptions = datasets["subscriptions"]
    converted = subscriptions.subscription_start_date.notna()
    cancelled = subscriptions.subscription_status == "cancelled"
    assert 55 <= converted.sum() <= 65
    assert 8 <= cancelled.sum() <= 15


def test_same_seed_is_reproducible():
    first = generate_datasets(account_count=100, seed=42)
    second = generate_datasets(account_count=100, seed=42)

    for name in EXPECTED_COLUMNS:
        assert_frame_equal(first[name], second[name], check_like=False)


def test_billing_history_supports_level_5_revenue_metrics():
    datasets = generate_datasets(account_count=100, seed=42)
    subscriptions = datasets["subscriptions"]
    invoices = datasets["invoices"].sort_values(
        ["account_id", "billing_period_start"]
    )

    cancelled = subscriptions.subscription_status == "cancelled"
    assert subscriptions.cancellation_date.notna().equals(cancelled)
    assert subscriptions.loc[cancelled, "subscription_start_date"].notna().all()
    assert (
        pd.to_datetime(subscriptions.loc[cancelled, "cancellation_date"])
        > pd.to_datetime(
            subscriptions.loc[cancelled, "subscription_start_date"]
        )
    ).all()

    assert set(invoices.subscription_id) <= set(subscriptions.subscription_id)
    assert (
        pd.to_datetime(invoices.billing_period_end)
        >= pd.to_datetime(invoices.billing_period_start)
    ).all()

    plan_prices = {"Starter": 49, "Growth": 249, "Enterprise": 999}
    assert invoices.amount.equals(invoices.plan.map(plan_prices))

    monthly_changes = invoices.groupby("account_id").amount.diff().dropna()
    assert (monthly_changes > 0).any(), "Seed 42 should include an expansion"
    assert (monthly_changes < 0).any(), "Seed 42 should include a contraction"

    cancelled_dates = subscriptions.loc[
        cancelled, ["account_id", "cancellation_date"]
    ].set_index("account_id").cancellation_date
    cancelled_invoices = invoices[invoices.account_id.isin(cancelled_dates.index)]
    invoice_cancellations = pd.to_datetime(
        cancelled_invoices.account_id.map(cancelled_dates)
    )
    assert (
        pd.to_datetime(cancelled_invoices.billing_period_start)
        < invoice_cancellations
    ).all()

    events = datasets["events"]
    cancelled_events = events[events.account_id.isin(cancelled_dates.index)]
    event_cancellations = pd.to_datetime(
        cancelled_events.account_id.map(cancelled_dates), utc=True
    )
    assert (
        pd.to_datetime(cancelled_events.event_timestamp, utc=True)
        < event_cancellations
    ).all()


def test_failed_payments_raise_but_do_not_guarantee_churn():
    common_signals = {
        "engagement_level": "medium",
        "recent_event_count": 8,
        "days_since_last_activity": 10,
        "active_user_count": 3,
        "seat_utilization": 0.35,
        "report_created_count": 3,
        "integration_connected": True,
    }
    no_failures = calculate_cancellation_probability(
        **common_signals, failed_payment_count=0
    )
    one_failure = calculate_cancellation_probability(
        **common_signals, failed_payment_count=1
    )
    multiple_failures = calculate_cancellation_probability(
        **common_signals, failed_payment_count=3
    )

    assert no_failures < one_failure < multiple_failures < 1


def test_churned_accounts_show_aggregate_pre_cancellation_decline():
    datasets = generate_datasets(account_count=100, seed=42)
    subscriptions = datasets["subscriptions"]
    cancellation_dates = subscriptions.loc[
        subscriptions.subscription_status == "cancelled",
        ["account_id", "cancellation_date"],
    ].set_index("account_id").cancellation_date
    events = datasets["events"].copy()
    events = events[events.account_id.isin(cancellation_dates.index)]
    events["event_date"] = pd.to_datetime(events.event_timestamp, utc=True).dt.date
    events["cancellation_date"] = pd.to_datetime(
        events.account_id.map(cancellation_dates)
    ).dt.date
    events["days_before_cancellation"] = (
        events.cancellation_date - events.event_date
    ).map(lambda value: value.days)

    earlier_period = events.days_before_cancellation.between(29, 56).sum()
    final_period = events.days_before_cancellation.between(1, 28).sum()
    assert final_period < earlier_period
