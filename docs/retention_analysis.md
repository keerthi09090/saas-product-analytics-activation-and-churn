# Retention Analysis: What Product Behaviors Are Associated with Retention?

## Scope

This memo analyzes the deterministic seed-42 synthetic dataset through the dbt
retention and revenue marts. It compares 48 currently active paid accounts with
8 paid accounts that cancelled.

The findings are **observational associations from synthetic data**. The
generator deliberately makes engagement, payment history, and usage influence
cancellation, so these patterns partly recover its design. They are not causal
claims and should not be treated as evidence that forcing one behavior will
prevent churn.

## Summary

Retained accounts are broader and more frequent product users in this sample.
They generate more events, involve more users, use more of their purchased
seats, create more reports, and connect integrations more often than churned
accounts. Low-engagement accounts have the weakest observed retention.

These signals are useful for deciding what a retention analyst should inspect:
recent activity, active-user breadth, seat utilization, reporting behavior,
integration status, and payment history.

## Retained vs Churned Behavior

| Behavior | Retained | Churned | Observed difference |
|---|---:|---:|---:|
| Average total events | 104.8 | 31.4 | 3.3× higher for retained |
| Average active users | 13.2 | 3.8 | 3.5× higher for retained |
| Average seat utilization | 32.3% | 19.6% | +12.7 percentage points |
| Average reports created | 9.3 | 3.1 | 3.0× higher for retained |
| Average reports exported | 3.0 | 0.9 | 3.4× higher for retained |
| Average integrations connected | 0.54 | 0.25 | 2.2× higher for retained |
| Average dashboard views | 27.1 | 8.6 | 3.1× higher for retained |

### Active usage

The largest separation is overall product depth: retained accounts average
104.8 events and 13.2 active users, compared with 31.4 events and 3.8 active
users for churned accounts. This suggests reviewing both frequency and breadth;
one active champion may not represent healthy account adoption.

### Reporting workflow

Retained accounts create and export materially more reports. In this synthetic
product, report creation is a deeper workflow than a login or dashboard view,
so the difference indicates that retained accounts reach recurring value more
often.

### Integrations

Retained accounts average 0.54 integration connections versus 0.25 for churned
accounts. Integration use is not necessary for every account, but absence of an
integration combined with low activity or few active users is a useful review
signal.

### Seat utilization

Retained accounts use 32.3% of purchased seats on average versus 19.6% for
churned accounts. Low utilization can mean rollout friction, over-purchasing, or
value concentrated in too few users. The metric needs account context before
any customer-facing action.

## Engagement and Segment Patterns

Observed paid-account retention rises with the synthetic engagement state:

| Engagement | Paid accounts | Retained | Churned | Retention |
|---|---:|---:|---:|---:|
| Low | 12 | 9 | 3 | 75.0% |
| Medium | 27 | 23 | 4 | 85.2% |
| High | 17 | 16 | 1 | 94.1% |

Enterprise accounts show 100% observed retention in this run, while Growth and
Starter are each 83.3%. The Enterprise group contains only eight accounts, so
the result should not be generalized.

## Revenue Context

- 56 of 100 trial accounts converted to paid.
- 48 paid accounts remain active and 8 have churned.
- December logo churn is 9.3%: 4 cancellations from 43 opening accounts.
- December churned MRR is $596, or 4.24% of $14,057 starting MRR.
- December NRR is 90.4% after churn and contraction; new-logo revenue is
  excluded.
- October NRR reaches 113.9% because $750 of expansion exceeds churn and
  contraction for the existing base.

## Recommended Human Review

A retention team using this synthetic demonstration would prioritize accounts
where several signals occur together:

1. falling 7-day or 30-day event activity;
2. long time since last activity, report, or login;
3. one or very few active users;
4. low seat utilization;
5. no integration and little reporting depth; and
6. recent or repeated failed payments.

These observations should start an investigation, not trigger an automated
message, discount, or account decision.

## Reproducibility

Figures come from `mart_retention_behavior`, `mart_retention_segments`,
`mart_logo_churn`, `mart_revenue_churn`, and `mart_revenue_retention` in
`analytics_dbt/analytics.duckdb`. Regenerate the seed-42 data and run dbt to
reproduce them.
