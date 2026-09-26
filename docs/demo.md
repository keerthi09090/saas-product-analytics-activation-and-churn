# Five-Minute Project Demo

This sequence is designed for a recruiter or hiring-manager walkthrough. Start
the Docker services, FastAPI, and Streamlit before the meeting; do not spend the
demo waiting for builds.

## 0:00–0:30 — Frame the problem

“This is a synthetic B2B SaaS platform that unifies activation, adoption,
retention, recurring revenue, and churn-risk prioritization. It demonstrates
the full analytical path without exposing customer data.”

Show the README architecture diagram and point out the separate batch and
streaming paths.

## 0:30–1:20 — Product analytics

Open Streamlit at <http://localhost:8501> on **Product Analytics**.

- Show 100 accounts, 50% activation, five-day median activation time, and 56%
  trial conversion.
- Explain the 14-day activation rule.
- Use the activation funnel to identify where accounts drop off.
- Show feature adoption and the weekly/monthly active-account trends.

Business question: “Where does onboarding lose accounts, and which features
have room to grow?”

## 1:20–2:10 — Retention and revenue

Select **Retention & Churn**.

- Show the retention-cohort heatmap.
- Compare logo churn with revenue churn.
- Explain NRR and point out expansion/contraction months.
- Compare retained and churned account behavior.

Business question: “Which segments and behaviors are associated with
retention, and how much recurring revenue is moving?”

## 2:10–3:00 — Churn-risk workflow

Select **Churn Risk**.

- State that the scores rank accounts; they are not calibrated probabilities.
- Show the risk distribution and top accounts.
- Look up one account and read only the API-provided descriptive reasons.
- Mention the held-out 32.9% relative PR-AUC improvement and 2.15× top-decile
  lift, together with the small-sample limitation.

Business question: “Which active paid accounts should a retention analyst
investigate first, and what observed signals provide context?”

## 3:00–3:35 — API

Open <http://localhost:8000/docs>.

- Expand `GET /v1/churn/{account_id}`.
- Point out typed responses, health/readiness endpoints, and Prometheus metrics.
- Emphasize that API requests load saved scores and never retrain the model.

## 3:35–4:10 — Streaming and orchestration

- Return to Streamlit's **Streaming Status** block and show event count and
  freshness.
- In Airflow at <http://localhost:8080>, show the daily DAG sequence:
  snapshots → dbt run → dbt test → score refresh.
- Explain that rerunning a logical date replaces its partition, demonstrating
  idempotent backfills.

## 4:10–4:35 — Observability

Open <http://localhost:9090/targets>.

- Confirm the churn API target is up.
- Explain the request/error/latency, Kafka freshness, analytics freshness, and
  Airflow health signals.
- Label the p95-under-200-ms goal as a local portfolio target, not an SLA.

## 4:35–5:00 — Engineering quality

Open the repository's GitHub Actions page.

- Show green **CI** and **Data Quality** workflows.
- Mention 55 Python tests and 113 dbt tests.
- Close with the outcome: tested product analytics plus a human-review churn
  queue, built from reproducible synthetic data.

## Useful tabs to prepare

1. Repository README
2. Streamlit Product Analytics
3. Streamlit Retention & Churn
4. Streamlit Churn Risk
5. FastAPI `/docs`
6. Airflow DAG graph/grid
7. Prometheus targets
8. GitHub Actions
