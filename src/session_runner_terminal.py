"""Terminal persistence, cleanup, and logging helpers for `session_runner`.

This module owns what happens when a session ends:

- map the terminal state into persisted progress fields
- flush detector stores when required
- delete processed `api_stream` temp files
- emit one operator-facing terminal log entry
"""

from __future__ import annotations

from analyzer_contract import AnalysisSlice, InputMode
from logger import format_log_context, get_logger
from session_io import update_session_status, write_session_progress
from session_models import SessionMetadata, SessionProgress, SessionStatus
import session_runner_progress
from stores import black_frame_store, blur_metrics_store
from stream_loader import ApiStreamLoader

logger = get_logger(__name__)
METRIC_STORES = (black_frame_store, blur_metrics_store)


def finalize_validation_failure(
    *,
    metadata: SessionMetadata,
    progress: SessionProgress,
    source_kind: InputMode,
    error: Exception,
) -> None:
    """Persist a validation failure before the caller re-raises it."""
    finalize_session_outcome(
        metadata=metadata,
        progress=progress,
        status="failed",
        source_kind=source_kind,
        flush_stores=False,
        log_level="error",
        log_message="Session %s failed: %s [%s]",
        error=error,
        extra_fields={"session_end_reason": "validation_failed"},
    )


def record_api_stream_cleanup(
    analysis_slice: AnalysisSlice,
    *,
    cleanup_success_count: int,
    cleanup_failure_count: int,
) -> tuple[int, int]:
    """Clean one processed live slice and update cleanup summary counters."""
    cleanup_result = cleanup_processed_api_stream_slice(analysis_slice)
    cleanup_success_count += 1 if cleanup_result is True else 0
    cleanup_failure_count += 1 if cleanup_result is False else 0
    return cleanup_success_count, cleanup_failure_count


def cleanup_processed_api_stream_slice(analysis_slice: AnalysisSlice) -> bool:
    """Delete one processed `api_stream` temp file after analysis completes."""
    try:
        if analysis_slice.file_path.exists():
            analysis_slice.file_path.unlink()
        return True
    except OSError:
        logger.warning(
            "Failed to delete processed api_stream temp file [%s]",
            format_log_context(current_item=analysis_slice.source_name),
        )
        return False


def build_api_stream_outcome_fields(
    *,
    loader: ApiStreamLoader,
    processed_count: int,
    session_end_reason: str,
    analysis_slice: AnalysisSlice | None = None,
    cleanup_success_count: int,
    cleanup_failure_count: int,
) -> dict[str, object]:
    """Build the terminal summary payload for an `api_stream` session."""
    if analysis_slice is not None:
        cleanup_success_count, cleanup_failure_count = record_api_stream_cleanup(
            analysis_slice,
            cleanup_success_count=cleanup_success_count,
            cleanup_failure_count=cleanup_failure_count,
        )
    return session_runner_progress.build_api_stream_session_log_fields(
        loader=loader,
        processed_count=processed_count,
        session_end_reason=session_end_reason,
        cleanup_success_count=cleanup_success_count,
        cleanup_failure_count=cleanup_failure_count,
    )


def finalize_session_outcome(
    *,
    metadata: SessionMetadata,
    progress: SessionProgress,
    status: SessionStatus,
    source_kind: InputMode,
    flush_stores: bool,
    log_level: str,
    log_message: str,
    error: Exception | None = None,
    extra_fields: dict[str, object] | None = None,
) -> tuple[SessionMetadata, SessionProgress]:
    """Persist the terminal session outcome and emit the matching log."""
    if flush_stores:
        flush_metric_stores()

    updated_metadata = update_session_status(metadata, status)
    terminal_status_reason, terminal_status_detail = session_runner_progress.build_terminal_progress_status(
        status=status,
        source_kind=source_kind,
        error=error,
        extra_fields=extra_fields,
    )
    updated_progress = session_runner_progress.build_progress_update(
        progress,
        status=updated_metadata.status,
        status_reason=terminal_status_reason,
        status_detail=terminal_status_detail,
    )
    write_session_progress(updated_progress)

    getattr(logger, log_level)(
        log_message,
        *_build_terminal_log_args(
            metadata=updated_metadata,
            progress=updated_progress,
            source_kind=source_kind,
            error=error,
            extra_fields=extra_fields,
        ),
    )
    return updated_metadata, updated_progress


def flush_metric_stores() -> None:
    """Flush the detector metric stores used by the session runner."""
    for store in METRIC_STORES:
        store.flush()


def _build_terminal_log_args(
    *,
    metadata: SessionMetadata,
    progress: SessionProgress,
    source_kind: InputMode,
    error: Exception | None,
    extra_fields: dict[str, object] | None,
) -> tuple[object, ...]:
    """Build the logger argument tuple for one terminal outcome."""
    log_context = session_runner_progress.build_session_log_context(
        metadata,
        progress,
        source_kind,
        extra_fields=extra_fields,
    )
    if error is None:
        return metadata.session_id, log_context
    return metadata.session_id, error, log_context
