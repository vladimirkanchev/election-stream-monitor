"""Shared request/response builders for the split FastAPI session adapter tests."""

from analyzer_contract import InputMode
from session_models import SessionMetadata
from session_models import SessionStatus

DEFAULT_VIDEO_FILES_INPUT = "tests/fixtures/media/video_files/black_trigger.mp4"


def session_start_request_body(
    *,
    mode: InputMode = "video_files",
    input_path: str = DEFAULT_VIDEO_FILES_INPUT,
    selected_detectors: list[str] | None = None,
) -> dict[str, object]:
    """Build a canonical POST `/sessions` request body for adapter tests."""
    return {
        "mode": mode,
        "input_path": input_path,
        "selected_detectors": selected_detectors or ["video_metrics"],
    }


def session_start_call(
    *,
    mode: InputMode = "video_files",
    input_path: str = DEFAULT_VIDEO_FILES_INPUT,
    selected_detectors: list[str] | None = None,
) -> tuple[InputMode, str, list[str]]:
    """Build the expected service call tuple derived from a start request body."""
    return (
        mode,
        input_path,
        list(selected_detectors or ["video_metrics"]),
    )


def session_start_payload(
    *,
    session_id: str,
    mode: InputMode = "video_files",
    input_path: str = DEFAULT_VIDEO_FILES_INPUT,
    selected_detectors: list[str] | None = None,
) -> dict[str, object]:
    """Build the expected pending-session payload returned by the adapter."""
    return {
        "session_id": session_id,
        "mode": mode,
        "input_path": input_path,
        "selected_detectors": list(selected_detectors or ["video_metrics"]),
        "status": "pending",
    }


def session_cancel_payload(
    *,
    session_id: str,
    mode: InputMode = "video_files",
    input_path: str = DEFAULT_VIDEO_FILES_INPUT,
    selected_detectors: list[str] | None = None,
    status: SessionStatus = "cancelling",
) -> dict[str, object]:
    """Build the canonical cancel-summary payload returned by the adapter."""
    return {
        "session_id": session_id,
        "mode": mode,
        "input_path": input_path,
        "selected_detectors": list(selected_detectors or ["video_metrics"]),
        "status": status,
    }


def session_not_found_payload(session_id: str) -> dict[str, str]:
    """Build the shared 404 payload for missing session routes."""
    return {
        "detail": "Session not found",
        "error_code": "session_not_found",
        "status_reason": "session_not_found",
        "status_detail": f"No persisted session snapshot found for session_id={session_id}",
    }


def validation_error_payload(detail: str) -> dict[str, str]:
    """Build the shared structured validation error payload."""
    return {
        "detail": detail,
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": detail,
    }


def pending_metadata(
    session_id: str,
    mode: InputMode,
    input_path: str,
    selected_detectors: list[str],
) -> SessionMetadata:
    """Create minimal pending metadata objects for route happy-path tests."""
    return SessionMetadata(
        session_id=session_id,
        mode=mode,
        input_path=input_path,
        selected_detectors=selected_detectors,
        status="pending",
    )


__all__ = [
    "DEFAULT_VIDEO_FILES_INPUT",
    "pending_metadata",
    "session_not_found_payload",
    "session_cancel_payload",
    "session_start_call",
    "session_start_payload",
    "session_start_request_body",
    "validation_error_payload",
]
