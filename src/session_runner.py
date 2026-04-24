"""Session orchestration for the current local-first monitoring runtime.

This module is the coordination layer for one monitoring session. It keeps the
high-level lifecycle readable by owning:

- validation and pending-to-running lifecycle transitions
- per-mode execution flow for local inputs and `api_stream`
- analyzer execution, event persistence, and terminal outcome handling

It intentionally delegates lower-level concerns to focused helpers:

- `session_runner_discovery` for local file discovery and slice expansion
- `session_runner_progress` for progress/status payload shaping and log context

The implementation remains local and file-backed today, but the meaning of a
session here is intended to stay stable even if transport details change later.
"""

import inspect
from pathlib import Path
from time import gmtime, strftime
from uuid import uuid4

from alert_rules import reset_session_rule_state
from analyzer_contract import AnalysisSlice, InputMode
from logger import format_log_context, get_logger
from processor import run_enabled_analyzers_bundle
from session_io import (
    append_alert,
    append_result,
    initialize_session,
    is_session_cancel_requested,
    update_session_status,
    write_session_progress,
)
from session_models import (
    AlertEvent,
    ResultEvent,
    SessionMetadata,
    SessionProgress,
    SessionStatus,
)
import session_runner_discovery
import session_runner_progress
from stores import black_frame_store, blur_metrics_store
from source_validation import (
    validate_source_input,
)
from stream_loader import (
    ApiStreamLoader,
    build_api_stream_source_contract,
    cleanup_api_stream_temp_session_dir,
    create_api_stream_loader,
    iter_api_stream_slices,
)

logger = get_logger(__name__)
METRIC_STORES = (black_frame_store, blur_metrics_store)

SUPPORTED_PATTERNS: dict[InputMode, tuple[str, ...]] = {
    "video_segments": ("*.ts",),
    "video_files": ("*.mp4",),
    "api_stream": (),
}


def create_session_id() -> str:
    """Create a stable session id for one monitoring run."""
    return f"session-{strftime('%Y%m%d-%H%M%S', gmtime())}-{uuid4().hex[:8]}"


def run_local_session(
    mode: InputMode,
    input_path: str | Path,
    selected_detectors: list[str],
    session_id: str | None = None,
) -> SessionMetadata:
    """Execute one monitoring session and persist the full session lifecycle.

    The runner validates the source, creates the initial session files, expands
    the input into analysis slices, and then processes those slices one by one.
    Detector output and alerts are persisted incrementally so the frontend can
    poll a stable session snapshot while the run is still active.
    """
    resolved_session_id = session_id or create_session_id()
    metadata, progress = _initialize_pending_session(
        mode=mode,
        input_path=input_path,
        selected_detectors=selected_detectors,
        session_id=resolved_session_id,
    )
    reset_session_rule_state(resolved_session_id)
    try:
        validated_input_path = validate_source_input(mode, input_path)
    except (OSError, ValueError) as error:
        _finalize_validation_failure(
            metadata=metadata,
            progress=progress,
            source_kind=mode,
            error=error,
        )
        raise

    metadata = _build_pending_metadata(
        session_id=resolved_session_id,
        mode=mode,
        input_path=validated_input_path,
        selected_detectors=selected_detectors,
    )
    initialize_session(metadata)

    try:
        if mode == "api_stream":
            return _run_validated_api_stream_session(
                metadata=metadata,
                progress=progress,
                input_path=validated_input_path,
                session_id=resolved_session_id,
                selected_detectors=selected_detectors,
            )

        return _run_validated_local_slice_session(
            metadata=metadata,
            progress=progress,
            input_path=validated_input_path,
            session_id=resolved_session_id,
            selected_detectors=selected_detectors,
        )
    finally:
        reset_session_rule_state(resolved_session_id)
        if mode == "api_stream":
            cleanup_api_stream_temp_session_dir(resolved_session_id)


def _build_pending_metadata(
    *,
    session_id: str,
    mode: InputMode,
    input_path: str | Path,
    selected_detectors: list[str],
) -> SessionMetadata:
    """Return one pending metadata snapshot for the current input path."""
    return SessionMetadata(
        session_id=session_id,
        mode=mode,
        input_path=str(input_path),
        selected_detectors=selected_detectors,
        status="pending",
    )


def _initialize_pending_session(
    *,
    mode: InputMode,
    input_path: str | Path,
    selected_detectors: list[str],
    session_id: str,
) -> tuple[SessionMetadata, SessionProgress]:
    """Persist the initial pending session metadata and progress snapshots."""
    metadata = _build_pending_metadata(
        session_id=session_id,
        mode=mode,
        input_path=input_path,
        selected_detectors=selected_detectors,
    )
    initialize_session(metadata)
    progress = SessionProgress.initial(session_id=session_id, total_count=0)
    write_session_progress(progress)
    return metadata, progress


