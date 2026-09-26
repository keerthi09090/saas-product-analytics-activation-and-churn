# Level 11 CI/CD quality gates

GitHub Actions validates every push to `main` and every pull request targeting
`main`. It does not deploy the application.

```text
Push / Pull Request
        |
        +--> CI
        |     lint
        |       -> deterministic data
        |       -> dbt model preparation
        |       -> lightweight ML artifacts
        |       -> complete Python test suite
        |
        +--> Data Quality
              deterministic data
                -> dbt debug
                -> dbt run
                -> dbt test
                -> data-contract and pipeline tests
```

## CI workflow

`.github/workflows/ci.yml` installs Python 3.11 dependencies with pip caching,
runs `ruff check .`, regenerates the seed-42 dataset, materializes the dbt
models required by the ML feature builder, builds deterministic model and
risk-score artifacts, and runs `python -m pytest`.

The complete test suite covers the generator, event contracts, model artifact
contract and leakage protections, FastAPI, Kafka consumer behavior, Airflow
DAG definitions and batch logic, and observability endpoints and metrics. No
Kafka broker, Airflow UI, Prometheus UI, or load test is required in normal CI.

## Data Quality workflow

`.github/workflows/data_quality.yml` independently verifies the DuckDB profile
with `dbt debug`, builds every model, executes all dbt data tests, then runs the
focused generator, streaming-contract, snapshot, backfill, and DAG-import
tests. This gives data-model failures a short, dedicated Actions log.

## What failure means

A red workflow means at least one required quality gate failed. Open the failed
job and expand the first red step. Fix the actual lint, test, model, data
contract, or dependency issue; do not make the workflow ignore its exit code.
A green workflow means all automated checks completed successfully for that
commit. It is not a deployment approval or a production SLA.

## Safe failure demonstration

Use a temporary branch, never `main`:

```bash
git switch -c demo/ci-failure
```

Temporarily change one harmless assertion in a test, commit it, and push the
branch. Open a pull request to `main`; CI should show a red X with the failed
assertion in its log. Restore the assertion, commit, and push again. The same
pull request should turn green. Delete the demonstration branch afterward.

This demonstrates that the gate detects a real failure without leaving the
default branch broken.

## Repository setup and badge

After the local repository is published, add the real workflow badge using
the actual GitHub owner and repository name:

```markdown
[![CI](https://github.com/OWNER/REPOSITORY/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPOSITORY/actions/workflows/ci.yml)
```

Do not substitute a guessed repository or a static “passing” image. The badge
is valid only after GitHub has run `.github/workflows/ci.yml`.

## Secrets and generated files

`.env` is ignored. `.env.example` contains only placeholders. GitHub workflows
do not need credentials. Generated Parquet, DuckDB, MLflow, model, streaming,
Airflow-log, dbt-target, cache, and virtual-environment files are ignored and
rebuilt deterministically in CI.

Cloud deployment, Kubernetes, Terraform, and public application hosting are
outside Level 11.
