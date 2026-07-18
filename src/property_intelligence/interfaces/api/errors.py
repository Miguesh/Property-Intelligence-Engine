"""Central exception-to-HTTP translation with secret-safe responses."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from property_intelligence.application.exceptions import ApplicationError
from property_intelligence.interfaces.api.context import request_id_context
from property_intelligence.interfaces.api.middleware import response_security_headers

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", request_id_context.get()))


def _payload(
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "error": {"code": code, "message": message, "details": details},
        "request_id": request_id or request_id_context.get(),
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Register stable public error envelopes."""

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "location": [str(part) for part in error.get("loc", ())],
                "message": error.get("msg", "Invalid value"),
                "type": error.get("type", "validation_error"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_payload(
                "validation_error",
                "Request validation failed.",
                details,
                request_id=_request_id(_request),
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        code = "authentication_failed" if exc.status_code == 401 else "http_error"
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(code, str(exc.detail), request_id=_request_id(_request)),
            headers=exc.headers,
        )

    @app.exception_handler(ApplicationError)
    async def application_error_handler(_request: Request, exc: ApplicationError) -> JSONResponse:
        # Provider exceptions are chained internally for debugging, but their
        # messages can contain request or upstream details. Keep production
        # logs metadata-only at this boundary.
        logger.warning(
            "application_error",
            extra={"error_type": type(exc).__name__},
        )
        return JSONResponse(
            status_code=503,
            content=_payload(
                "service_unavailable",
                "A required analysis service is unavailable.",
                request_id=_request_id(_request),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", exc_info=exc)
        request_id = _request_id(_request)
        return JSONResponse(
            status_code=500,
            content=_payload(
                "internal_error",
                "An unexpected error occurred.",
                request_id=request_id,
            ),
            headers=response_security_headers(request_id),
        )
