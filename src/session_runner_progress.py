"""Progress and terminal-status helpers for `session_runner`.

This module keeps progress snapshots and operator-facing terminal status/log
fields consistent across local and `api_stream` runs. It owns:

- progress snapshot updates for running and per-slice execution
- stable terminal `status_reason` and `status_detail` mapping
- compact session log context for completion, cancel, and failure outcomes
"""

from __future__ import annotations

from time import gmtime, strftime

from analyzer_contract import InputMode
from logger import format_log_context
from session_models import SessionMetadata, SessionProgress, SessionStatus
from stream_loader import ApiStreamLoader


def build_progress_update(
    current: SessionProgress,
    *,
    status: SessionStatus,
    status_reason: str | None = None,
    status_detail: str | None = None,
) -> SessionProgress:
    """Return a copy of session progress with a validated lifecycle update."""
    return SessionProgress(
        session_id=current.session_id,
        status=status,
        processed_count=current.processed_count,
        total_count=current.total_count,
        current_item=current.current_item,
        latest_result_detector=current.latest_result_detector,
        alert_count=current.alert_count,
        last_updated_utc=_current_utc_timestamp(),
        latest_result_detectors=current.latest_result_detectors,
        status_reason=status_reason or default_progress_status_reason(status),
        status_detail=status_detail,
    )


def build_slice_progress(
    *,
    current: SessionProgress,
    processed_count: int,
    total_count: int,
    current_item: str,
    bundle: dict[str, list[dict[str, object]]],
    status: SessionStatus,
) -> SessionProgress:
    """Build the next progress payload after processing one input slice."""
    latest_result_detectors = [
        str(result_payload["detector_id"])
        for result_payload in bundle["results"]
    ]
    latest_result_detector = (
        latest_result_detectors[-1] if latest_result_detectors else None
    )
    return SessionProgress(
        session_id=current.session_id,
        status=status,
        processed_count=processed_count,
        total_count=total_count,
        current_item=current_item,
        latest_result_detector=latest_result_detector,
        alert_count=current.alert_count + len(bundle["alerts"]),
        last_updated_utc=_current_utc_timestamp(),
        latest_result_detectors=latest_result_detectors,
        status_reason=default_progress_status_reason(status),
        status_detail=None,
    )


def build_session_log_context(
    metadata: SessionMetadata,
    progress: SessionProgress,
    source_kind: InputMode,
    *,
    extra_fields: dict[str, object] | None = None,
) -> str:
    """Build consistent lifecycle context for session outcome logs."""
    fields: dict[str, object] = {
        "session_id": metadata.session_id,
        "source_kind": source_kind,
        "current_item": progress.current_item,
    }
    if extra_fields:
        fields.update(extra_fields)
    return format_log_context(**fields)


def build_api_stream_session_log_fields(
    *,
    loader: ApiStreamLoader,
    processed_count: int,
    session_end_reason: str,
    cleanup_success_count: int,
    cleanup_failure_count: int,
) -> dict[str, object]:
    """Return one compact transport/session summary for api_stream end logs."""
    telemetry = loader.telemetry_snapshot()
    return {
        "session_end_reason": session_end_reason,
        "source_url_class": telemetry.source_url_class,
        "playlist_refresh_count": telemetry.playlist_refresh_count,
        "processed_chunk_count": processed_count,
        "skipped_replay_count": telemetry.skipped_replay_count,
        "reconnect_attempt_count": telemetry.reconnect_attempt_count,
        "reconnect_budget_exhaustion_count": telemetry.reconnect_budget_exhaustion_count,
        "terminal_failure_reason": telemetry.terminal_failure_reason,
        "temp_cleanup_success_count": cleanup_success_count,
        "temp_cleanup_failure_count": cleanup_failure_count,
    }


def default_progress_status_reason(status: SessionStatus) -> str:
    """Return the default stable reason label for non-terminal progress updates."""
    if status == "cancelled":
        return "cancel_requested"
    if status == "failed":
        return "session_runtime_error"
    return status


def build_terminal_progress_status(
    *,
    status: SessionStatus,
    source_kind: InputMode,
    error: Exception | None,
    extra_fields: dict[str, object] | None,
) -> tuple[str, str | None]:
    """Return stable terminal progress reason/detail values for persisted snapshots."""
    session_end_reason = _coerce_optional_string(
        extra_fields.get("session_end_reason") if extra_fields else None
    )

    if status == "cancelled":
        if session_end_reason == "cancel_requested_during_processing":
            return "cancel_requested", "Cancellation requested during slice processing"
        if session_end_reason == "cancel_requested_after_iteration":
            return "cancel_requested", "Cancellation requested after iteration"
        return "cancel_requested", "Cancellation requested by client"

    if status == "completed":
        if session_end_reason == "idle_poll_budget_exhausted":
            return "idle_poll_budget_exhausted", "Idle poll budget exhausted"
        if session_end_reason and session_end_reason != "completed":
            return "completed", _humanize_session_end_reason(session_end_reason)
        return "completed", None

    if status == "failed":
        terminal_failure_reason = _coerce_optional_string(
            extra_fields.get("terminal_failure_reason") if extra_fields else None
        )
        if session_end_reason == "validation_failed":
            if error is not None:
                return "validation_failed", str(error)
            if terminal_failure_reason:
                return "validation_failed", terminal_failure_reason
            return "validation_failed", "Session input validation failed"
        if source_kind == "api_stream":
            if terminal_failure_reason:
                return "source_unreachable", terminal_failure_reason
            if error is not None:
                return "source_unreachable", str(error)
            return "source_unreachable", "Live source became unavailable during session"
        if terminal_failure_reason:
            return session_end_reason or "session_runtime_error", terminal_failure_reason
        if error is not None:
            return session_end_reason or "session_runtime_error", str(error)
        return (
            session_end_reason or "session_runtime_error",
            "Session failed during execution",
        )

    return default_progress_status_reason(status), None


def _humanize_session_end_reason(reason: str) -> str:
    """Return a readable snapshot detail for a transport-specific end reason."""
    words = reason.replace("_", " ").strip()
    if not words:
        return "Session ended"
    return words[0].upper() + words[1:]


def _coerce_optional_string(value: object) -> str | None:
    """Return a string when the value is meaningfully populated."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _current_utc_timestamp() -> str:
    """Return the persisted UTC timestamp format used by session progress."""
    return strftime("%Y-%m-%d %H:%M:%S", gmtime())
