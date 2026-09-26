"""Generate realistic, reproducible SaaS data with pandas.

Run from the project root with:

    python -m simulator.generate
"""

from __future__ import annotations

import argparse
import calendar
import math
import random
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pandas as pd


DEFAULT_SEED = 42
DEFAULT_ACCOUNT_COUNT = 100
SIMULATION_END = datetime(2025, 12, 31, 23, 59, tzinfo=timezone.utc)

PLANS = ["Starter", "Growth", "Enterprise"]
ACQUISITION_CHANNELS = ["Organic", "Google Ads", "LinkedIn", "Referral", "Partner"]
ENGAGEMENT_LEVELS = ["low", "medium", "high"]
ROLES = ["Admin", "Manager", "Analyst", "Member"]
EVENT_NAMES = [
    "workspace_created",
    "invite_sent",
    "integration_connected",
    "report_created",
    "report_exported",
    "dashboard_viewed",
    "user_login",
]

PLAN_SETTINGS = {
    "Starter": {
        "company_size": (5, 50),
        "seats": (2, 15),
        "monthly_price": 49,
        "max_users": 8,
    },
    "Growth": {
        "company_size": (30, 300),
        "seats": (12, 80),
        "monthly_price": 249,
        "max_users": 20,
    },
    "Enterprise": {
        "company_size": (200, 2_000),
        "seats": (80, 500),
        "monthly_price": 999,
        "max_users": 40,
    },
}

COMPANY_PREFIXES = [
    "Acme", "Bright", "Cedar", "Cloud", "Copper", "Evergreen", "Focal", "Golden",
    "Harbor", "Juniper", "Lumen", "Northstar", "Pioneer", "Summit", "Vertex", "Willow",
]
COMPANY_SUFFIXES = [
    "Analytics", "Commerce", "Health", "Labs", "Logistics", "Media", "Robotics",
    "Security", "Software", "Systems", "Works", "Networks",
]


def weighted_choice(rng: random.Random, values: list[str], weights: list[float]) -> str:
    """Return one deterministic weighted random choice."""

    return rng.choices(values, weights=weights, k=1)[0]


def iso_timestamp(value: datetime) -> str:
    """Store timestamps consistently in UTC ISO-8601 format."""

    return value.astimezone(timezone.utc).isoformat()


def add_calendar_months(value: date, months: int) -> date:
    """Move a date by whole billing months without accumulating day drift."""

    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def generate_accounts(rng: random.Random, account_count: int) -> pd.DataFrame:
    """Create companies whose size, plan, seats, and engagement agree."""

    low_count = round(account_count * 0.35)
    medium_count = round(account_count * 0.45)
    high_count = account_count - low_count - medium_count
    engagement_pool = (
        ["low"] * low_count
        + ["medium"] * medium_count
        + ["high"] * high_count
    )
    rng.shuffle(engagement_pool)

    rows = []
    for index in range(account_count):
        account_id = f"A{index + 1:03d}"
        plan = weighted_choice(rng, PLANS, [0.50, 0.35, 0.15])
        settings = PLAN_SETTINGS[plan]
        company_size = rng.randint(*settings["company_size"])

        seat_min, seat_max = settings["seats"]
        seat_max = min(seat_max, company_size)
        seat_min = min(seat_min, seat_max)
        seats_purchased = rng.randint(seat_min, seat_max)

        if plan == "Starter":
            channel_weights = [0.36, 0.28, 0.10, 0.20, 0.06]
        elif plan == "Growth":
            channel_weights = [0.25, 0.24, 0.18, 0.19, 0.14]
        else:
            channel_weights = [0.10, 0.08, 0.22, 0.15, 0.45]

        acquisition_channel = weighted_choice(
            rng, ACQUISITION_CHANNELS, channel_weights
        )
        engagement_level = engagement_pool[index]

        days_before_end = rng.randint(0, 170)
        trial_start = SIMULATION_END.date() - timedelta(days=days_before_end)
        account_created_at = datetime.combine(
            trial_start,
            time(hour=rng.randint(8, 16), minute=rng.randint(0, 59)),
            tzinfo=timezone.utc,
        )
        company_name = (
            f"{COMPANY_PREFIXES[index % len(COMPANY_PREFIXES)]} "
            f"{COMPANY_SUFFIXES[(index // len(COMPANY_PREFIXES)) % len(COMPANY_SUFFIXES)]} "
            f"{index // (len(COMPANY_PREFIXES) * len(COMPANY_SUFFIXES)) + 1}"
        )

        rows.append(
            {
                "account_id": account_id,
                "company_name": company_name,
                "company_size": company_size,
                "plan": plan,
                "seats_purchased": seats_purchased,
                "acquisition_channel": acquisition_channel,
                "trial_start_date": trial_start.isoformat(),
                "account_created_at": iso_timestamp(account_created_at),
                "engagement_level": engagement_level,
            }
        )

    return pd.DataFrame(rows)


