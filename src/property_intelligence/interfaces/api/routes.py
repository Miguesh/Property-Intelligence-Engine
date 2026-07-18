"""Versioned REST routes kept free of provider and scoring logic."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Security, status

from property_intelligence.application.use_cases import AnalyzeListingUseCase
from property_intelligence.interfaces.api.auth import verify_api_key
from property_intelligence.interfaces.api.dependencies import get_analyze_listing_use_case
from property_intelligence.interfaces.api.schemas import (
    AnalysisResponse,
    ErrorResponse,
    HealthResponse,
    ListingAnalysisRequest,
)

health_router = APIRouter(tags=["health"])
analysis_router = APIRouter(
    prefix="/analyses",
    tags=["analysis"],
    dependencies=[Security(verify_api_key)],
)


@health_router.get(
    "/health/live",
    response_model=HealthResponse,
    summary="Process liveness",
)
async def liveness(request: Request) -> HealthResponse:
    """Report whether the API process is serving requests."""

    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        environment=settings.environment,
        components={},
    )


@health_router.get(
    "/health/ready",
    response_model=HealthResponse,
    summary="Dependency readiness",
)
async def readiness(request: Request) -> HealthResponse:
    """Report composed provider modes without making billable API calls."""

    settings = request.app.state.settings
    components = dict(request.app.state.component_status)
    required_unavailable = any(value == "required_unavailable" for value in components.values())
    return HealthResponse(
        status="degraded" if required_unavailable else "ok",
        version=settings.app_version,
        environment=settings.environment,
        components=components,
    )


@analysis_router.post(
    "",
    response_model=AnalysisResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication failed"},
        413: {"model": ErrorResponse, "description": "Request too large"},
        422: {"model": ErrorResponse, "description": "Validation failed"},
        503: {"model": ErrorResponse, "description": "Required provider unavailable"},
    },
    summary="Analyze a short-term rental listing",
)
async def analyze_listing(
    payload: ListingAnalysisRequest,
    use_case: Annotated[AnalyzeListingUseCase, Depends(get_analyze_listing_use_case)],
) -> AnalysisResponse:
    """Analyze submitted listing content and return actionable recommendations."""

    result = await use_case.execute(payload.to_domain())
    return AnalysisResponse.from_domain(result)
