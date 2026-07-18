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

from fastapi import Depends, Request

from api.errors import RateLimitExceededError
from api.http_auth_policy import (
    AUTHENTICATION_FAILURE_RESPONSES,
    require_http_principal,
)
from api.schemas import (
    ApiErrorResponse,
    ApiRateLimitErrorResponse,
)
from api_auth import AuthPrincipal
from api_rate_limit import (
    RateLimitError,
    enforce_resolved_rate_limit,
    resolve_api_rate_limit_context,
)

logger = logging.getLogger(__name__)

# Keep the protected-route response metadata here so auth/rate-limit contract
# changes do not require repeating the same response dictionary in every alert
# route declaration.
ALERT_ROUTE_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ApiErrorResponse, "description": "Validation failed"},
    **AUTHENTICATION_FAILURE_RESPONSES,
    429: {
        "model": ApiRateLimitErrorResponse,
        "description": "Rate limit exceeded",
    },
    404: {"model": ApiErrorResponse, "description": "Session not found"},
    422: {"model": ApiErrorResponse, "description": "Request validation failed"},
}


async def require_http_alert_principal(
    request: Request,
    principal: AuthPrincipal = Depends(require_http_principal),
) -> AuthPrincipal:
    """Authenticate and rate-limit one protected alert-route request.

    This is the single dependency attached to the alerts router. It composes
    the auth seam and the limiter seam in the correct order, emits boundary
    logs for the protected surface, and returns only the authenticated
    principal back to FastAPI's dependency system.
    """

    _enforce_http_alert_rate_limit(request=request, principal=principal)
    return principal


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
