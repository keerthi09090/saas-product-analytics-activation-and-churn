"""Reusable cohort filters and product-analytics calculations."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import pandas as pd


FEATURE_NAMES = [
    "invite_sent",
    "integration_connected",
    "report_created",
    "report_exported",
    "dashboard_viewed",
]


def apply_account_filters(
    accounts: pd.DataFrame,
    plan: str = "All",
    engagement_level: str = "All",
    subscription_status: str = "All",
) -> pd.DataFrame:
    """Return the account cohort selected by the three sidebar filters."""

    filtered = accounts.copy()
    if plan != "All":
        filtered = filtered.loc[filtered["plan"] == plan]
    if engagement_level != "All":
        filtered = filtered.loc[
            filtered["engagement_level"] == engagement_level
        ]
    if subscription_status != "All":
        filtered = filtered.loc[
            filtered["subscription_status"] == subscription_status
        ]
    return filtered.reset_index(drop=True)


def filter_to_accounts(
    frame: pd.DataFrame,
    account_ids: Iterable[str],
) -> pd.DataFrame:
    """Restrict any account-grain or event-grain frame to one cohort."""

    selected_ids = set(account_ids)
    return frame.loc[frame["account_id"].isin(selected_ids)].copy()


def _safe_rate(numerator: int, denominator: int) -> float:
    """Return a proportion, using zero for an empty denominator."""

    return numerator / denominator if denominator else 0.0


def weekly_active_accounts(events: pd.DataFrame) -> pd.DataFrame:
    """Count distinct event-producing accounts in each Monday-starting week."""

    if events.empty:
        return pd.DataFrame(columns=["week_start", "active_accounts"])

    timestamps = pd.to_datetime(events["event_timestamp"], utc=True, errors="coerce")
    event_dates = timestamps.dt.tz_convert(None).dt.normalize()
    week_starts = event_dates - pd.to_timedelta(event_dates.dt.weekday, unit="D")

    activity = events[["account_id"]].copy()
    activity["week_start"] = week_starts
    return (
        activity.dropna(subset=["week_start"])
        .groupby("week_start", as_index=False)["account_id"]
        .nunique()
        .rename(columns={"account_id": "active_accounts"})
        .sort_values("week_start")
        .reset_index(drop=True)
    )


def monthly_active_accounts(events: pd.DataFrame) -> pd.DataFrame:
    """Count distinct event-producing accounts in each calendar month."""

    if events.empty:
        return pd.DataFrame(columns=["month_start", "active_accounts"])

    timestamps = pd.to_datetime(events["event_timestamp"], utc=True, errors="coerce")
    month_starts = timestamps.dt.tz_convert(None).dt.to_period("M").dt.to_timestamp()

    activity = events[["account_id"]].copy()
    activity["month_start"] = month_starts
    return (
        activity.dropna(subset=["month_start"])
        .groupby("month_start", as_index=False)["account_id"]
        .nunique()
        .rename(columns={"account_id": "active_accounts"})
        .sort_values("month_start")
        .reset_index(drop=True)
    )


def align_activity_periods(
    activity: pd.DataFrame,
    all_periods: pd.DataFrame,
    period_column: str,
) -> pd.DataFrame:
    """Keep a stable time axis under filters and fill unused periods with zero."""

    periods = all_periods[[period_column]].drop_duplicates()
    aligned = periods.merge(activity, on=period_column, how="left")
    aligned["active_accounts"] = (
        pd.to_numeric(aligned["active_accounts"], errors="coerce")
        .fillna(0)
        .astype(int)
    )
    return aligned.sort_values(period_column).reset_index(drop=True)


def calculate_kpis(
    accounts: pd.DataFrame,
    subscriptions: pd.DataFrame,
    activation: pd.DataFrame,
    monthly_activity: pd.DataFrame,
    latest_observed_month: Optional[pd.Timestamp],
) -> Dict[str, object]:
    """Calculate the six executive KPIs for the selected account cohort."""

    total_accounts = len(accounts)
    activated_accounts = int(
        activation["is_activated"].fillna(False).astype(bool).sum()
    )
    converted_accounts = int(subscriptions["subscription_start_date"].notna().sum())

    activated_days = activation.loc[
        activation["is_activated"].fillna(False), "days_to_activation"
    ].dropna()
    median_days = None if activated_days.empty else float(activated_days.median())

    monthly_active = 0
    if latest_observed_month is not None and not monthly_activity.empty:
        latest_row = monthly_activity.loc[
            monthly_activity["month_start"] == latest_observed_month
        ]
        if not latest_row.empty:
            monthly_active = int(latest_row.iloc[0]["active_accounts"])

    return {
        "total_accounts": total_accounts,
        "activated_accounts": activated_accounts,
        "activation_rate": _safe_rate(activated_accounts, total_accounts),
        "median_days_to_activation": median_days,
        "trial_conversion_rate": _safe_rate(converted_accounts, total_accounts),
        "monthly_active_accounts": monthly_active,
        "latest_observed_month": latest_observed_month,
    }


def activation_funnel(
    accounts: pd.DataFrame,
    activation: pd.DataFrame,
    events: pd.DataFrame,
) -> pd.DataFrame:
    """Build the ordered account-level onboarding funnel."""

    total_accounts = len(accounts)
    event_accounts = events.groupby("event_name")["account_id"].nunique()
    activated_accounts = int(
        activation["is_activated"].fillna(False).astype(bool).sum()
    )

    stages = [
        ("Trial Started", total_accounts),
        ("Workspace Created", int(event_accounts.get("workspace_created", 0))),
        ("Invite Sent", int(event_accounts.get("invite_sent", 0))),
        (
            "Integration Connected",
            int(event_accounts.get("integration_connected", 0)),
        ),
        ("Activated", activated_accounts),
    ]
    funnel = pd.DataFrame(stages, columns=["stage", "account_count"])
    funnel["percentage"] = funnel["account_count"].map(
        lambda count: _safe_rate(int(count), total_accounts)
    )
    funnel["percentage_display"] = funnel["percentage"].map(
        lambda value: f"{value:.0%}"
    )
    return funnel


def feature_adoption(
    events: pd.DataFrame,
    total_accounts: int,
    precomputed_mart: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Calculate adoption, or use the global dbt mart when no filter is active."""

    if precomputed_mart is not None:
        adoption = precomputed_mart.copy()
        adoption = adoption.set_index("feature_name").reindex(FEATURE_NAMES).reset_index()
    else:
        usage = (
            events.loc[events["event_name"].isin(FEATURE_NAMES)]
            .groupby("event_name")["account_id"]
            .nunique()
            .reindex(FEATURE_NAMES, fill_value=0)
        )
        adoption = pd.DataFrame(
            {
                "feature_name": FEATURE_NAMES,
                "accounts_using_feature": usage.astype(int).values,
                "total_accounts": total_accounts,
            }
        )
        adoption["adoption_rate"] = adoption["accounts_using_feature"].map(
            lambda count: _safe_rate(int(count), total_accounts)
        )

    adoption["accounts_using_feature"] = (
        adoption["accounts_using_feature"].fillna(0).astype(int)
    )
    adoption["total_accounts"] = adoption["total_accounts"].fillna(0).astype(int)
    adoption["adoption_rate"] = adoption["adoption_rate"].fillna(0.0).astype(float)
    adoption["adoption_percentage"] = adoption["adoption_rate"] * 100
    return adoption


