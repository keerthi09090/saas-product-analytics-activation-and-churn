"""Level 7 contract tests for the churn-risk API."""

from fastapi.testclient import TestClient

from api.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_known_account_returns_score_and_correct_id():
    with TestClient(app) as client:
        response = client.get("/v1/churn/A040")
    assert response.status_code == 200
    result = response.json()
    assert result["account_id"] == "A040"
    assert 0 <= result["churn_score"] <= 1
    assert result["risk_bucket"] in {"Low", "Medium", "High"}
    assert all(reason for reason in result["top_reasons"])


def test_account_lookup_is_case_insensitive():
    with TestClient(app) as client:
        response = client.get("/v1/churn/a040")
    assert response.status_code == 200
    assert response.json()["account_id"] == "A040"


def test_unknown_account_returns_clear_404():
    with TestClient(app) as client:
        response = client.get("/v1/churn/DOES_NOT_EXIST")
    assert response.status_code == 404
    assert response.json() == {"detail": "Account not found"}


def test_ranked_list_is_sorted_and_scores_are_valid():
    with TestClient(app) as client:
        response = client.get("/v1/churn", params={"limit": 100})
    assert response.status_code == 200
    result = response.json()
    scores = [account["churn_score"] for account in result["accounts"]]
    assert result["count"] == len(result["accounts"])
    assert scores == sorted(scores, reverse=True)
    assert all(0 <= score <= 1 for score in scores)


def test_high_risk_filter_returns_only_high_accounts():
    with TestClient(app) as client:
        response = client.get(
            "/v1/churn", params={"risk_bucket": "High", "limit": 20}
        )
    assert response.status_code == 200
    result = response.json()
    assert all(
        account["risk_bucket"] == "High" for account in result["accounts"]
    )


def test_limit_caps_result_count():
    with TestClient(app) as client:
        response = client.get("/v1/churn", params={"limit": 5})
    assert response.status_code == 200
    assert response.json()["count"] <= 5


def test_invalid_limits_and_bucket_are_rejected():
    with TestClient(app) as client:
        assert client.get("/v1/churn", params={"limit": 0}).status_code == 422
        assert client.get("/v1/churn", params={"limit": 101}).status_code == 422
        assert (
            client.get(
                "/v1/churn", params={"risk_bucket": "Critical"}
            ).status_code
            == 422
        )


def test_summary_matches_ranked_data():
    with TestClient(app) as client:
        summary_response = client.get("/v1/churn/summary")
        list_response = client.get("/v1/churn", params={"limit": 100})
    assert summary_response.status_code == 200
    summary = summary_response.json()
    accounts = list_response.json()["accounts"]
    assert summary["scored_accounts"] == len(accounts)
    assert summary["high_risk_accounts"] == sum(
        account["risk_bucket"] == "High" for account in accounts
    )
    assert summary["medium_risk_accounts"] == sum(
        account["risk_bucket"] == "Medium" for account in accounts
    )
    assert summary["low_risk_accounts"] == sum(
        account["risk_bucket"] == "Low" for account in accounts
    )


def test_openapi_documentation_is_available():
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/docs").status_code == 200
        assert client.get("/redoc").status_code == 200
