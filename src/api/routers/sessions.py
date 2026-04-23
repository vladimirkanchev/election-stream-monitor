import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter

from api.errors import (
    CancelFailedError,
    SessionNotFoundError,
    SessionStartFailedError,
    ValidationFailedError,
)
from api.schemas import (
    ApiErrorResponse,
    CancelSessionResponse,
    SessionSnapshotResponse,
    SessionSummaryResponse,
    StartSessionRequest,
)
from session_runner import create_session_id
from session_io import read_session_snapshot, request_session_cancel
from session_models import SessionMetadata
from source_validation import validate_source_input
from stream_loader import build_api_stream_start_session_contract

router = APIRouter(tags=["sessions"])
TERMINAL_SESSION_STATUSES = {"completed", "cancelled", "failed"}


@router.post(
    "/sessions",
    response_model=SessionSummaryResponse,
    responses={
        400: {"model": ApiErrorResponse, "description": "Validation failed"},
        422: {"model": ApiErrorResponse, "description": "Request validation failed"},
        500: {"model": ApiErrorResponse, "description": "Session start failed"},
    },
)
async def start_session(payload: StartSessionRequest) -> SessionSummaryResponse:
    try:
        validated_input_path = validate_source_input(payload.mode, payload.input_path)
        if payload.mode == "api_stream":
            build_api_stream_start_session_contract(
                input_path=validated_input_path,
                selected_detectors=payload.selected_detectors,
            )
    except (OSError, ValueError) as err:
        raise ValidationFailedError(str(err)) from err

    session_id = create_session_id()
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[2] / "session_cli.py"),
        "run-session",
        "--mode",
        payload.mode,
        "--input-path",
        validated_input_path,
        "--session-id",
        session_id,
    ]
    for detector in payload.selected_detectors:
        command.extend(["--detector", detector])

    try:
        subprocess.Popen(  # noqa: S603
            command,
            cwd=str(Path(__file__).resolve().parents[2]),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as err:
        raise SessionStartFailedError(str(err)) from err

    metadata = SessionMetadata(
        session_id=session_id,
        mode=payload.mode,
        input_path=validated_input_path,
        selected_detectors=payload.selected_detectors,
        status="pending",
    )
    return SessionSummaryResponse.model_validate(metadata.to_dict())


@router.get(
    "/sessions/{session_id}",
    response_model=SessionSnapshotResponse,
    responses={
        404: {"model": ApiErrorResponse, "description": "Session not found"},
    },
)
async def get_session(session_id: str) -> SessionSnapshotResponse:
    try:
        snapshot = read_session_snapshot(session_id)
    except ValueError as err:
        raise ValidationFailedError(str(err)) from err
    if snapshot.get("session") is None:
        raise SessionNotFoundError(session_id)
    return SessionSnapshotResponse.model_validate(snapshot)


@router.post(
    "/sessions/{session_id}/cancel",
    response_model=CancelSessionResponse,
    responses={
        404: {"model": ApiErrorResponse, "description": "Session not found"},
        409: {
            "model": ApiErrorResponse,
            "description": "Cancel not allowed for current session state",
        },
    },
)
async def cancel_session(session_id: str) -> CancelSessionResponse:
    try:
        snapshot = read_session_snapshot(session_id)
    except ValueError as err:
        raise ValidationFailedError(str(err)) from err
    session = snapshot.get("session")
    if session is None:
        raise SessionNotFoundError(session_id)

    session_status = session.get("status")
    if session_status in TERMINAL_SESSION_STATUSES:
        raise CancelFailedError(session_id, str(session_status))

    try:
        request_session_cancel(session_id)
    except ValueError as err:
        raise ValidationFailedError(str(err)) from err
    return CancelSessionResponse(
        session_id=session_id,
        mode=session.get("mode"),
        input_path=session.get("input_path"),
        selected_detectors=session.get("selected_detectors", []),
        status="cancelling",
    )
