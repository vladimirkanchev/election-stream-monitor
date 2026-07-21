"""Reusable FastAPI authentication dependency for protected HTTP routes.

This module owns HTTP-specific API-key extraction, safe authentication-failure
logging, and stable ``401`` mapping. Route families compose it with their own
authorization or resource policies instead of duplicating request mechanics.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Header, Request

from api.errors import AuthenticationFailedError
from api.schemas import ApiAuthenticationErrorResponse
from api_auth import (
    API_KEY_HEADER_NAME,
    AuthPrincipal,
    AuthenticationError,
    authenticate_api_request,
)

logger = logging.getLogger(__name__)

AUTHENTICATION_FAILURE_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {
        "model": ApiAuthenticationErrorResponse,
        "description": "Authentication failed",
    },
}


async def require_http_principal(
    request: Request,
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER_NAME),
) -> AuthPrincipal:
    """Return the authenticated HTTP principal or raise the stable ``401`` error."""

    try:
        return authenticate_api_request(x_api_key=x_api_key)
    except AuthenticationError as err:
        logger.warning(
            "auth_failed path=%s reason_code=%s",
            request.url.path,
            err.reason_code,
        )
        raise AuthenticationFailedError(str(err)) from err
