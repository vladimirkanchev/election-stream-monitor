"""Shared FastAPI boundary policy for alert-query routes.

This module keeps the non-business HTTP protection mechanics in one place for
the alert-query router family:

- router-scoped authentication
- router-scoped rate limiting
- stable shared response metadata for the protected alert routes

Keeping that policy separate lets `api/routers/alerts.py` read more like a set
of thin route declarations over the shared alert services.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Header, Request

from api.errors import AuthenticationFailedError, RateLimitExceededError
from api.schemas import (
    ApiAuthenticationErrorResponse,
    ApiErrorResponse,
    ApiRateLimitErrorResponse,
)
from api_auth import (
    API_KEY_HEADER_NAME,
    AuthPrincipal,
    AuthenticationError,
    authenticate_api_request,
)
from api_rate_limit import (
    RateLimitError,
    enforce_resolved_rate_limit,
    resolve_api_rate_limit_context,
)

logger = logging.getLogger(__name__)

# Keep the protected-route response metadata here so auth/rate-limit contract
# changes do not require repeating the same response dictionary in every alert
# route declaration.
ALERT_ROUTE_RESPONSES: dict[int, dict[str, Any]] = {
    400: {"model": ApiErrorResponse, "description": "Validation failed"},
    401: {
        "model": ApiAuthenticationErrorResponse,
        "description": "Authentication failed",
    },
    429: {
        "model": ApiRateLimitErrorResponse,
        "description": "Rate limit exceeded",
    },
    404: {"model": ApiErrorResponse, "description": "Session not found"},
    422: {"model": ApiErrorResponse, "description": "Request validation failed"},
}


async def require_http_alert_principal(
    request: Request,
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER_NAME),
) -> AuthPrincipal:
    """Authenticate and rate-limit one protected alert-route request.

    This is the single dependency attached to the alerts router. It composes
    the auth seam and the limiter seam in the correct order, emits boundary
    logs for the protected surface, and returns only the authenticated
    principal back to FastAPI's dependency system.
    """

    principal = _authenticate_http_alert_request(request=request, x_api_key=x_api_key)
    _enforce_http_alert_rate_limit(request=request, principal=principal)
    return principal


def _authenticate_http_alert_request(
    *,
    request: Request,
    x_api_key: str | None,
) -> AuthPrincipal:
    """Authenticate one alert-route request against the shared auth seam.

    HTTP-specific `401` mapping and warning-level boundary logging stay here
    so the underlying auth module can remain a transport-agnostic
    credential-validation seam.
    """

    try:
        return authenticate_api_request(x_api_key=x_api_key)
    except AuthenticationError as err:
        logger.warning(
            "auth_failed path=%s reason=%s",
            request.url.path,
            str(err),
        )
        raise AuthenticationFailedError(str(err)) from err


def _enforce_http_alert_rate_limit(
    *,
    request: Request,
    principal: AuthPrincipal,
) -> None:
    """Apply alerts-router rate limiting after authentication succeeds.

    The limiter module raises plain domain-style rate-limit failures. This
    helper keeps ownership of the FastAPI-specific `429` mapping, coarse
    `Retry-After` shaping, and rate-limit logging local to the protected
    alerts boundary.
    """

    request_host = _get_request_host(request)
    context = resolve_api_rate_limit_context(
        principal=principal,
        request_host=request_host,
    )
    if context is None:
        return

    try:
        enforce_resolved_rate_limit(context=context)
    except RateLimitError as err:
        logger.info(
            "rate_limit_exceeded path=%s strategy=%s subject=%s auth_type=%s reason=%s",
            request.url.path,
            context.settings.strategy,
            context.subject,
            principal.auth_type,
            str(err),
        )
        raise RateLimitExceededError(
            str(err),
            retry_after_seconds=context.settings.window_seconds,
        ) from err


def _get_request_host(request: Request) -> str | None:
    """Return one best-effort request host for the current HTTP boundary.

    The current limiter can fall back to host-based identity under the `ip`
    strategy, so the boundary resolves the host once here instead of
    scattering request-client handling across auth and limiter code.
    """

    if request.client is None:
        return None
    return request.client.host
