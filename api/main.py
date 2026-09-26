"""FastAPI routes for the Level 7 churn-risk serving layer."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import Annotated, Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from opentelemetry import trace
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from api.config import (
    API_TITLE,
    API_VERSION,
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    RISK_SCORES_PATH,
    SCORE_DESCRIPTION,
)
from api.schemas import (
    ChurnAccountList,
    ChurnPrediction,
    ChurnSummary,
    HealthResponse,
    RiskBucket,
)
from api.observability import (
    HTTP_DURATION,
    HTTP_ERRORS,
    HTTP_REQUESTS,
    configure_opentelemetry,
    refresh_observability_metrics,
)
from api.service import ChurnScoreService


def create_app(scores_path: Path = RISK_SCORES_PATH) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        # The artifact is read once at startup, never once per request.
        try:
            application.state.churn_service = ChurnScoreService.load(scores_path)
            application.state.startup_error = None
        except (FileNotFoundError, OSError, ValueError) as exc:
            application.state.churn_service = None
            application.state.startup_error = str(exc)
        yield

    application = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=(
            "Read-only access to the latest Level 6 account churn-risk ranking. "
            f"{SCORE_DESCRIPTION} The service does not retrain models or trigger "
            "customer actions."
        ),
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def observe_request(request: Request, call_next):
        started = perf_counter()
        response_status = 500
        try:
            response = await call_next(request)
            response_status = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            endpoint = getattr(route, "path", request.url.path)
            method = request.method
            HTTP_REQUESTS.labels(method, endpoint, str(response_status)).inc()
            HTTP_DURATION.labels(method, endpoint).observe(perf_counter() - started)
            if response_status >= 400:
                HTTP_ERRORS.labels(method, endpoint, str(response_status)).inc()
            span_context = trace.get_current_span().get_span_context()
            if "response" in locals() and span_context.is_valid:
                response.headers["X-Trace-ID"] = format(
                    span_context.trace_id, "032x"
                )

    def service(request: Request) -> ChurnScoreService:
        churn_service = request.app.state.churn_service
        if churn_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Churn scores are unavailable",
            )
        return churn_service

    @application.get(
        "/health",
        response_model=HealthResponse,
        summary="Check service health",
        description="Confirms that the API and churn-score artifact loaded successfully.",
    )
    def health(request: Request) -> HealthResponse:
        if request.app.state.churn_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service is degraded",
            )
        return HealthResponse(status="ok")

    @application.get("/ready", summary="Check service readiness")
    def ready(request: Request) -> dict[str, bool]:
        if request.app.state.churn_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Churn scores are unavailable",
            )
        return {"ready": True}

    @application.get("/metrics", include_in_schema=False)
    def metrics(request: Request) -> Response:
        refresh_observability_metrics(
            request.app.state.churn_service is not None
        )
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @application.get(
        "/v1/churn",
        response_model=ChurnAccountList,
        summary="List ranked account churn risk",
        description=(
            "Returns precomputed accounts from highest to lowest churn risk score. "
            "Optionally filters by risk bucket."
        ),
    )
    def list_churn_risk(
        request: Request,
        risk_bucket: Optional[RiskBucket] = Query(
            default=None, description="Optional Low, Medium, or High filter."
        ),
        limit: Annotated[
            int,
            Query(
                ge=1,
                le=MAX_LIST_LIMIT,
                description=f"Maximum accounts to return, up to {MAX_LIST_LIMIT}.",
            ),
        ] = DEFAULT_LIST_LIMIT,
    ) -> ChurnAccountList:
        accounts = service(request).list_accounts(risk_bucket, limit)
        return ChurnAccountList(count=len(accounts), accounts=accounts)

    # Keep this static route above the dynamic account route.
    @application.get(
        "/v1/churn/summary",
        response_model=ChurnSummary,
        summary="Summarize scored accounts and revenue at risk",
        description="Aggregates risk buckets and high-risk monthly revenue from the latest scoring run.",
    )
    def churn_summary(request: Request) -> ChurnSummary:
        return service(request).summary()

    @application.get(
        "/v1/churn/{account_id}",
        response_model=ChurnPrediction,
        responses={
            status.HTTP_404_NOT_FOUND: {
                "description": "The account is not present in the latest active-account scoring run."
            }
        },
        summary="Get churn risk for one account",
        description=(
            "Returns the account's precomputed risk score, bucket, business context, "
            "and non-causal descriptive risk signals."
        ),
    )
    def account_churn_risk(account_id: str, request: Request) -> ChurnPrediction:
        prediction = service(request).get_account(account_id)
        if prediction is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found",
            )
        return prediction

    configure_opentelemetry(application)
    return application


app = create_app()
