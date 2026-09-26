"""Small safeguards for generated files and local-only credentials."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_local_environment_and_generated_outputs_are_ignored():
    ignored = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    for expected in [
        ".env",
        ".venv/",
        ".pytest_cache/",
        ".ruff_cache/",
        "analytics_dbt/target/",
        "analytics_dbt/logs/",
        "airflow/logs/",
        "data/*.parquet",
        "data/streaming/product_events/",
        "mlruns/",
    ]:
        assert expected in ignored


def test_compose_uses_environment_variables_for_local_credentials():
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "POSTGRES_PASSWORD: ${AIRFLOW_DB_PASSWORD}" in compose
    assert "AIRFLOW__WEBSERVER__SECRET_KEY: ${AIRFLOW_WEBSERVER_SECRET_KEY}" in compose
    assert "POSTGRES_PASSWORD: airflow" not in compose
    assert "--password admin" not in compose

    example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "AIRFLOW_DB_PASSWORD=change_me" in example
    assert "AIRFLOW_ADMIN_PASSWORD=change_me" in example
