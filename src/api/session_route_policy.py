"""Authentication and resource policy for session start and cancellation.

Session reads remain authentication-only for now. Starts and cancellations are
separate because worker creation is expensive while cancellation must retain
capacity during a burst of admitted start requests.
"""

from __future__ import annotations

from fastapi import Depends, Request

from api.http_auth_policy import require_http_principal
from api.http_rate_limit_policy import enforce_http_rate_limit
from api_auth import AuthPrincipal
from api_boundary_config import (
    get_session_control_rate_limit_settings,
    get_session_start_rate_limit_settings,
)

SESSION_CONTROL_BUDGET = "session-control"
SESSION_START_BUDGET = "session-start"


async def require_http_session_start_principal(
    request: Request,
    principal: AuthPrincipal = Depends(require_http_principal),  # noqa: B008
) -> AuthPrincipal:
    """Authenticate one start request and reserve cancellation capacity.

    The stricter start-only guard runs first. A rejected extra start therefore
    does not consume the shared session-control budget used by cancellation.
    """

    enforce_http_rate_limit(
        request=request,
        principal=principal,
        settings=get_session_start_rate_limit_settings(),
        budget_name=SESSION_START_BUDGET,
    )
    enforce_http_rate_limit(
        request=request,
        principal=principal,
        settings=get_session_control_rate_limit_settings(),
        budget_name=SESSION_CONTROL_BUDGET,
    )
    return principal


async def require_http_session_cancel_principal(
    request: Request,
    principal: AuthPrincipal = Depends(require_http_principal),  # noqa: B008
) -> AuthPrincipal:
    """Authenticate one cancellation against the shared control budget."""

    enforce_http_rate_limit(
        request=request,
        principal=principal,
        settings=get_session_control_rate_limit_settings(),
        budget_name=SESSION_CONTROL_BUDGET,
    )
    return principal
