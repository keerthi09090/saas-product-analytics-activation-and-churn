# Churn Model Card

## Purpose

This model ranks currently active, paid SaaS accounts by the likelihood that
they will cancel in the next 30 days. Its intended use is to help a retention
team decide which accounts to review first and to provide a few factual reasons
for that review. It is not a causal model, an automated cancellation decision,
or a substitute for account-manager judgment.

## Prediction definition

- **Unit of prediction:** one paid account on one monthly prediction date.
- **Target:** `1` when cancellation occurs strictly after the prediction date
  and no more than 30 days later; otherwise `0`.
- **Eligibility:** the account must have started a paid subscription and must
  not already be cancelled at the prediction date.
- **Feature cutoff:** product events through the end of the prediction date and
  invoices dated on or before the prediction date. Cancellation date and
  current/future cancellation status are never model features.

`mart_churn_features` builds the historical snapshots. Its latest-event and
latest-invoice metadata make the cutoff testable.

## Data and validation design

The reproducible seed-42 dataset produces 107 account-month observations: 8
positive churn labels (7.5%) and 99 negative labels. The small sample is useful
for demonstrating the complete workflow, but it is not enough for a
production-quality model.

The split is chronological, never random:

| Split | Prediction dates | Rows |
|---|---|---:|
| Train | 2025-08-01 through 2025-10-01 | 32 |
| Validation | 2025-11-01 | 32 |
| Test | 2025-12-01 | 43 |

Model selection and classification thresholds use only the validation month.
The December test month remains untouched until final evaluation.

## Features

The model uses attributes known at prediction time:

- account plan, acquisition channel, size, purchased seats, and account age;
- 7-day and 30-day event frequency plus change from the prior 30 days;
- recent active-user count and seat utilization;
- report creation/export, dashboard, invite, and integration usage;
- days since activity, report creation, and login;
- failed-payment history and historical monthly revenue; and
- activation status and time to activation when activation had already occurred.

These features are predictive signals, not proof that an action causes churn.

## Models and held-out results

Both models use class weighting to address the imbalanced target.

| Model | PR-AUC | ROC-AUC | Precision | Recall | F1 | Top-decile lift |
|---|---:|---:|---:|---:|---:|---:|
| Logistic regression | 0.130 | 0.545 | 0.114 | 1.000 | 0.205 | 0.00x |
| Histogram gradient boosting | 0.173 | 0.660 | 0.125 | 0.500 | 0.200 | 2.15x |

Histogram gradient boosting is selected because it wins the validation-only
selection rule: highest top-decile lift, then PR-AUC. On the untouched test
month it improves PR-AUC by 32.9% relative to logistic regression and achieves
2.15x top-decile lift, meeting both suggested portfolio gates. The low absolute
precision is important: this is a prioritization demonstration, not evidence
of production readiness.

The classification cutoff was selected on validation data by maximum F1, with
higher precision and then a higher cutoff as tie-breakers. PR-AUC, ROC-AUC, and
lift are ranking metrics and are independent of that cutoff.

## Interpretation

Permutation importance on the held-out month identifies recent event volume,
days since last login, company size, and 30-day activity change as the strongest
signals in this small dataset. Importance may vary substantially after data
regeneration or with more observations.

Each scored account receives up to three descriptive reasons derived from its
input values, such as declining activity, low seat utilization, no recent
reports, failed payments, or no connected integration. These reasons describe
the observed account state; they do not claim to explain the model causally.

## Current scoring output

`artifacts/churn_risk_scores.parquet` contains all 48 currently active paid
accounts, sorted by model score. In the current run, one account is above the
illustrative high-risk cutoff and represents $49 in monthly revenue. The raw
scores are useful for ranking but are not claimed to be calibrated
probabilities.

## Limitations and responsible use

- The data is synthetic and reflects the assumptions of the generator.
- Eight churn outcomes are far too few for stable performance estimates.
- Repeated account snapshots are correlated, even though the time split avoids
  future-to-past leakage.
- Permutation importance is unstable on a test set with four positive cases.
- Probability calibration was not attempted because the validation sample is
  too small.
- A real deployment should add more history, calibration, segment stability
  checks, drift monitoring, intervention-outcome tracking, and a human review
  policy before taking customer-facing action.

## Reproduction

From the project root, after building the dbt models:

```bash
python ml/build_dataset.py
python ml/train.py
python ml/evaluate.py
python ml/explain.py
python ml/score_accounts.py
```

Inspect experiments locally with:

```bash
mlflow ui --backend-store-uri ./mlruns --port 5000
```

The stored artifacts include the training snapshots, both fitted models, model
metrics, permutation importance, and account-level risk rankings.
