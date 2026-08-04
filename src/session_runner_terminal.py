"""Persist terminal session state and related cleanup for `session_runner`.

This module owns the end-of-session work: map terminal state into durable
metadata and progress, flush metric stores when needed, clean processed
`api_stream` temp files, and emit the matching operator log.
"""

from __future__ import annotations

import session_runner_progress
from analyzer_contract import AnalysisSlice, InputMode
from logger import format_log_context, get_logger
from session_models import SessionMetadata, SessionProgress, SessionStatus
from session_store import SessionStore
from session_store_runtime import get_default_session_store
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
    session_store: SessionStore | None = None,
) -> None:
    """Persist a validation failure before the caller re-raises the error."""
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
        session_store=session_store,
    )


def record_api_stream_cleanup(
    analysis_slice: AnalysisSlice,
    *,
    cleanup_success_count: int,
    cleanup_failure_count: int,
) -> tuple[int, int]:
    """Delete one processed live slice and update cleanup counters."""
    cleanup_result = cleanup_processed_api_stream_slice(analysis_slice)
    cleanup_success_count += 1 if cleanup_result is True else 0
    cleanup_failure_count += 1 if cleanup_result is False else 0
    return cleanup_success_count, cleanup_failure_count


def cleanup_processed_api_stream_slice(analysis_slice: AnalysisSlice) -> bool:
    """Delete one processed `api_stream` temp file after analysis."""
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
    """Build terminal log fields for one `api_stream` outcome."""
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
    session_store: SessionStore | None = None,
) -> tuple[SessionMetadata, SessionProgress]:
    """Persist the terminal outcome, then emit the matching log record."""
    session_store = session_store or get_default_session_store()
    if flush_stores:
        flush_metric_stores()

    updated_metadata = metadata.transition_to(status)
    session_store.write_metadata(updated_metadata)
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
    updated_progress = session_runner_progress.persist_progress_if_changed(
        current=progress,
        next_progress=updated_progress,
        write_progress=session_store.write_progress,
    )

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
    """Flush detector metric stores that accumulate session-scoped state."""
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
    """Build the logger argument tuple for one terminal session outcome."""
    log_context = session_runner_progress.build_session_log_context(
        metadata,
        progress,
        source_kind,
        extra_fields=extra_fields,
    )
    if error is None:
        return metadata.session_id, log_context
    return metadata.session_id, error, log_context
