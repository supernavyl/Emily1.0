"""
API authentication — Bearer token validation.

All API endpoints require Authorization: Bearer <token> when api.secret_key
(or EMILY_API_SECRET) is set. The secret must be set in environment or .env,
not in config.yaml.

Usage: add Depends(require_bearer) to routes, or apply via middleware.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import get_settings

_scheme = HTTPBearer(auto_error=False)


def get_api_secret() -> str | None:
    """
    Return the API secret from config or EMILY_API_SECRET env.

    Prefer env var so the secret is never stored in config.yaml.
    """
    settings = get_settings()
    secret = settings.api.secret_key
    if secret:
        return secret
    return os.environ.get("EMILY_API_SECRET") or None


def require_bearer(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_scheme)],
) -> None:
    """
    FastAPI dependency: require valid Bearer token for the request.

    If no API secret is configured, all requests are rejected with 401
    and a message to set EMILY_API_SECRET (or api.secret_key via env).
    """
    secret = get_api_secret()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API secret not configured. Set EMILY_API_SECRET in .env or environment.",
        )
    if not credentials or credentials.credentials != secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
