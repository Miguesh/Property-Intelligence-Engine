"""FastAPI dependencies that expose application services, not providers."""

from typing import cast

from fastapi import Request

from property_intelligence.application.use_cases import AnalyzeListingUseCase


def get_analyze_listing_use_case(request: Request) -> AnalyzeListingUseCase:
    """Resolve the composed use case from application state."""

    return cast(AnalyzeListingUseCase, request.app.state.analyze_listing_use_case)
