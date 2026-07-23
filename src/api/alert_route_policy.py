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

from typing import Any

from fastapi import Depends, Request

from api.http_auth_policy import (
    AUTHENTICATION_FAILURE_RESPONSES,
    require_http_principal,
)
from api.http_rate_limit_policy import enforce_http_rate_limit
from api.schemas import (
    ApiErrorResponse,
    ApiRateLimitErrorResponse,
)
from api_auth import AuthPrincipal

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

    enforce_http_rate_limit(request=request, principal=principal)
