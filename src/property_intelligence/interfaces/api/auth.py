"""Header-token authentication dependency for protected API routers."""

from __future__ import annotations

from hashlib import sha256
from secrets import compare_digest
from typing import Annotated

from fastapi import HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(auto_error=False)


async def verify_api_key(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)] = None,
) -> None:
    """Enforce the configured bearer API key using constant-time comparison."""

    settings = request.app.state.settings
    if not settings.auth_enabled:
        return
    expected = settings.api_key.get_secret_value() if settings.api_key else ""
    supplied = credentials.credentials if credentials else ""
    if (
        credentials is None
        or credentials.scheme.casefold() != "bearer"
        or not compare_digest(
            sha256(supplied.encode("utf-8")).digest(),
            sha256(expected.encode("utf-8")).digest(),
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
