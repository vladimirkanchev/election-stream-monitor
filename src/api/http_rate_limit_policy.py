"""Shared HTTP mapping for authenticated route-family rate limits.

Route families select their own settings and budget name. This module keeps
the common FastAPI-specific ``429`` mapping, safe logging, and request-host
lookup out of business services and out of any one router's policy module.
"""

from __future__ import annotations

import logging

from fastapi import Request

from api.errors import RateLimitExceededError
from api_auth import AuthPrincipal
from api_boundary_config import ApiRateLimitSettings
from api_rate_limit import (
    RateLimitError,
    ResolvedRateLimitContext,
    enforce_resolved_rate_limit,
    resolve_api_rate_limit_context,
)

logger = logging.getLogger(__name__)


def enforce_http_rate_limit(
    *,
    request: Request,
    principal: AuthPrincipal,
    settings: ApiRateLimitSettings | None = None,
    budget_name: str | None = None,
) -> None:
    """Enforce one named HTTP route-family budget after authentication."""

    context = resolve_api_rate_limit_context(
        principal=principal,
        request_host=_get_request_host(request),
        settings=settings,
        budget_name=budget_name,
    )
    if context is None:
        return

    try:
        enforce_resolved_rate_limit(context=context)
    except RateLimitError as error:
        _raise_rate_limit_exceeded(
            request=request,
            principal=principal,
            context=context,
            error=error,
        )


def _raise_rate_limit_exceeded(
    *,
    request: Request,
    principal: AuthPrincipal,
    context: ResolvedRateLimitContext,
    error: RateLimitError,
) -> None:
    """Log and map one limiter failure without exposing caller credentials."""

    logger.info(
        "rate_limit_exceeded path=%s budget=%s strategy=%s subject=%s auth_type=%s reason=%s",
        request.url.path,
        context.budget_name or "default",
        context.settings.strategy,
        context.subject,
        principal.auth_type,
        str(error),
    )
    raise RateLimitExceededError(
        str(error),
        retry_after_seconds=context.settings.window_seconds,
    ) from error


def _get_request_host(request: Request) -> str | None:
    """Return one best-effort request host for host-based limiter identity."""

    if request.client is None:
        return None
    return request.client.host
