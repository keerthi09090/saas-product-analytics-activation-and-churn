# Retention and Churn Analysis

This summary describes the seed-42 synthetic dataset as observed through
December 2025. Results are associations in simulated data, not causal claims.

## Retention pattern

- Week 0 retention is 100% by cohort definition. Among cohorts old enough to
  reach Week 4, 49 of 89 accounts were active, a cohort-weighted retention rate
  of 55.1%.
- Growth and Enterprise paid accounts both showed 100% current retention in
  this sample. Starter paid accounts showed 96.6% retention (28 of 29).
- High- and medium-engagement paid accounts showed 100% current retention.
  Low-engagement paid accounts showed 91.7% retention (11 of 12).

## Behavior associated with retention

- Retained paid accounts averaged 98.9 events and 11.4 active users, compared
  with 8 events and 1 active user for the churned group.
- Retained accounts averaged 8.9 reports created, 4.2 reports exported, and
  0.53 integration connections. The churned group averaged 1 report created,
  2 exports, and no integration connection.
- The churned comparison contains one account, so these differences are
  descriptive and should not be generalized beyond this synthetic sample.

## Churn and revenue

- Logo churn was 0% from July through November and 2.17% in December (1 of 46
  opening paid accounts).
- December churned MRR was $49, equal to 0.35% of $13,954 starting MRR.
- NRR was 100.0% in August, 88.5% in September, 100.0% in October, 108.2% in
  November, and 99.6% in December. September included $200 of contraction;
  November included $750 of expansion.

All figures come from the Level 5 dbt marts in `analytics_dbt/analytics.duckdb`.
