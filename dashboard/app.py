"""Streamlit dashboard for the dbt-modeled SaaS product analytics data."""

from __future__ import annotations

from typing import Optional

import altair as alt
import pandas as pd
import streamlit as st

try:
    from dashboard.churn_api import (
        API_BASE_URL,
        ChurnAPIError,
        load_account_churn_risk,
        load_api_health,
        load_churn_summary,
        load_highest_risk_accounts,
    )
    from dashboard.data_loader import (
        DEFAULT_DATABASE_PATH,
        DashboardDataError,
        database_signature,
        load_dashboard_data,
        load_streaming_status,
        streaming_signature,
    )
    from dashboard.metrics import (
        activation_funnel,
        align_activity_periods,
        apply_account_filters,
        calculate_kpis,
        descriptive_insights,
        feature_adoption,
        filter_to_accounts,
        monthly_active_accounts,
        weekly_active_accounts,
    )
except ModuleNotFoundError as exc:
    # `streamlit run dashboard/app.py` adds dashboard/ rather than the project
    # root to sys.path. Keep that documented command and package-based tests
    # both working without changing the user's launch workflow.
    if exc.name != "dashboard":
        raise
    from churn_api import (
        API_BASE_URL,
        ChurnAPIError,
        load_account_churn_risk,
        load_api_health,
        load_churn_summary,
        load_highest_risk_accounts,
    )
    from data_loader import (
        DEFAULT_DATABASE_PATH,
        DashboardDataError,
        database_signature,
        load_dashboard_data,
        load_streaming_status,
        streaming_signature,
    )
    from metrics import (
        activation_funnel,
        align_activity_periods,
        apply_account_filters,
        calculate_kpis,
        descriptive_insights,
        feature_adoption,
        filter_to_accounts,
        monthly_active_accounts,
        weekly_active_accounts,
    )


st.set_page_config(
    page_title="SaaS Product Analytics",
    page_icon="📊",
    layout="wide",
)


def format_days(value: Optional[float]) -> str:
    """Format a median day value without unnecessary decimal places."""

    if value is None:
        return "N/A"
    if float(value).is_integer():
        return f"{int(value)} days"
    return f"{value:.1f} days"


def render_kpis(kpis: dict) -> None:
    """Render the six executive metrics in two readable rows."""

    first_row = st.columns(3)
    first_row[0].metric("Total Accounts", f"{kpis['total_accounts']:,}")
    first_row[1].metric("Activated Accounts", f"{kpis['activated_accounts']:,}")
    first_row[2].metric("Activation Rate", f"{kpis['activation_rate']:.0%}")

    second_row = st.columns(3)
    second_row[0].metric(
        "Median Time to Activation",
        format_days(kpis["median_days_to_activation"]),
    )
    second_row[1].metric(
        "Trial Conversion Rate",
        f"{kpis['trial_conversion_rate']:.0%}",
    )
    second_row[2].metric(
        "Monthly Active Accounts",
        f"{kpis['monthly_active_accounts']:,}",
    )

    latest_month = kpis["latest_observed_month"]
    if latest_month is not None:
        st.caption(
            "Monthly Active Accounts uses the latest observed calendar month: "
            f"{pd.Timestamp(latest_month).strftime('%B %Y')}."
        )


