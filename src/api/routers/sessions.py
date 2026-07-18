"""FastAPI adapters for session start/read/cancel endpoints.

Keep shared session lifecycle mechanics in `session_service.py`.
Keep this module focused on:

- request/response schema binding
- HTTP-oriented error mapping
- route-level ownership of the FastAPI session surface
- shared authentication inherited by every session route

Whether a caller must present a key is resolved by the active local/share
runtime policy, not by individual route handlers.
"""

from fastapi import APIRouter, Depends

from api.errors import (
    CancelFailedError,
    SessionNotFoundError,
    SessionStartFailedError,
    ValidationFailedError,
)
from api.http_auth_policy import (
    AUTHENTICATION_FAILURE_RESPONSES,
    require_http_principal,
)
from api.schemas import (
    ApiErrorResponse,
    CancelSessionResponse,
    SessionSnapshotResponse,
    SessionSummaryResponse,
    StartSessionRequest,
)
from session_service import (
    SessionServiceCancelFailedError,
    SessionServiceNotFoundError,
    SessionServiceStartFailedError,
    cancel_session as cancel_session_service,
    read_session_snapshot_or_none,
    start_session as start_session_service,
)

router = APIRouter(
    tags=["sessions"],
    dependencies=[Depends(require_http_principal)],
)


@router.post(
    "/sessions",
    response_model=SessionSummaryResponse,
    responses={
        **AUTHENTICATION_FAILURE_RESPONSES,
        400: {"model": ApiErrorResponse, "description": "Validation failed"},
        422: {"model": ApiErrorResponse, "description": "Request validation failed"},
        500: {"model": ApiErrorResponse, "description": "Session start failed"},
    },
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
    },
)
async def get_session(session_id: str) -> SessionSnapshotResponse:
    """Read one session snapshot through the shared service seam."""
    try:
        snapshot = read_session_snapshot_or_none(session_id)
    except ValueError as err:
        raise ValidationFailedError(str(err)) from err
    if snapshot is None:
        raise SessionNotFoundError(session_id)
    return SessionSnapshotResponse.model_validate(snapshot)


@router.post(
    "/sessions/{session_id}/cancel",
    response_model=CancelSessionResponse,
    responses={
        **AUTHENTICATION_FAILURE_RESPONSES,
        404: {"model": ApiErrorResponse, "description": "Session not found"},
        409: {
            "model": ApiErrorResponse,
            "description": "Cancel not allowed for current session state",
        },
    },
)
async def cancel_session(session_id: str) -> CancelSessionResponse:
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