def _finalize_validation_failure(
    *,
    metadata: SessionMetadata,
    progress: SessionProgress,
    source_kind: InputMode,
    error: Exception,
) -> None:
    """Persist one validation failure consistently before re-raising it."""
    _finalize_session_outcome(
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


def _start_running_session(
    metadata: SessionMetadata,
    progress: SessionProgress,
    *,
    total_count: int,
) -> tuple[SessionMetadata, SessionProgress]:
    """Transition a validated pending session into its running lifecycle state."""
    initialized_progress = SessionProgress.initial(
        session_id=progress.session_id,
        total_count=total_count,
    )
    write_session_progress(initialized_progress)
    updated_metadata = update_session_status(metadata, "running")
    updated_progress = session_runner_progress.build_progress_update(
        initialized_progress,
        status=updated_metadata.status,
    )
    write_session_progress(updated_progress)
    return updated_metadata, updated_progress


def _run_validated_api_stream_session(
    *,
    metadata: SessionMetadata,
    progress: SessionProgress,
    input_path: str | Path,
    session_id: str,
    selected_detectors: list[str],
) -> SessionMetadata:
    """Run one already-validated live session through the loader seam."""
    running_metadata, running_progress = _start_running_session(
        metadata,
        progress,
        total_count=0,
    )
    updated_metadata, _ = _run_api_stream_session(
        metadata=running_metadata,
        progress=running_progress,
        input_path=input_path,
        session_id=session_id,
        selected_detectors=selected_detectors,
    )
    return updated_metadata


def _run_validated_local_slice_session(
    *,
    metadata: SessionMetadata,
    progress: SessionProgress,
    input_path: str | Path,
    session_id: str,
    selected_detectors: list[str],
) -> SessionMetadata:
    """Discover local slices and process them through the shared session loop."""
    try:
        input_slices = discover_input_slices(
            metadata.mode,
            input_path,
            session_id=session_id,
        )
    except (OSError, ValueError) as error:
        _finalize_validation_failure(
            metadata=metadata,
            progress=progress,
            source_kind=metadata.mode,
            error=error,
        )
        raise

    running_metadata, running_progress = _start_running_session(
        metadata,
        progress,
        total_count=len(input_slices),
    )
    updated_metadata, _ = _process_discovered_slices(
        metadata=running_metadata,
        progress=running_progress,
        mode=metadata.mode,
        session_id=session_id,
        selected_detectors=selected_detectors,
        input_slices=input_slices,
    )
    return updated_metadata


def _process_discovered_slices(
    *,
    metadata: SessionMetadata,
    progress: SessionProgress,
    mode: InputMode,
    session_id: str,
    selected_detectors: list[str],
    input_slices: list[AnalysisSlice],
) -> tuple[SessionMetadata, SessionProgress]:
    """Process one finite list of discovered local slices."""
    try:
        for processed_count, analysis_slice in enumerate(input_slices, start=1):
            if is_session_cancel_requested(session_id):
                return _finalize_session_outcome(
                    metadata=metadata,
                    progress=progress,
                    status="cancelled",
                    source_kind=mode,
                    flush_stores=True,
                    log_level="info",
                    log_message="Cancelled session %s [%s]",
                )

            bundle = _run_analyzers_for_slice(
                analysis_slice=analysis_slice,
                mode=mode,
                session_id=session_id,
                selected_detectors=selected_detectors,
            )

            _persist_bundle_events(bundle)
            progress = session_runner_progress.build_slice_progress(
                current=progress,
                processed_count=processed_count,
                total_count=len(input_slices),
                current_item=analysis_slice.source_name,
                bundle=bundle,
                status=metadata.status,
            )
            write_session_progress(progress)

        return _finalize_session_outcome(
            metadata=metadata,
            progress=progress,
            status="completed",
            source_kind=mode,
            flush_stores=True,
            log_level="info",
            log_message="Completed session %s [%s]",
        )
    except (OSError, ValueError) as error:
        _finalize_session_outcome(
            metadata=metadata,
            progress=progress,
            status="failed",
            source_kind=mode,
            flush_stores=False,
            log_level="error",
            log_message="Session %s failed: %s [%s]",
            error=error,
        )
        raise


def discover_input_files(mode: InputMode, input_path: str | Path) -> list[Path]:
    """Resolve one source into concrete processable files for the chosen mode.

    For `video_segments`, playlist order wins over filesystem ordering when an
    HLS-style playlist is present. Direct malformed playlist inputs degrade to
    an empty segment list instead of being treated as playable media.
    """
    return session_runner_discovery.discover_input_files(
        mode,
        input_path,
        supported_patterns=SUPPORTED_PATTERNS,
    )


def discover_input_slices(
    mode: InputMode,
    input_path: str | Path,
    session_id: str | None = None,
) -> list[AnalysisSlice]:
    """Expand local inputs into temporal slices.

    `.ts` segment inputs remain one slice per file. `.mp4` inputs are expanded
    into roughly 1-second windows so detector output and alert rules operate on
    the same time-based model as HLS segments.

    `api_stream` is intentionally routed through a dedicated loader seam so
    live connection and chunk-yielding behavior can evolve without being baked
    directly into the session runner.

    This is an important current-stage behavior: progress and alert timing for
    `video_files` is slice-based, not "one whole file equals one analysis unit".
    """
    return session_runner_discovery.discover_input_slices(
        mode,
        input_path,
        supported_patterns=SUPPORTED_PATTERNS,
        duration_probe=_probe_video_duration,
        api_stream_slice_discoverer=_discover_api_stream_slices,
        session_id=session_id,
    )


def get_api_stream_loader(session_id: str | None = None) -> ApiStreamLoader:
    """Return the backend loader responsible for future live-stream fetching.

    This small factory keeps the session runner independent from the concrete
    implementation. Tests can swap in fake loaders, and later a real HTTP/HLS
    loader can be introduced without rewriting detector or rule code.
    """
    return create_api_stream_loader(session_id=session_id)


def _discover_api_stream_slices(
    input_path: str | Path,
    session_id: str | None = None,
) -> list[AnalysisSlice]:
    """Materialize live-analysis slices through the dedicated loader seam."""
    source = build_api_stream_source_contract(str(input_path))
    loader = get_api_stream_loader(session_id=session_id)
    return list(iter_api_stream_slices(loader, source))


def _run_api_stream_session(
    *,
    metadata: SessionMetadata,
    progress: SessionProgress,
    input_path: str | Path,
    session_id: str,
    selected_detectors: list[str],
) -> tuple[SessionMetadata, SessionProgress]:
    """Process live slices incrementally as the loader yields them.

    Unlike local file modes, `api_stream` should not collect all slices up
    front. The runner consumes one slice at a time so the session behaves like
    a real live stream while preserving the existing detector/rule/persistence
    model.
    """
    source = build_api_stream_source_contract(str(input_path))
    loader = get_api_stream_loader(session_id=session_id)
    processed_count = progress.processed_count
    cleanup_success_count = 0
    cleanup_failure_count = 0
    try:
        for analysis_slice in iter_api_stream_slices(loader, source):
            if is_session_cancel_requested(session_id):
                return _finalize_session_outcome(
                    metadata=metadata,
                    progress=progress,
                    status="cancelled",
                    source_kind="api_stream",
                    flush_stores=True,
                    log_level="info",
                    log_message="Cancelled session %s [%s]",
                    extra_fields=_build_api_stream_outcome_fields(
                        loader=loader,
                        processed_count=processed_count,
                        session_end_reason="cancel_requested_during_processing",
                        analysis_slice=analysis_slice,
                        cleanup_success_count=cleanup_success_count,
                        cleanup_failure_count=cleanup_failure_count,
                    ),
                )

            try:
                bundle = _run_analyzers_for_slice(
                    analysis_slice=analysis_slice,
                    mode="api_stream",
                    session_id=session_id,
                    selected_detectors=selected_detectors,
                )
                processed_count += 1
                _persist_bundle_events(bundle)
                progress = session_runner_progress.build_slice_progress(
                    current=progress,
                    processed_count=processed_count,
                    total_count=max(loader.accepted_slice_count(), processed_count),
                    current_item=analysis_slice.source_name,
                    bundle=bundle,
                    status=metadata.status,
                )
                write_session_progress(progress)
            finally:
                cleanup_success_count, cleanup_failure_count = _record_api_stream_cleanup(
                    analysis_slice,
                    cleanup_success_count=cleanup_success_count,
                    cleanup_failure_count=cleanup_failure_count,
                )
    except (OSError, ValueError) as error:
        metadata, progress = _finalize_session_outcome(
            metadata=metadata,
            progress=progress,
            status="failed",
            source_kind="api_stream",
            flush_stores=False,
            log_level="error",
            log_message="Session %s failed: %s [%s]",
            error=error,
            extra_fields=session_runner_progress.build_api_stream_session_log_fields(
                loader=loader,
                processed_count=processed_count,
                session_end_reason="terminal_failure",
                cleanup_success_count=cleanup_success_count,
                cleanup_failure_count=cleanup_failure_count,
            ),
        )
        raise

    if is_session_cancel_requested(session_id):
        return _finalize_session_outcome(
            metadata=metadata,
            progress=progress,
            status="cancelled",
            source_kind="api_stream",
            flush_stores=True,
            log_level="info",
            log_message="Cancelled session %s [%s]",
            extra_fields=session_runner_progress.build_api_stream_session_log_fields(
                loader=loader,
                processed_count=processed_count,
                session_end_reason="cancel_requested_after_iteration",
                cleanup_success_count=cleanup_success_count,
                cleanup_failure_count=cleanup_failure_count,
            ),
        )

    return _finalize_session_outcome(
        metadata=metadata,
        progress=progress,
        status="completed",
        source_kind="api_stream",
        flush_stores=True,
        log_level="info",
        log_message="Completed session %s [%s]",
        extra_fields=session_runner_progress.build_api_stream_session_log_fields(
            loader=loader,
            processed_count=processed_count,
            session_end_reason=loader.telemetry_snapshot().stop_reason or "completed",
            cleanup_success_count=cleanup_success_count,
            cleanup_failure_count=cleanup_failure_count,
        ),
    )


def _run_analyzers_for_slice(
    analysis_slice: AnalysisSlice,
    mode: InputMode,
    session_id: str,
    selected_detectors: list[str],
) -> dict[str, list[dict[str, object]]]:
    """Call the analyzer bundle while preserving compatibility with test doubles."""
    kwargs = {
        "file_path": analysis_slice.file_path,
        "prefix": analysis_slice.file_path.parent.name,
        "mode": mode,
        "session_id": session_id,
        "selected_analyzers": set(selected_detectors),
        "persist_to_store": True,
        "analysis_slice": analysis_slice,
    }
    accepted = inspect.signature(run_enabled_analyzers_bundle).parameters
    filtered_kwargs = {
        key: value
        for key, value in kwargs.items()
        if key in accepted
    }
    return run_enabled_analyzers_bundle(**filtered_kwargs)


def _probe_video_duration(file_path: Path) -> float:
    """Return container duration in seconds or ``0.0`` if probing fails."""
    return session_runner_discovery.probe_video_duration(file_path)


def _record_api_stream_cleanup(
    analysis_slice: AnalysisSlice,
    *,
    cleanup_success_count: int,
    cleanup_failure_count: int,
) -> tuple[int, int]:
    """Apply temp-file cleanup for one live slice and update summary counters."""
    cleanup_result = _cleanup_processed_api_stream_slice(analysis_slice)
    cleanup_success_count += 1 if cleanup_result is True else 0
    cleanup_failure_count += 1 if cleanup_result is False else 0
    return cleanup_success_count, cleanup_failure_count


def _cleanup_processed_api_stream_slice(analysis_slice: AnalysisSlice) -> bool:
    """Remove one processed `api_stream` temp file after analysis completes."""
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


def _build_api_stream_outcome_fields(
    *,
    loader: ApiStreamLoader,
    processed_count: int,
    session_end_reason: str,
    analysis_slice: AnalysisSlice | None = None,
    cleanup_success_count: int,
    cleanup_failure_count: int,
) -> dict[str, object]:
    """Build one api_stream completion/cancel/failure summary payload."""
    if analysis_slice is not None:
        cleanup_success_count, cleanup_failure_count = _record_api_stream_cleanup(
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


def _persist_bundle_events(bundle: dict[str, list[dict[str, object]]]) -> None:
    """Persist one analyzer bundle into the session event logs."""
    for result_payload in bundle["results"]:
        append_result(ResultEvent(**result_payload))

    for alert_payload in bundle["alerts"]:
        append_alert(AlertEvent(**alert_payload))


def _finalize_session_outcome(
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
    """Persist one terminal session outcome and log it consistently."""
    if flush_stores:
        _flush_metric_stores()

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

    log_args: tuple[object, ...]
    if error is None:
        log_args = (
            updated_metadata.session_id,
            session_runner_progress.build_session_log_context(
                updated_metadata,
                updated_progress,
                source_kind,
                extra_fields=extra_fields,
            ),
        )
    else:
        log_args = (
            updated_metadata.session_id,
            error,
            session_runner_progress.build_session_log_context(
                updated_metadata,
                updated_progress,
                source_kind,
                extra_fields=extra_fields,
            ),
        )
    getattr(logger, log_level)(log_message, *log_args)
    return updated_metadata, updated_progress


def _flush_metric_stores() -> None:
    """Flush all detector metric stores used by the session runner."""
    for store in METRIC_STORES:
        store.flush()