def format_freshness(seconds: Optional[float]) -> str:
    if seconds is None:
        return "No events yet"
    if seconds < 60:
        return f"{int(seconds)} seconds ago"
    if seconds < 3_600:
        minutes = max(1, int(seconds // 60))
        unit = "minute" if minutes == 1 else "minutes"
        return f"{minutes} {unit} ago"
    return f"{seconds / 3_600:.1f} hours ago"


def streaming_health_status(seconds: Optional[float]) -> str:
    if seconds is None:
        return "No data"
    return "Healthy" if seconds <= 300 else "Stale"


def render_streaming_status(status: dict) -> None:
    """Render the intentionally small Level 8 freshness addition."""

    st.subheader("Streaming Status")
    streaming_columns = st.columns(4)
    streaming_columns[0].metric(
        "Total Streamed Events", f"{status['events_received']:,}"
    )
    latest = status["latest_event_timestamp"]
    latest_display = (
        "No streamed events"
        if latest is None
        else pd.Timestamp(latest).strftime("%Y-%m-%d %H:%M:%S %Z")
    )
    streaming_columns[1].metric("Latest Streamed Event", latest_display)
    streaming_columns[2].metric(
        "Freshness", format_freshness(status["seconds_since_last_event"])
    )
    streaming_columns[3].metric(
        "Status", streaming_health_status(status["seconds_since_last_event"])
    )
    st.caption(
        "Raw Kafka consumer output. Local development freshness target: under "
        "five minutes; this is not a production SLA."
    )


def render_rate_trend(
    frame: pd.DataFrame,
    rate_column: str,
    label: str,
    color: str,
) -> None:
    """Render a monthly percentage trend with a readable percent axis."""

    trend = frame[["month", rate_column]].copy()
    trend["percentage"] = trend[rate_column] * 100
    st.line_chart(
        trend,
        x="month",
        y="percentage",
        x_label="Month",
        y_label=label,
        color=color,
        height=300,
    )


def render_retention_and_churn(data: dict[str, pd.DataFrame]) -> None:
    """Render the Level 5 cohort, churn, revenue, and behavior views."""

    st.header("Retention & Churn")
    st.caption(
        "Observed retention and revenue movements from the Level 5 dbt marts. "
        "These views describe associations; they do not make causal or "
        "predictive claims."
    )

    st.subheader("Weekly Retention Cohorts")
    cohorts = data["retention_cohorts"].copy()
    if cohorts.empty:
        st.info("No cohort retention data is available.")
    else:
        cohorts["cohort"] = pd.to_datetime(cohorts["cohort_week"]).dt.strftime(
            "%Y-%m-%d"
        )
        heatmap = (
            alt.Chart(cohorts)
            .mark_rect(stroke="white", strokeWidth=0.5)
            .encode(
                x=alt.X(
                    "weeks_since_start:O",
                    title="Weeks since signup",
                    sort="ascending",
                ),
                y=alt.Y("cohort:N", title="Signup cohort", sort="ascending"),
                color=alt.Color(
                    "retention_rate:Q",
                    title="Retention",
                    scale=alt.Scale(domain=[0, 1], scheme="blues"),
                    legend=alt.Legend(format=".0%"),
                ),
                tooltip=[
                    alt.Tooltip("cohort:N", title="Cohort"),
                    alt.Tooltip(
                        "weeks_since_start:O", title="Weeks since signup"
                    ),
                    alt.Tooltip("cohort_size:Q", title="Cohort size"),
                    alt.Tooltip(
                        "retained_accounts:Q", title="Retained accounts"
                    ),
                    alt.Tooltip(
                        "retention_rate:Q", title="Retention", format=".1%"
                    ),
                ],
            )
            .properties(height=max(300, cohorts["cohort"].nunique() * 24))
        )
        st.altair_chart(heatmap, use_container_width=True)

    st.divider()
    logo_column, revenue_column = st.columns(2)
    with logo_column:
        st.subheader("Logo Churn")
        st.caption("Cancelled accounts divided by accounts active at month start.")
        render_rate_trend(
            data["logo_churn"], "logo_churn_rate", "Logo churn (%)", "#B45309"
        )
    with revenue_column:
        st.subheader("Revenue Churn")
        st.caption("MRR lost from cancellations divided by beginning MRR.")
        render_rate_trend(
            data["revenue_churn"],
            "revenue_churn_rate",
            "Revenue churn (%)",
            "#B91C1C",
        )

    st.subheader("Net Revenue Retention")
    st.caption(
        "Beginning MRR after churn and contraction, plus expansion; new-logo "
        "revenue is excluded."
    )
    render_rate_trend(
        data["revenue_retention"], "nrr", "Net revenue retention (%)", "#0F766E"
    )
    st.dataframe(
        data["revenue_retention"],
        hide_index=True,
        width="stretch",
        column_config={
            "month": st.column_config.DateColumn("Month", format="MMM YYYY"),
            "starting_mrr": st.column_config.NumberColumn(
                "Starting MRR", format="$%.0f"
            ),
            "churned_mrr": st.column_config.NumberColumn(
                "Churned MRR", format="$%.0f"
            ),
            "contraction_mrr": st.column_config.NumberColumn(
                "Contraction MRR", format="$%.0f"
            ),
            "expansion_mrr": st.column_config.NumberColumn(
                "Expansion MRR", format="$%.0f"
            ),
            "ending_mrr": st.column_config.NumberColumn(
                "Retained ending MRR", format="$%.0f"
            ),
            "nrr": st.column_config.ProgressColumn(
                "NRR", min_value=0.0, max_value=1.5, format="percent"
            ),
        },
    )

    st.divider()
    st.subheader("Retention by Customer Segment")
    segments = data["retention_segments"].copy()
    segments["retention_percentage"] = segments["retention_rate"] * 100
    plan_column, engagement_column = st.columns(2)
    with plan_column:
        st.markdown("**Plan**")
        plan_retention = segments.loc[segments.segment_type == "plan"]
        st.bar_chart(
            plan_retention,
            x="segment_value",
            y="retention_percentage",
            x_label="Plan",
            y_label="Observed retention (%)",
            color="#2563EB",
            height=300,
        )
    with engagement_column:
        st.markdown("**Engagement level**")
        engagement_retention = segments.loc[
            segments.segment_type == "engagement_level"
        ]
        st.bar_chart(
            engagement_retention,
            x="segment_value",
            y="retention_percentage",
            x_label="Engagement level",
            y_label="Observed retention (%)",
            color="#0F766E",
            height=300,
        )

    st.divider()
    st.subheader("Retained vs Churned Behavior")
    st.caption(
        "Average product behavior for currently active paid accounts versus "
        "cancelled paid accounts. Differences are descriptive associations."
    )
    behavior = data["retention_behavior"].copy()
    st.dataframe(
        behavior,
        hide_index=True,
        width="stretch",
        column_config={
            "retention_status": "Status",
            "total_accounts": "Accounts",
            "avg_total_events": st.column_config.NumberColumn(
                "Avg events", format="%.1f"
            ),
            "avg_active_users": st.column_config.NumberColumn(
                "Avg active users", format="%.1f"
            ),
            "avg_seat_utilization": st.column_config.NumberColumn(
                "Avg seat utilization", format="percent"
            ),
            "avg_reports_created": st.column_config.NumberColumn(
                "Avg reports created", format="%.1f"
            ),
            "avg_reports_exported": st.column_config.NumberColumn(
                "Avg reports exported", format="%.1f"
            ),
            "avg_integrations_connected": st.column_config.NumberColumn(
                "Avg integrations", format="%.2f"
            ),
            "avg_dashboards_viewed": st.column_config.NumberColumn(
                "Avg dashboard views", format="%.1f"
            ),
            "avg_days_since_last_activity": st.column_config.NumberColumn(
                "Avg days inactive", format="%.1f"
            ),
        },
    )

    if not segments.empty:
        insights = []
        plans = segments.loc[segments.segment_type == "plan"]
        engagement = segments.loc[segments.segment_type == "engagement_level"]
        if not plans.empty:
            best = plans.loc[plans.retention_rate.idxmax()]
            insights.append(
                f"{best.segment_value} had the highest observed plan retention "
                f"at {best.retention_rate:.1%}."
            )
        if not engagement.empty:
            best = engagement.loc[engagement.retention_rate.idxmax()]
            insights.append(
                f"{best.segment_value.title()}-engagement accounts had "
                f"{best.retention_rate:.1%} observed retention."
            )
        if not data["revenue_retention"].empty:
            latest = data["revenue_retention"].iloc[-1]
            insights.append(
                f"Latest-month NRR was {latest.nrr:.1%}, with "
                f"${latest.churned_mrr:,.0f} churned MRR."
            )
        st.subheader("Level 5 Observations")
        for insight in insights:
            st.markdown(f"- {insight}")


def render_churn_risk() -> None:
    """Render Level 6 scores exclusively through the Level 7 API."""

    st.title("Churn Risk")
    st.caption("Model-generated risk ranking for currently active paid accounts.")
    st.info(
        "Risk scores are used for ranking and are not claimed to be calibrated "
        "probabilities."
    )

    try:
        health = load_api_health()
        if health.get("status") != "ok":
            raise ChurnAPIError("Churn API returned an unhealthy status")
        summary = load_churn_summary()
        ranking = load_highest_risk_accounts(limit=10)
    except ChurnAPIError:
        st.sidebar.warning("Churn API: Unavailable")
        st.warning(
            "Churn API is unavailable. Start FastAPI with: "
            "`uvicorn api.main:app --reload`"
        )
        return

    st.sidebar.success("Churn API: Connected")
    st.sidebar.caption(f"Source: {API_BASE_URL}")

    st.header("Risk Overview")
    overview = st.columns(5)
    overview[0].metric("Scored Accounts", f"{summary['scored_accounts']:,}")
    overview[1].metric("High Risk", f"{summary['high_risk_accounts']:,}")
    overview[2].metric("Medium Risk", f"{summary['medium_risk_accounts']:,}")
    overview[3].metric("Low Risk", f"{summary['low_risk_accounts']:,}")
    overview[4].metric(
        "High-Risk MRR",
        f"${summary['high_risk_monthly_revenue']:,.0f}",
    )

    st.divider()
    st.header("Risk Distribution")
    distribution = pd.DataFrame(
        {
            "Risk": ["High", "Medium", "Low"],
            "Accounts": [
                summary["high_risk_accounts"],
                summary["medium_risk_accounts"],
                summary["low_risk_accounts"],
            ],
        }
    )
    st.bar_chart(
        distribution,
        x="Risk",
        y="Accounts",
        x_label="Risk level",
        y_label="Accounts",
        color="#B45309",
        sort=False,
        height=300,
    )

    st.divider()
    st.header("Highest-Risk Accounts")
    accounts = ranking.get("accounts", [])
    ranking_rows = [
        {
            "Account": account["account_id"],
            "Risk Score": account["churn_score"],
            "Risk Bucket": account["risk_bucket"],
            "Monthly Revenue": account["monthly_revenue"],
            "Top Reason": (
                account["top_reasons"][0] if account["top_reasons"] else ""
            ),
        }
        for account in accounts
    ]
    ranking_table = pd.DataFrame(ranking_rows)
    st.dataframe(
        ranking_table,
        hide_index=True,
        width="stretch",
        column_config={
            "Account": "Account",
            "Risk Score": st.column_config.NumberColumn(
                "Risk Score", min_value=0.0, max_value=1.0, format="%.3f"
            ),
            "Risk Bucket": "Risk",
            "Monthly Revenue": st.column_config.NumberColumn(
                "MRR", min_value=0.0, format="$%.0f"
            ),
            "Top Reason": "Main Reason",
        },
    )

    st.divider()
    st.header("Account Lookup")
    default_account = accounts[0]["account_id"] if accounts else ""
    account_id = st.text_input(
        "Account ID",
        value=default_account,
        placeholder="A040",
        help="Enter an account from the latest active paid-account scoring run.",
    )
    if account_id.strip():
        try:
            account = load_account_churn_risk(account_id)
        except ChurnAPIError as exc:
            if str(exc) == "Account not found":
                st.warning("Account not found in the latest churn scoring run.")
            else:
                st.warning(
                    "Churn API is unavailable. Start FastAPI with: "
                    "`uvicorn api.main:app --reload`"
                )
        else:
            st.subheader(f"Account {account['account_id']}")
            details = st.columns(4)
            details[0].metric("Risk Score", f"{account['churn_score']:.3f}")
            details[1].metric("Risk Level", account["risk_bucket"])
            details[2].metric(
                "Monthly Revenue", f"${account['monthly_revenue']:,.0f}"
            )
            details[3].metric("Prediction Date", account["prediction_date"])

            st.markdown("**Why is this account considered risky?**")
            reasons = account.get("top_reasons", [])
            if reasons:
                for reason in reasons:
                    st.markdown(f"- {reason}")
            else:
                st.caption("No individual descriptive risk signals are available.")


def main() -> None:
    """Load the dbt tables and render the dashboard."""

    st.sidebar.header("Navigation")
    selected_page = st.sidebar.radio(
        "Page",
        ["Product Analytics", "Retention & Churn", "Churn Risk"],
        label_visibility="collapsed",
    )

    if selected_page == "Churn Risk":
        render_churn_risk()
        return

    st.title("SaaS Product Analytics")

    try:
        database_path, database_mtime_ns = database_signature()
        data = load_dashboard_data(database_path, database_mtime_ns)
    except DashboardDataError as exc:
        st.error(str(exc))
        st.stop()

    if selected_page == "Retention & Churn":
        st.sidebar.caption(f"Source: {DEFAULT_DATABASE_PATH.name}")
        render_retention_and_churn(data)
        return

    st.caption(
        "Activation, adoption, and account activity from dbt models in DuckDB."
    )

    accounts = data["accounts"]

    st.sidebar.header("Filters")
    selected_plan = st.sidebar.selectbox(
        "Plan",
        ["All", "Starter", "Growth", "Enterprise"],
    )
    selected_engagement = st.sidebar.selectbox(
        "Engagement Level",
        ["All", "low", "medium", "high"],
    )
    selected_status = st.sidebar.selectbox(
        "Subscription Status",
        ["All", "trial", "active", "cancelled"],
    )

    filtered_accounts = apply_account_filters(
        accounts,
        plan=selected_plan,
        engagement_level=selected_engagement,
        subscription_status=selected_status,
    )
    selected_account_ids = filtered_accounts["account_id"]
    filters_active = any(
        value != "All"
        for value in [selected_plan, selected_engagement, selected_status]
    )

    st.sidebar.divider()
    st.sidebar.metric(
        "Accounts in view",
        f"{len(filtered_accounts):,}",
        help="All dashboard sections use this selected account cohort.",
    )
    st.sidebar.caption(f"Source: {DEFAULT_DATABASE_PATH.name}")

    filtered_subscriptions = filter_to_accounts(
        data["subscriptions"], selected_account_ids
    )
    filtered_activation = filter_to_accounts(
        data["activation"], selected_account_ids
    )
    filtered_events = filter_to_accounts(data["events"], selected_account_ids)
    filtered_activity = filter_to_accounts(
        data["account_activity"], selected_account_ids
    )

    all_weekly_activity = weekly_active_accounts(data["events"])
    all_monthly_activity = monthly_active_accounts(data["events"])
    filtered_weekly_activity = align_activity_periods(
        weekly_active_accounts(filtered_events),
        all_weekly_activity,
        "week_start",
    )
    filtered_monthly_activity = align_activity_periods(
        monthly_active_accounts(filtered_events),
        all_monthly_activity,
        "month_start",
    )
    latest_observed_month = (
        None
        if all_monthly_activity.empty
        else pd.Timestamp(all_monthly_activity.iloc[-1]["month_start"])
    )

    kpis = calculate_kpis(
        filtered_accounts,
        filtered_subscriptions,
        filtered_activation,
        filtered_monthly_activity,
        latest_observed_month,
    )

    st.header("Executive Overview")
    if filters_active:
        st.caption("All values below reflect the selected account filters.")
    render_kpis(kpis)

    try:
        stream_path, stream_file_count, stream_mtime_ns = streaming_signature()
        stream_status = load_streaming_status(
            stream_path, stream_file_count, stream_mtime_ns
        )
    except DashboardDataError as exc:
        st.warning(str(exc))
    else:
        render_streaming_status(stream_status)

    st.divider()
    st.header("Activation Funnel")
    st.caption(
        "Milestone stages show accounts that ever completed each action; "
        "Activated applies the dbt 14-day activation definition."
    )
    funnel = activation_funnel(
        filtered_accounts,
        filtered_activation,
        filtered_events,
    )
    funnel_chart_column, funnel_table_column = st.columns([2, 1])
    with funnel_chart_column:
        st.bar_chart(
            funnel,
            x="stage",
            y="account_count",
            x_label="Funnel stage",
            y_label="Accounts",
            color="#2563EB",
            horizontal=True,
            sort=False,
            height=300,
        )
    with funnel_table_column:
        st.dataframe(
            funnel[["stage", "account_count", "percentage"]],
            hide_index=True,
            width="stretch",
            column_config={
                "stage": "Stage",
                "account_count": st.column_config.NumberColumn(
                    "Accounts", format="%d"
                ),
                "percentage": st.column_config.ProgressColumn(
                    "%",
                    min_value=0.0,
                    max_value=1.0,
                    format="percent",
                ),
            },
        )

    st.divider()
    st.header("Feature Adoption")
    adoption = feature_adoption(
        filtered_events,
        len(filtered_accounts),
        precomputed_mart=(
            None if filters_active else data["feature_adoption"]
        ),
    )
    st.bar_chart(
        adoption,
        x="feature_name",
        y="adoption_percentage",
        x_label="Feature",
        y_label="Adoption rate (%)",
        color="#0F766E",
        sort=False,
        height=340,
    )
    st.dataframe(
        adoption[
            [
                "feature_name",
                "accounts_using_feature",
                "total_accounts",
                "adoption_rate",
            ]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "feature_name": "Feature",
            "accounts_using_feature": "Accounts using feature",
            "total_accounts": "Accounts in cohort",
            "adoption_rate": st.column_config.ProgressColumn(
                "Adoption rate",
                min_value=0.0,
                max_value=1.0,
                format="percent",
            ),
        },
    )

    st.divider()
    weekly_column, monthly_column = st.columns(2)
    with weekly_column:
        st.header("Weekly Active Accounts")
        st.caption("Unique selected accounts with at least one event per week.")
        st.line_chart(
            filtered_weekly_activity,
            x="week_start",
            y="active_accounts",
            x_label="Week",
            y_label="Active accounts",
            color="#2563EB",
            height=330,
        )
    with monthly_column:
        st.header("Monthly Active Accounts")
        st.caption("Unique selected accounts with at least one event per month.")
        st.bar_chart(
            filtered_monthly_activity,
            x="month_start",
            y="active_accounts",
            x_label="Month",
            y_label="Active accounts",
            color="#0F766E",
            height=330,
        )

    st.divider()
    st.header("Account Activity")
    st.caption(
        "Click a column header to sort. The default view shows the most active "
        "accounts first."
    )
    activity_table = filtered_activity.merge(
        filtered_accounts[
            ["account_id", "plan", "engagement_level", "subscription_status"]
        ],
        on="account_id",
        how="left",
        validate="one_to_one",
    )
    activity_table = activity_table[
        [
            "account_id",
            "plan",
            "engagement_level",
            "subscription_status",
            "total_events",
            "active_users",
            "first_event_at",
            "last_event_at",
            "report_created_count",
            "report_exported_count",
            "dashboard_viewed_count",
        ]
    ].sort_values(["total_events", "account_id"], ascending=[False, True])
    st.dataframe(
        activity_table,
        hide_index=True,
        width="stretch",
        height=450,
        column_config={
            "account_id": "Account",
            "plan": "Plan",
            "engagement_level": "Engagement",
            "subscription_status": "Subscription",
            "total_events": st.column_config.NumberColumn(
                "Total events", format="%d"
            ),
            "active_users": st.column_config.NumberColumn(
                "Active users", format="%d"
            ),
            "first_event_at": st.column_config.DatetimeColumn(
                "First event", format="YYYY-MM-DD HH:mm"
            ),
            "last_event_at": st.column_config.DatetimeColumn(
                "Last event", format="YYYY-MM-DD HH:mm"
            ),
            "report_created_count": "Reports created",
            "report_exported_count": "Reports exported",
            "dashboard_viewed_count": "Dashboard views",
        },
    )

    st.divider()
    st.header("Business Insights")
    for insight in descriptive_insights(kpis, adoption, filtered_monthly_activity):
        st.markdown(f"- {insight}")

    st.caption(
        "All metrics are calculated from materialized dbt models in "
        f"{DEFAULT_DATABASE_PATH}."
    )


if __name__ == "__main__":
    main()
