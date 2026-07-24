"""FastAPI adapters for session start/read/cancel endpoints.

Keep shared session lifecycle mechanics in `session_service.py`.
Keep this module focused on:

- request/response schema binding
- HTTP-oriented error mapping
- route-level ownership of the FastAPI session surface
- per-operation authentication, rate limits, and response bounds

Whether a caller must present a key is resolved by the active local/share
runtime policy, not by individual route handlers.
"""

from typing import Any

from fastapi import APIRouter, Depends

from api.errors import (
    CancelFailedError,
    ResponseLimitExceededError,
    SessionNotFoundError,
    SessionStartFailedError,
    ValidationFailedError,
)
from api.http_auth_policy import AUTHENTICATION_FAILURE_RESPONSES, require_http_principal
from api.session_route_policy import (
    require_http_session_cancel_principal,
    require_http_session_start_principal,
)
from api.schemas import (
    ApiErrorResponse,
    ApiRateLimitErrorResponse,
    CancelSessionResponse,
    SessionSnapshotResponse,
    SessionIdentifier,
    SessionSummaryResponse,
    StartSessionRequest,
)
from read_resource_policy import MAX_SESSION_SNAPSHOT_RESPONSE_BYTES
from session_service import (
    SessionServiceCancelFailedError,
    SessionServiceNotFoundError,
    SessionServiceStartFailedError,
    cancel_session as cancel_session_service,
    read_session_snapshot_or_none,
    start_session as start_session_service,
)

router = APIRouter(tags=["sessions"])

_RATE_LIMIT_RESPONSE: dict[int | str, dict[str, Any]] = {
    429: {"model": ApiRateLimitErrorResponse, "description": "Rate limit exceeded"},
}


@router.post(
    "/sessions",
    response_model=SessionSummaryResponse,
    responses={
        **AUTHENTICATION_FAILURE_RESPONSES,
        **_RATE_LIMIT_RESPONSE,
        400: {"model": ApiErrorResponse, "description": "Validation failed"},
        413: {"model": ApiErrorResponse, "description": "Request body too large"},
        422: {"model": ApiErrorResponse, "description": "Request validation failed"},
        500: {"model": ApiErrorResponse, "description": "Session start failed"},
    },
    dependencies=[Depends(require_http_session_start_principal)],
)
async def start_session(payload: StartSessionRequest) -> SessionSummaryResponse:
    """Start a session through the shared service and map API errors."""
    try:
        metadata = start_session_service(
            mode=payload.mode,
            input_path=payload.input_path,
            selected_detectors=payload.selected_detectors,
        )
    except SessionServiceStartFailedError as err:
        raise SessionStartFailedError(str(err)) from err
    except (OSError, ValueError) as err:
        raise ValidationFailedError(str(err)) from err

    return SessionSummaryResponse.model_validate(metadata.to_dict())


@router.get(
    "/sessions/{session_id}",
    response_model=SessionSnapshotResponse,
    responses={
        **AUTHENTICATION_FAILURE_RESPONSES,
        404: {"model": ApiErrorResponse, "description": "Session not found"},
        422: {"model": ApiErrorResponse, "description": "Response limit exceeded"},
    },
    dependencies=[Depends(require_http_principal)],
)
async def get_session(session_id: SessionIdentifier) -> SessionSnapshotResponse:
    """Read one complete snapshot or reject it when its HTTP response is too large."""
    try:
        snapshot = read_session_snapshot_or_none(session_id)
    except ValueError as err:
        raise ValidationFailedError(str(err)) from err
    if snapshot is None:
        raise SessionNotFoundError(session_id)
    response = SessionSnapshotResponse.model_validate(snapshot)
    if len(response.model_dump_json().encode("utf-8")) > MAX_SESSION_SNAPSHOT_RESPONSE_BYTES:
        raise ResponseLimitExceededError(
            resource="Session snapshot",
            max_bytes=MAX_SESSION_SNAPSHOT_RESPONSE_BYTES,
        )
    return response


@router.post(
    "/sessions/{session_id}/cancel",
    response_model=CancelSessionResponse,
    responses={
        **AUTHENTICATION_FAILURE_RESPONSES,
        **_RATE_LIMIT_RESPONSE,
        404: {"model": ApiErrorResponse, "description": "Session not found"},
        409: {
            "model": ApiErrorResponse,
            "description": "Cancel not allowed for current session state",
        },
    },
    dependencies=[Depends(require_http_session_cancel_principal)],
)
async def cancel_session(session_id: SessionIdentifier) -> CancelSessionResponse:
    """Request session cancellation through the shared service seam."""
    try:
        summary = cancel_session_service(session_id)
    except SessionServiceNotFoundError:
        raise SessionNotFoundError(session_id)
    except SessionServiceCancelFailedError as err:
        raise CancelFailedError(session_id, err.current_status) from err
    except ValueError as err:
        raise ValidationFailedError(str(err)) from err
    return CancelSessionResponse.model_validate(summary)