def generate_subscriptions(
    rng: random.Random, accounts: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, datetime]]:
    """Create trials and paid conversions before later churn behavior is scored."""

    rows = []
    access_end_by_account: dict[str, datetime] = {}

    for index, account in accounts.iterrows():
        trial_start = date.fromisoformat(account["trial_start_date"])
        trial_end = trial_start + timedelta(days=14)

        if trial_end > SIMULATION_END.date():
            status = "trial"
            subscription_start = None
            cancellation_date = None
            access_end = SIMULATION_END
        else:
            # Conversion is not automatic. Engagement is the main driver, with
            # a small plan adjustment for larger customers receiving more help.
            conversion_probability = {
                "low": 0.43,
                "medium": 0.72,
                "high": 0.92,
            }[account["engagement_level"]]
            conversion_probability += {
                "Starter": -0.03,
                "Growth": 0.02,
                "Enterprise": 0.05,
            }[account["plan"]]
            converted = rng.random() < min(0.95, max(0.05, conversion_probability))

            if not converted:
                status = "trial"
                subscription_start = None
                cancellation_date = None
                access_end = datetime.combine(
                    trial_end, time(18, 0), tzinfo=timezone.utc
                )
                rows.append(
                    {
                        "subscription_id": f"S{index + 1:03d}",
                        "account_id": account["account_id"],
                        "plan": account["plan"],
                        "trial_start_date": trial_start.isoformat(),
                        "trial_end_date": trial_end.isoformat(),
                        "subscription_start_date": None,
                        "cancellation_date": None,
                        "subscription_status": status,
                        "monthly_price": PLAN_SETTINGS[account["plan"]]["monthly_price"],
                    }
                )
                access_end_by_account[account["account_id"]] = access_end
                continue

            subscription_start = trial_end
            status = "active"
            cancellation_date = None
            access_end = SIMULATION_END

        rows.append(
            {
                "subscription_id": f"S{index + 1:03d}",
                "account_id": account["account_id"],
                "plan": account["plan"],
                "trial_start_date": trial_start.isoformat(),
                "trial_end_date": trial_end.isoformat(),
                "subscription_start_date": (
                    subscription_start.isoformat() if subscription_start else None
                ),
                "cancellation_date": (
                    cancellation_date.isoformat() if cancellation_date else None
                ),
                "subscription_status": status,
                "monthly_price": PLAN_SETTINGS[account["plan"]]["monthly_price"],
            }
        )
        access_end_by_account[account["account_id"]] = access_end

    return pd.DataFrame(rows), access_end_by_account


def planned_user_count(rng: random.Random, account: pd.Series) -> int:
    """Choose provisioned users based on seats and behavioral engagement."""

    utilization = {"low": 0.18, "medium": 0.38, "high": 0.62}[
        account["engagement_level"]
    ]
    utilization *= rng.uniform(0.80, 1.20)
    estimated_users = max(1, round(account["seats_purchased"] * utilization))
    return min(
        estimated_users,
        account["seats_purchased"],
        PLAN_SETTINGS[account["plan"]]["max_users"],
    )


def daily_event_count(
    rng: random.Random,
    engagement_level: str,
    user_count: int,
    is_weekday: bool,
    is_onboarding: bool,
) -> int:
    """Return a small daily event count with clear weekday seasonality."""

    base_rate = {"low": 0.12, "medium": 0.55, "high": 1.35}[
        engagement_level
    ]
    user_multiplier = 1 + math.log1p(user_count) / 3
    weekday_multiplier = 1.0 if is_weekday else 0.18
    onboarding_multiplier = 1.25 if is_onboarding else 1.0
    expected = base_rate * user_multiplier * weekday_multiplier * onboarding_multiplier
    return min(7, int(expected) + int(rng.random() < expected % 1))


