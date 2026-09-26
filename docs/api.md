# Churn Risk API

The Level 7 FastAPI service exposes the latest account-level risk ranking from
`artifacts/churn_risk_scores.parquet`. It loads that file once when the service
starts. Requests do not retrain the model or rerun the ML feature pipeline.

The score is a model-generated ranking signal. It is not claimed to be the
exact probability that an account will churn.

## Start the API

From the project root:

```bash
source .venv/bin/activate
uvicorn api.main:app --reload
```

The Level 6 scoring artifact must exist. Regenerate it, if needed, with:

```bash
python ml/score_accounts.py
```

## Endpoints

| Method and path | Purpose |
|---|---|
| `GET /health` | Confirm the service and artifact loaded |
| `GET /v1/churn/{account_id}` | Retrieve one account's risk and reasons |
| `GET /v1/churn` | List accounts in descending risk order |
| `GET /v1/churn?risk_bucket=High&limit=20` | Filter and limit ranking results |
| `GET /v1/churn/summary` | Summarize risk buckets and high-risk revenue |
| `GET /docs` | Interactive Swagger documentation |
| `GET /redoc` | ReDoc documentation |

The list endpoint accepts `limit` from 1 through 100. Risk bucket accepts
`Low`, `Medium`, or `High`. Unknown accounts return HTTP 404; invalid query
parameters return HTTP 422.

Example request:

```bash
curl http://127.0.0.1:8000/v1/churn/A040
```

Example response from the reproducible scoring run:

```json
{
  "account_id": "A040",
  "churn_score": 0.708328,
  "risk_bucket": "High",
  "prediction_date": "2025-12-31",
  "monthly_revenue": 49.0,
  "top_reasons": [
    "activity declined 75% versus the prior 30 days",
    "last product activity was 28 days ago",
    "no report has been created"
  ]
}
```

## Local load test

With Uvicorn running in another terminal:

```bash
python tests/load_test.py --requests 200
```

The script reports request count, errors, average, p50, and p95 latency and
checks the portfolio target of p95 below 200 ms. This target is measured
locally on the development machine and is not a production-scale benchmark.

Measured on September 25, 2026 using CPython 3.9, Uvicorn on the macOS
development machine's loopback interface, and 200 sequential requests after 10
warm-up requests:

| Result | Value |
|---|---:|
| Errors | 0 |
| Average | 1.18 ms |
| p50 | 1.09 ms |
| p95 | 1.59 ms |

This measurement uses a tiny in-memory dataset and should not be interpreted as
production capacity or internet-facing latency.

## Human decision-making

The API supplies risk, descriptive signals, and monthly revenue to help a
retention team prioritize account review. It does not contact customers, issue
discounts, cancel subscriptions, or change plans. A human decides whether any
action is appropriate.
