# Churn Risk Model Card

## Model purpose

The model ranks currently active, paid SaaS accounts by risk of cancelling in
the next 30 days. It helps a retention team decide which accounts to review
first. It does not contact customers, approve discounts, change subscriptions,
or make account decisions.

## Prediction and label

- **Prediction unit:** one eligible paid account on one monthly prediction date.
- **Positive label:** cancellation occurs strictly after the prediction date
  and no more than 30 days later.
- **Eligibility:** paid subscription started and not already cancelled on the
  prediction date.
- **Information cutoff:** only product events and invoices known by the
  prediction date are used.

Cancellation date and future subscription state are never input features.
`mart_churn_features` stores cutoff metadata so leakage checks are testable.

## Data and evaluation method

The deterministic seed-42 training artifact contains 107 account-month rows:
eight churn labels (7.5%) and 99 non-churn labels. Splits are chronological,
not random.

| Split | Prediction dates | Rows |
|---|---|---:|
| Train | 2025-08-01 through 2025-10-01 | 32 |
| Validation | 2025-11-01 | 32 |
| Test | 2025-12-01 | 43 |

The validation month selects the model and classification threshold. The test
month remains untouched until final evaluation.

## Features

Features available at prediction time include:

- recent 7-day and 30-day activity;
- change from the preceding 30-day period;
- days since activity, report creation, and login;
- active users and seat utilization;
- invites, integrations, dashboards, reports created, and reports exported;
- failed-payment history and historical monthly revenue;
- activation status and known time to activation; and
- plan, acquisition channel, company size, seats, and account age.

These fields are predictive signals, not proof that an action causes churn.

## Models

- **Baseline:** Logistic Regression with preprocessing and class weighting.
- **Candidate/selected model:** HistGradientBoosting with class weighting.
- **Selection rule:** highest validation top-10% lift, then validation PR-AUC.

## Held-out test results

| Model | PR-AUC | ROC-AUC | Precision | Recall | F1 | Top-10% lift |
|---|---:|---:|---:|---:|---:|---:|
| Logistic Regression | 0.130 | 0.545 | 0.114 | 1.000 | 0.205 | 0.00× |
| HistGradientBoosting | 0.173 | 0.660 | 0.125 | 0.500 | 0.200 | 2.15× |

HistGradientBoosting improved held-out PR-AUC by 32.9% relative to the
baseline and achieved 2.15× top-decile lift. Absolute precision remains low;
this is a prioritization demonstration, not evidence of production readiness.

## Interpretation

Permutation importance on the held-out month ranked recent event volume, days
since last login, company size, and 30-day activity change among the strongest
signals in this small sample. Importance can move substantially with more data.

Each scored account receives up to three factual reasons derived from its
feature values, such as declining activity, low seat utilization, no recent
reports, a failed-payment signal, or no integration. The reasons describe the
account state and do not claim to explain the model causally.

The latest saved score artifact ranks 48 active paid accounts: 2 Medium and 46
Low under the current illustrative thresholds. Scores are useful for ordering
review work and are **not claimed to be calibrated churn probabilities**.

## Limitations

- All data is synthetic and reflects generator assumptions.
- Eight positive outcomes are insufficient for stable performance estimates.
- Multiple account-month rows from one account are correlated.
- The held-out test month contains only four positive cases.
- Permutation importance is unstable at this sample size.
- Probability calibration was not attempted.
- Segment stability, drift, fairness, and intervention outcomes are not
  established.

## Human-decision use

Use the score to create an investigation queue. A person should examine account
history, service context, and customer relationship information before any
action. A real deployment would require more history, probability calibration,
segment and drift monitoring, intervention measurement, and a documented
human-review policy.

## Reproduce the artifacts

After `dbt run`:

```bash
python ml/build_dataset.py
python ml/train.py
python ml/evaluate.py
python ml/explain.py
python ml/score_accounts.py
```

The workflow saves training snapshots, both models, evaluation metrics,
permutation importance, and the active-account ranking under `artifacts/`.