def generate_users_and_events(
    rng: random.Random,
    accounts: pd.DataFrame,
    access_end_by_account: dict[str, datetime],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create users and chronological product behavior for every company."""

    user_rows = []
    event_rows = []
    next_user_number = 1

    for _, account in accounts.iterrows():
        account_id = account["account_id"]
        account_created_at = pd.Timestamp(account["account_created_at"]).to_pydatetime()
        access_end = access_end_by_account[account_id]

        owner_id = f"U{next_user_number:05d}"
        next_user_number += 1
        account_users = [
            {
                "user_id": owner_id,
                "account_id": account_id,
                "role": "Admin",
                "created_at": iso_timestamp(account_created_at),
                "is_admin": True,
            }
        ]

        workspace_at = account_created_at + timedelta(minutes=rng.randint(20, 150))
        workspace_at = min(workspace_at, access_end)
        account_events = [
            {
                "account_id": account_id,
                "user_id": owner_id,
                "event_name": "workspace_created",
                "event_timestamp": workspace_at,
            }
        ]

        # A single onboarding propensity makes related setup actions correlated:
        # teams that invite colleagues are also more likely to add an integration.
        # The action thresholds still vary by engagement and plan below.
        onboarding_propensity = rng.random()
        invite_probability = {
            "low": 0.50,
            "medium": 0.86,
            "high": 0.97,
        }[account["engagement_level"]]
        invite_probability += {
            "Starter": -0.04,
            "Growth": 0.02,
            "Enterprise": 0.05,
        }[account["plan"]]
        will_invite = onboarding_propensity < min(
            0.99, max(0.05, invite_probability)
        )
        target_users = max(2, planned_user_count(rng, account)) if will_invite else 1
        target_users = min(target_users, account["seats_purchased"])
        available_invite_hours = int(
            max(0, (access_end - workspace_at).total_seconds() // 3600 - 2)
        )
        max_invite_hours = min(10 * 24, available_invite_hours)

        for _ in range(1, target_users):
            if max_invite_hours < 2:
                break
            invite_at = workspace_at + timedelta(hours=rng.randint(2, max_invite_hours))
            remaining_hours = int(
                max(1, (access_end - invite_at).total_seconds() // 3600)
            )
            accepted_after = rng.randint(1, min(36, remaining_hours))
            user_created_at = min(invite_at + timedelta(hours=accepted_after), access_end)
            role = weighted_choice(
                rng, ROLES, [0.12, 0.20, 0.35, 0.33]
            )
            user_id = f"U{next_user_number:05d}"
            next_user_number += 1

            account_events.append(
                {
                    "account_id": account_id,
                    "user_id": owner_id,
                    "event_name": "invite_sent",
                    "event_timestamp": invite_at,
                }
            )
            account_users.append(
                {
                    "user_id": user_id,
                    "account_id": account_id,
                    "role": role,
                    "created_at": iso_timestamp(user_created_at),
                    "is_admin": role == "Admin",
                }
            )

        # Engaged accounts are more likely to connect an integration during onboarding.
        integration_probability = {"low": 0.23, "medium": 0.50, "high": 0.80}[
            account["engagement_level"]
        ]
        integration_probability += {
            "Starter": -0.08,
            "Growth": 0.08,
            "Enterprise": 0.15,
        }[account["plan"]]
        integration_probability = min(0.95, max(0.05, integration_probability))
        if (
            onboarding_propensity < integration_probability
            and workspace_at + timedelta(hours=4) <= access_end
        ):
            integration_at = workspace_at + timedelta(
                hours=rng.randint(4, min(9 * 24, max(4, available_invite_hours)))
            )
            integration_at = min(integration_at, access_end)
            account_events.append(
                {
                    "account_id": account_id,
                    "user_id": owner_id,
                    "event_name": "integration_connected",
                    "event_timestamp": integration_at,
                }
            )

        report_probability = {"low": 0.36, "medium": 0.68, "high": 0.90}[
            account["engagement_level"]
        ]
        report_probability += {"Starter": -0.03, "Growth": 0.00, "Enterprise": 0.03}[
            account["plan"]
        ]
        will_create_reports = rng.random() < min(0.97, max(0.05, report_probability))

        export_probability = {"low": 0.35, "medium": 0.65, "high": 0.85}[
            account["engagement_level"]
        ]
        will_export_reports = will_create_reports and rng.random() < export_probability

        dashboard_probability = {"low": 0.58, "medium": 0.86, "high": 0.97}[
            account["engagement_level"]
        ]
        dashboard_probability += {"Starter": -0.03, "Growth": 0.01, "Enterprise": 0.03}[
            account["plan"]
        ]
        will_use_dashboard = rng.random() < min(0.99, max(0.05, dashboard_probability))

        reports_created_at: list[datetime] = []
        lifecycle_hours = int(max(0, (access_end - workspace_at).total_seconds() // 3600))

        # Add the first adopted feature event explicitly. Recurring activity below
        # can create more events, but it cannot make a non-adopter adopt by accident.
        if will_use_dashboard and lifecycle_hours >= 2:
            dashboard_at = workspace_at + timedelta(
                hours=rng.randint(2, min(48, lifecycle_hours))
            )
            account_events.append(
                {
                    "account_id": account_id,
                    "user_id": owner_id,
                    "event_name": "dashboard_viewed",
                    "event_timestamp": dashboard_at,
                }
            )

        if will_create_reports and lifecycle_hours >= 4:
            first_report_at = workspace_at + timedelta(
                hours=rng.randint(4, min(7 * 24, lifecycle_hours))
            )
            reports_created_at.append(first_report_at)
            account_events.append(
                {
                    "account_id": account_id,
                    "user_id": owner_id,
                    "event_name": "report_created",
                    "event_timestamp": first_report_at,
                }
            )
            remaining_hours = int(
                max(0, (access_end - first_report_at).total_seconds() // 3600)
            )
            if will_export_reports and remaining_hours >= 1:
                export_at = first_report_at + timedelta(
                    hours=rng.randint(1, min(72, remaining_hours))
                )
                account_events.append(
                    {
                        "account_id": account_id,
                        "user_id": owner_id,
                        "event_name": "report_exported",
                        "event_timestamp": export_at,
                    }
                )

        day = workspace_at.date()
        while day <= access_end.date():
            is_weekday = day.weekday() < 5
            is_onboarding = day <= workspace_at.date() + timedelta(days=14)
            count = daily_event_count(
                rng,
                account["engagement_level"],
                len(account_users),
                is_weekday,
                is_onboarding,
            )
            proposed_times = sorted(
                datetime.combine(
                    day,
                    time(hour=rng.randint(8, 18), minute=rng.randint(0, 59)),
                    tzinfo=timezone.utc,
                )
                for _ in range(count)
            )

            for event_at in proposed_times:
                if event_at <= workspace_at:
                    event_at = workspace_at + timedelta(minutes=1)
                if event_at > access_end:
                    continue

                eligible_users = [
                    user
                    for user in account_users
                    if pd.Timestamp(user["created_at"]) <= pd.Timestamp(event_at)
                ]
                available_reports = [
                    created_at for created_at in reports_created_at if created_at < event_at
                ]
                possible_events = ["user_login"]
                event_weights = [0.55]
                if will_use_dashboard:
                    possible_events.append("dashboard_viewed")
                    event_weights.append(0.30)
                if will_create_reports:
                    possible_events.append("report_created")
                    event_weights.append(0.12)
                if will_export_reports and available_reports:
                    possible_events.append("report_exported")
                    event_weights.append(0.08)
                event_name = weighted_choice(rng, possible_events, event_weights)
                allowed_roles = {"Admin", "Manager", "Analyst"}
                if event_name in {"report_created", "report_exported"}:
                    eligible_users = [
                        user for user in eligible_users if user["role"] in allowed_roles
                    ] or [account_users[0]]

                actor = rng.choice(eligible_users)
                if event_name == "report_created":
                    reports_created_at.append(event_at)
                account_events.append(
                    {
                        "account_id": account_id,
                        "user_id": actor["user_id"],
                        "event_name": event_name,
                        "event_timestamp": event_at,
                    }
                )
            day += timedelta(days=1)

        user_rows.extend(account_users)
        event_rows.extend(account_events)

    users = pd.DataFrame(user_rows).sort_values("user_id").reset_index(drop=True)
    events = pd.DataFrame(event_rows).sort_values(
        ["event_timestamp", "account_id", "event_name", "user_id"]
    ).reset_index(drop=True)
    events.insert(0, "event_id", [f"E{index + 1:07d}" for index in range(len(events))])
    events["event_version"] = events.event_timestamp.map(
        lambda value: 1 if value.date() < date(2025, 10, 1) else 2
    )
    events["event_timestamp"] = events.event_timestamp.map(iso_timestamp)
    return users, events


def generate_invoices(
    rng: random.Random,
    accounts: pd.DataFrame,
    subscriptions: pd.DataFrame,
    access_end_by_account: dict[str, datetime],
) -> pd.DataFrame:
    """Generate calendar-aligned monthly plan and billing history."""

    engagement_by_account = accounts.set_index("account_id").engagement_level
    rows = []
    invoice_number = 1

    for _, subscription in subscriptions.iterrows():
        if subscription["subscription_status"] == "trial":
            continue

        account_id = subscription["account_id"]
        subscription_id = subscription["subscription_id"]
        subscription_start = date.fromisoformat(
            subscription["subscription_start_date"]
        )
        cancellation_date = (
            date.fromisoformat(subscription["cancellation_date"])
            if pd.notna(subscription["cancellation_date"])
            else None
        )
        engagement = engagement_by_account.loc[account_id]
        failure_probability = {"low": 0.08, "medium": 0.04, "high": 0.02}[engagement]
        current_plan = subscription["plan"]
        current_plan_index = PLANS.index(current_plan)
        billing_cycle = 0

        while True:
            billing_period_start = add_calendar_months(
                subscription_start, billing_cycle
            )
            if billing_period_start > SIMULATION_END.date():
                break
            if cancellation_date and billing_period_start >= cancellation_date:
                break

            # Re-evaluate the plan at each renewal. Engagement makes upgrades
            # more likely and low engagement makes contraction more likely;
            # transitions are limited to one adjacent tier per month.
            if billing_cycle > 0:
                upgrade_probability = {
                    "low": 0.005,
                    "medium": 0.025,
                    "high": 0.10,
                }[engagement]
                downgrade_probability = {
                    "low": 0.10,
                    "medium": 0.02,
                    "high": 0.005,
                }[engagement]
                movement_draw = rng.random()
                if (
                    movement_draw < upgrade_probability
                    and current_plan_index < len(PLANS) - 1
                ):
                    current_plan_index += 1
                elif (
                    movement_draw < upgrade_probability + downgrade_probability
                    and current_plan_index > 0
                ):
                    current_plan_index -= 1
                current_plan = PLANS[current_plan_index]

            next_period_start = add_calendar_months(
                subscription_start, billing_cycle + 1
            )
            billing_period_end = next_period_start - timedelta(days=1)
            if cancellation_date:
                billing_period_end = min(
                    billing_period_end, cancellation_date - timedelta(days=1)
                )

            if (SIMULATION_END.date() - billing_period_start).days <= 4:
                payment_status = "pending"
            else:
                payment_status = "failed" if rng.random() < failure_probability else "paid"
            rows.append(
                {
                    "invoice_id": f"I{invoice_number:05d}",
                    "account_id": account_id,
                    "subscription_id": subscription_id,
                    "invoice_date": billing_period_start.isoformat(),
                    "billing_period_start": billing_period_start.isoformat(),
                    "billing_period_end": billing_period_end.isoformat(),
                    "plan": current_plan,
                    "amount": PLAN_SETTINGS[current_plan]["monthly_price"],
                    "payment_status": payment_status,
                }
            )
            invoice_number += 1
            billing_cycle += 1

    return pd.DataFrame(
        rows,
        columns=[
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
    )


def calculate_cancellation_probability(
    engagement_level: str,
    recent_event_count: int,
    days_since_last_activity: int,
    active_user_count: int,
    seat_utilization: float,
    report_created_count: int,
    integration_connected: bool,
    failed_payment_count: int,
) -> float:
    """Estimate cancellation risk from observable product and billing behavior.

    Engagement supplies the starting probability. Small, additive adjustments
    then make the outcome respond to recent usage, adoption, utilization, and
    payment trouble without making any single signal deterministic.
    """

    probability = {"low": 0.30, "medium": 0.15, "high": 0.065}[
        engagement_level
    ]

    if recent_event_count < 4:
        probability += 0.05
    elif recent_event_count >= 20:
        probability -= 0.035

    if days_since_last_activity > 30:
        probability += 0.055
    elif days_since_last_activity > 14:
        probability += 0.025
    elif days_since_last_activity <= 7:
        probability -= 0.02

    if seat_utilization < 0.15:
        probability += 0.06
    elif seat_utilization < 0.30:
        probability += 0.015
    elif seat_utilization >= 0.55:
        probability -= 0.035

    if active_user_count <= 1:
        probability += 0.04
    elif active_user_count >= 5:
        probability -= 0.025

    if report_created_count == 0:
        probability += 0.035
    elif report_created_count >= 8:
        probability -= 0.025

    probability += -0.02 if integration_connected else 0.035
    probability += min(failed_payment_count, 2) * 0.055
    return min(0.65, max(0.05, probability))


def apply_churn_outcomes(
    rng: random.Random,
    accounts: pd.DataFrame,
    subscriptions: pd.DataFrame,
    invoices: pd.DataFrame,
    events: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Choose churn from actual behavior, then stop billing and taper activity."""

    subscriptions = subscriptions.copy()
    invoices = invoices.copy()
    events = events.copy()
    event_times = pd.to_datetime(events.event_timestamp, utc=True)
    simulation_end = pd.Timestamp(SIMULATION_END)
    account_details = accounts.set_index("account_id")
    cancellation_by_account: dict[str, date] = {}
    paid_account_ids = subscriptions.loc[
        subscriptions.subscription_status == "active", "account_id"
    ]
    decision_draws = {account_id: rng.random() for account_id in paid_account_ids}

    for row_index, subscription in subscriptions.iterrows():
        if subscription["subscription_status"] != "active":
            continue

        account_id = subscription["account_id"]
        subscription_start = date.fromisoformat(
            subscription["subscription_start_date"]
        )
        account_invoices = invoices[invoices.account_id == account_id].sort_values(
            "billing_period_start"
        )
        renewal_dates = [
            date.fromisoformat(value)
            for value in account_invoices.billing_period_start.iloc[1:]
        ]
        if not renewal_dates:
            # A newly converted account has not yet had a realistic opportunity
            # to cancel after spending time as a paying customer.
            continue

        account_events = events[events.account_id == account_id]
        account_event_times = event_times.loc[account_events.index]
        recent_cutoff = simulation_end - pd.Timedelta(days=30)
        recent_events = account_events[account_event_times >= recent_cutoff]
        last_event_at = account_event_times.max()
        days_since_last_activity = max(
            0, (simulation_end.date() - last_event_at.date()).days
        )
        active_users = recent_events.user_id.nunique()
        seats = int(account_details.loc[account_id, "seats_purchased"])
        seat_utilization = active_users / seats if seats else 0.0
        failed_payments = account_invoices[
            account_invoices.payment_status == "failed"
        ]

        cancellation_probability = calculate_cancellation_probability(
            engagement_level=account_details.loc[account_id, "engagement_level"],
            recent_event_count=len(recent_events),
            days_since_last_activity=days_since_last_activity,
            active_user_count=active_users,
            seat_utilization=seat_utilization,
            report_created_count=(
                account_events.event_name == "report_created"
            ).sum(),
            integration_connected=(
                account_events.event_name == "integration_connected"
            ).any(),
            failed_payment_count=len(failed_payments),
        )
        if decision_draws[account_id] >= cancellation_probability:
            continue

        # When payment trouble is present, cancellation can only follow a failed
        # invoice. It remains probabilistic: many failed-payment accounts retain.
        eligible_renewals = renewal_dates
        if not failed_payments.empty:
            first_failure = date.fromisoformat(
                failed_payments.iloc[0].billing_period_start
            )
            after_failure = [value for value in renewal_dates if value > first_failure]
            if after_failure:
                eligible_renewals = after_failure

        # Slightly favor later renewals so a churned account has a visible paid
        # history and enough time for its activity to decline gradually.
        cancellation_date = rng.choices(
            eligible_renewals,
            weights=range(1, len(eligible_renewals) + 1),
            k=1,
        )[0]
        assert cancellation_date > subscription_start
        cancellation_by_account[account_id] = cancellation_date
        subscriptions.at[row_index, "subscription_status"] = "cancelled"
        subscriptions.at[row_index, "cancellation_date"] = cancellation_date.isoformat()

    if not cancellation_by_account:
        return subscriptions, invoices, events

    cancellation_series = invoices.account_id.map(cancellation_by_account)
    invoice_starts = pd.to_datetime(invoices.billing_period_start).dt.date
    keep_invoice = cancellation_series.isna() | (invoice_starts < cancellation_series)
    invoices = invoices.loc[keep_invoice].copy().reset_index(drop=True)
    invoices["invoice_id"] = [f"I{index + 1:05d}" for index in range(len(invoices))]

    # Product usage fades during the eight weeks before cancellation. Setup
    # events remain as historical facts; recurring activity is progressively
    # less likely to survive as the cancellation date approaches.
    recurring_events = {
        "user_login",
        "dashboard_viewed",
        "report_created",
        "report_exported",
    }
    keep_event = []
    for row in events.itertuples():
        cancellation_date = cancellation_by_account.get(row.account_id)
        if cancellation_date is None:
            keep_event.append(True)
            continue

        event_at = pd.Timestamp(row.event_timestamp).date()
        if event_at >= cancellation_date:
            keep_event.append(False)
            continue
        days_before_cancellation = (cancellation_date - event_at).days
        if row.event_name not in recurring_events or days_before_cancellation > 56:
            keep_event.append(True)
            continue

        keep_probability = 0.12 + 0.88 * (days_before_cancellation / 56)
        keep_event.append(rng.random() < keep_probability)

    events = events.loc[keep_event].copy()
    events["_event_time"] = pd.to_datetime(events.event_timestamp, utc=True)
    events = events.sort_values(
        ["_event_time", "account_id", "event_name", "user_id"]
    ).drop(columns="_event_time").reset_index(drop=True)
    report_seen: set[str] = set()
    valid_report_history = []
    for row in events.itertuples():
        if row.event_name == "report_created":
            report_seen.add(row.account_id)
        valid_report_history.append(
            row.event_name != "report_exported" or row.account_id in report_seen
        )
    events = events.loc[valid_report_history].reset_index(drop=True)
    events["event_id"] = [f"E{index + 1:07d}" for index in range(len(events))]
    return subscriptions, invoices, events


def generate_datasets(
    account_count: int = DEFAULT_ACCOUNT_COUNT,
    seed: int = DEFAULT_SEED,
) -> dict[str, pd.DataFrame]:
    """Generate all five tables in memory using reproducible random streams."""

    accounts = generate_accounts(random.Random(seed), account_count)
    subscriptions, access_end_by_account = generate_subscriptions(
        random.Random(seed + 101), accounts
    )
    users, events = generate_users_and_events(
        random.Random(seed + 202), accounts, access_end_by_account
    )
    invoices = generate_invoices(
        random.Random(seed + 303), accounts, subscriptions, access_end_by_account
    )
    subscriptions, invoices, events = apply_churn_outcomes(
        random.Random(seed + 404),
        accounts,
        subscriptions,
        invoices,
        events,
    )

    # Accounts and subscriptions are current-state snapshots; invoices retain
    # the historical plan on every service month.
    if not invoices.empty:
        latest_billing = (
            invoices.sort_values(["billing_period_start", "invoice_id"])
            .groupby("account_id", as_index=False)
            .tail(1)
            .set_index("account_id")
        )
        current_plan_by_account = latest_billing["plan"]
        accounts["plan"] = accounts["account_id"].map(
            current_plan_by_account
        ).fillna(accounts["plan"])
        subscriptions["plan"] = subscriptions["account_id"].map(
            current_plan_by_account
        ).fillna(subscriptions["plan"])
        subscriptions["monthly_price"] = subscriptions["plan"].map(
            lambda plan: PLAN_SETTINGS[plan]["monthly_price"]
        )
    datasets = {
        "accounts": accounts,
        "users": users,
        "subscriptions": subscriptions,
        "invoices": invoices,
        "events": events,
    }
    validate_datasets(datasets)
    return datasets


def validate_datasets(datasets: dict[str, pd.DataFrame]) -> None:
    """Raise a clear error if a relationship or chronology rule is broken."""

    accounts = datasets["accounts"]
    users = datasets["users"]
    subscriptions = datasets["subscriptions"]
    invoices = datasets["invoices"]
    events = datasets["events"]

    assert accounts.account_id.is_unique, "Account IDs must be unique"
    assert users.user_id.is_unique, "User IDs must be unique"
    assert subscriptions.subscription_id.is_unique, "Subscription IDs must be unique"
    assert invoices.invoice_id.is_unique, "Invoice IDs must be unique"
    valid_accounts = set(accounts.account_id)
    valid_users = set(users.user_id)
    assert set(users.account_id) <= valid_accounts, "A user references an unknown account"
    assert set(subscriptions.account_id) <= valid_accounts, "A subscription references an unknown account"
    assert set(invoices.account_id) <= valid_accounts, "An invoice references an unknown account"
    assert set(events.account_id) <= valid_accounts, "An event references an unknown account"
    assert set(events.user_id) <= valid_users, "An event references an unknown user"
    assert (accounts.seats_purchased >= 0).all(), "Seats cannot be negative"
    assert (invoices.amount >= 0).all(), "Invoice amounts cannot be negative"

    cancellation_dates = pd.to_datetime(
        subscriptions.cancellation_date, errors="coerce"
    )
    subscription_starts = pd.to_datetime(
        subscriptions.subscription_start_date, errors="coerce"
    )
    is_cancelled = subscriptions.subscription_status == "cancelled"
    assert cancellation_dates.notna().equals(
        is_cancelled
    ), "Only cancelled subscriptions must have a cancellation date"
    assert (
        cancellation_dates[is_cancelled] > subscription_starts[is_cancelled]
    ).all(), "Cancellation must follow paid subscription start"

    event_users = events.merge(
        users[["user_id", "account_id", "created_at"]],
        on="user_id",
        suffixes=("_event", "_user"),
    )
    assert (
        event_users.account_id_event == event_users.account_id_user
    ).all(), "An event user belongs to a different account"
    assert (
        pd.to_datetime(event_users.event_timestamp, utc=True)
        >= pd.to_datetime(event_users.created_at, utc=True)
    ).all(), "An event occurs before its user was created"

    event_times = events.assign(
        parsed_time=pd.to_datetime(events.event_timestamp, utc=True)
    )
    workspace_times = (
        event_times[event_times.event_name == "workspace_created"]
        .set_index("account_id")
        .parsed_time
    )
    assert workspace_times.index.is_unique, "Each account must have one workspace"
    non_workspace = event_times[event_times.event_name != "workspace_created"].copy()
    after_workspace = (
        non_workspace.parsed_time
        > non_workspace.account_id.map(workspace_times)
    )
    assert after_workspace.mean() >= 0.95, "Most activity must follow workspace creation"

    for account_id, history in event_times.groupby("account_id"):
        created = history[history.event_name == "report_created"].parsed_time
        exported = history[history.event_name == "report_exported"].parsed_time
        if not exported.empty:
            assert not created.empty, f"{account_id} exported without creating a report"
            assert created.min() < exported.min(), f"{account_id} exported before report creation"

    user_counts = users.groupby("account_id").size()
    seats = accounts.set_index("account_id").seats_purchased
    assert (user_counts <= seats.reindex(user_counts.index)).all(), "Users exceed purchased seats"

    converted_accounts = set(
        subscriptions.loc[
            subscriptions.subscription_status.isin(["active", "cancelled"]),
            "account_id",
        ]
    )
    assert set(invoices.account_id) <= converted_accounts, "Trial accounts cannot have invoices"

    if not invoices.empty:
        invoice_subscriptions = invoices.merge(
            subscriptions[
                ["subscription_id", "account_id", "cancellation_date"]
            ],
            on="subscription_id",
            suffixes=("_invoice", "_subscription"),
        )
        assert len(invoice_subscriptions) == len(
            invoices
        ), "An invoice references an unknown subscription"
        assert (
            invoice_subscriptions.account_id_invoice
            == invoice_subscriptions.account_id_subscription
        ).all(), "An invoice belongs to the wrong account"

        invoice_dates = pd.to_datetime(invoices.invoice_date)
        period_starts = pd.to_datetime(invoices.billing_period_start)
        period_ends = pd.to_datetime(invoices.billing_period_end)
        assert invoice_dates.equals(
            period_starts
        ), "Invoice date must equal billing period start"
        assert (period_ends >= period_starts).all(), "Billing periods cannot be negative"
        expected_amounts = invoices.plan.map(
            lambda plan: PLAN_SETTINGS[plan]["monthly_price"]
        )
        assert invoices.amount.equals(
            expected_amounts
        ), "Invoice amount must match its historical plan"

        for subscription_id, history in invoices.groupby(
            "subscription_id", sort=False
        ):
            history = history.sort_values("billing_period_start")
            starts = pd.to_datetime(history.billing_period_start).reset_index(
                drop=True
            )
            ends = pd.to_datetime(history.billing_period_end).reset_index(drop=True)
            if len(history) > 1:
                assert (
                    starts.iloc[1:].reset_index(drop=True)
                    == ends.iloc[:-1].reset_index(drop=True) + pd.Timedelta(days=1)
                ).all(), f"{subscription_id} has a billing-period gap"
                plan_positions = history.plan.map(PLANS.index).to_numpy()
                assert (
                    abs(plan_positions[1:] - plan_positions[:-1]) <= 1
                ).all(), f"{subscription_id} skipped a plan tier"

            cancellation_value = subscriptions.loc[
                subscriptions.subscription_id == subscription_id,
                "cancellation_date",
            ].iloc[0]
            if pd.notna(cancellation_value):
                assert ends.max() < pd.Timestamp(
                    cancellation_value
                ), f"{subscription_id} bills on or after cancellation"

        latest_invoices = (
            invoices.sort_values(["billing_period_start", "invoice_id"])
            .groupby("account_id", as_index=False)
            .tail(1)
            .set_index("account_id")
        )
        account_plans = accounts.set_index("account_id").plan
        subscription_plans = subscriptions.set_index("account_id").plan
        assert latest_invoices.plan.equals(
            account_plans.reindex(latest_invoices.index)
        ), "Account plan must match its latest billed plan"
        assert latest_invoices.plan.equals(
            subscription_plans.reindex(latest_invoices.index)
        ), "Subscription plan must match its latest billed plan"

    cancelled = subscriptions.loc[
        is_cancelled, ["account_id", "cancellation_date"]
    ].set_index("account_id")
    if not cancelled.empty:
        cancellation_by_event = events.loc[
            events.account_id.isin(cancelled.index)
        ].copy()
        event_cancellations = cancellation_by_event.account_id.map(
            pd.to_datetime(cancelled.cancellation_date)
        )
        assert (
            pd.to_datetime(cancellation_by_event.event_timestamp, utc=True)
            < event_cancellations.dt.tz_localize("UTC")
        ).all(), "Product activity cannot occur on or after cancellation"


def save_datasets(datasets: dict[str, pd.DataFrame], output_dir: Path) -> None:
    """Write the five dataframes as Parquet files."""

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, dataframe in datasets.items():
        dataframe.to_parquet(output_dir / f"{name}.parquet", index=False)


def print_distribution(title: str, values: pd.Series, order: list[str]) -> None:
    print(f"\n{title}:")
    counts = values.value_counts().reindex(order, fill_value=0)
    for label, count in counts.items():
        print(f"{label}: {count:,}")


def print_summary(datasets: dict[str, pd.DataFrame]) -> None:
    """Print an easy-to-read generation report."""

    print("\nSynthetic SaaS Dataset Generated\n")
    print(f"Accounts: {len(datasets['accounts']):,}")
    print(f"Users: {len(datasets['users']):,}")
    print(f"Subscriptions: {len(datasets['subscriptions']):,}")
    print(f"Invoices: {len(datasets['invoices']):,}")
    print(f"Events: {len(datasets['events']):,}")
    print_distribution("Plan distribution", datasets["accounts"].plan, PLANS)
    print_distribution(
        "Engagement distribution",
        datasets["accounts"].engagement_level,
        ENGAGEMENT_LEVELS,
    )
    print_distribution("Event distribution", datasets["events"].event_name, EVENT_NAMES)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic SaaS data")
    parser.add_argument("--accounts", type=int, default=DEFAULT_ACCOUNT_COUNT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, default=Path("data"))
    args = parser.parse_args()

    datasets = generate_datasets(account_count=args.accounts, seed=args.seed)
    save_datasets(datasets, args.output)
    print_summary(datasets)


if __name__ == "__main__":
    main()