def descriptive_insights(
    kpis: Dict[str, object],
    adoption: pd.DataFrame,
    monthly_activity: pd.DataFrame,
) -> List[str]:
    """Create factual, non-predictive observations from the visible cohort."""

    total_accounts = int(kpis["total_accounts"])
    if total_accounts == 0:
        return ["No accounts match the current filter selection."]

    insights = [
        f"{float(kpis['activation_rate']):.0%} of selected accounts reached activation."
    ]

    median_days = kpis["median_days_to_activation"]
    if median_days is not None:
        median_text = (
            str(int(median_days))
            if float(median_days).is_integer()
            else f"{float(median_days):.1f}"
        )
        insights.append(f"Median activation time is {median_text} days.")

    adoption_lookup = adoption.set_index("feature_name")["adoption_rate"]
    integration_rate = float(adoption_lookup.get("integration_connected", 0.0))
    report_rate = float(adoption_lookup.get("report_created", 0.0))
    if integration_rate < report_rate:
        insights.append(
            "Integration adoption "
            f"({integration_rate:.0%}) is lower than report creation adoption "
            f"({report_rate:.0%})."
        )
    elif integration_rate > report_rate:
        insights.append(
            "Integration adoption "
            f"({integration_rate:.0%}) is higher than report creation adoption "
            f"({report_rate:.0%})."
        )

    if len(monthly_activity) >= 2:
        previous = int(monthly_activity.iloc[-2]["active_accounts"])
        latest = int(monthly_activity.iloc[-1]["active_accounts"])
        difference = latest - previous
        if difference > 0:
            insights.append(
                f"Monthly active accounts increased by {difference} in the latest month."
            )
        elif difference < 0:
            insights.append(
                f"Monthly active accounts decreased by {abs(difference)} in the latest month."
            )
        else:
            insights.append("Monthly active accounts were unchanged in the latest month.")

    return insights[:4]
