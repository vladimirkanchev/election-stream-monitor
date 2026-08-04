"""Authentication and resource policy for playback-source resolution."""

from __future__ import annotations

from fastapi import Depends, Request

from api.http_auth_policy import require_http_principal
from api.http_rate_limit_policy import enforce_http_rate_limit
from api_auth import AuthPrincipal
from api_boundary_config import get_playback_resolution_rate_limit_settings

PLAYBACK_RESOLUTION_BUDGET = "playback-resolution"


async def require_http_playback_principal(
    request: Request,
    principal: AuthPrincipal = Depends(require_http_principal),  # noqa: B008
) -> AuthPrincipal:
    """Authenticate one playback request and enforce its separate budget."""

    enforce_http_rate_limit(
        request=request,
        principal=principal,
        settings=get_playback_resolution_rate_limit_settings(),
        budget_name=PLAYBACK_RESOLUTION_BUDGET,
    )
    return principal
