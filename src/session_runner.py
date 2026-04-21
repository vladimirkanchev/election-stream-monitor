"""Session orchestration for the current local-first monitoring runtime.

This module turns one validated input source into a persisted monitoring
session. It is responsible for:

- validating the input source contract before work starts
- expanding inputs into per-file or per-time-slice analysis units
- running detector bundles slice by slice
- persisting session progress, results, and alerts
- applying consistent lifecycle transitions on completion, cancel, or failure

The implementation is intentionally local and file-backed today, but the
meaning of a session here is meant to stay stable even if the transport layer
changes later.
"""

import inspect
import json
import subprocess
from pathlib import Path
from time import gmtime, strftime
from uuid import uuid4

from alert_rules import reset_session_rule_state
from analyzer_contract import AnalysisSlice, InputMode
import config
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
from stores import black_frame_store, blur_metrics_store
from source_validation import (
    ensure_path_within_root,
    resolve_validated_local_input_path,
    validate_local_media_size,
    validate_source_input,
)
from stream_loader import (
    ApiStreamLoader,
    cleanup_api_stream_temp_session_dir,
    build_api_stream_source_contract,
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
    metadata = SessionMetadata(
        session_id=resolved_session_id,
        mode=mode,
        input_path=str(input_path),
        selected_detectors=selected_detectors,
        status="pending",
    )
    reset_session_rule_state(resolved_session_id)
    initialize_session(metadata)
    progress = SessionProgress.initial(
        session_id=resolved_session_id,
        total_count=0,
    )
    write_session_progress(progress)
    try:
        validated_input_path = validate_source_input(mode, input_path)
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
            extra_fields={"session_end_reason": "validation_failed"},
        )
        reset_session_rule_state(resolved_session_id)
        raise

    metadata = SessionMetadata(
        session_id=resolved_session_id,
        mode=mode,
        input_path=str(validated_input_path),
        selected_detectors=selected_detectors,
        status="pending",
    )
    initialize_session(metadata)
    if mode == "api_stream":
        try:
            metadata = update_session_status(metadata, "running")
            progress = _build_progress_update(progress, status=metadata.status)
            write_session_progress(progress)
            metadata, progress = _run_api_stream_session(
                metadata=metadata,
                progress=progress,
                input_path=validated_input_path,
                session_id=resolved_session_id,
                selected_detectors=selected_detectors,
            )
            return metadata
        finally:
            reset_session_rule_state(resolved_session_id)
            cleanup_api_stream_temp_session_dir(resolved_session_id)

    try:
        input_slices = discover_input_slices(
            mode,
            validated_input_path,
            session_id=resolved_session_id,
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
            extra_fields={"session_end_reason": "validation_failed"},
        )
        reset_session_rule_state(resolved_session_id)
        raise

    progress = SessionProgress.initial(
        session_id=resolved_session_id,
        total_count=len(input_slices),
    )
    write_session_progress(progress)
    metadata = update_session_status(metadata, "running")
    progress = _build_progress_update(progress, status=metadata.status)
    write_session_progress(progress)

    try:
        for processed_count, analysis_slice in enumerate(input_slices, start=1):
            if is_session_cancel_requested(resolved_session_id):
                metadata, progress = _finalize_session_outcome(
                    metadata=metadata,
                    progress=progress,
                    status="cancelled",
                    source_kind=mode,
                    flush_stores=True,
                    log_level="info",
                    log_message="Cancelled session %s [%s]",
                )
                return metadata

            bundle = _run_analyzers_for_slice(
                analysis_slice=analysis_slice,
                mode=mode,
                session_id=resolved_session_id,
                selected_detectors=selected_detectors,
            )

            _persist_bundle_events(bundle)
            progress = _build_slice_progress(
                current=progress,
                processed_count=processed_count,
                total_count=len(input_slices),
                current_item=analysis_slice.source_name,
                bundle=bundle,
                status=metadata.status,
            )
            write_session_progress(progress)
            _cleanup_processed_api_stream_slice(analysis_slice, mode)

        metadata, progress = _finalize_session_outcome(
            metadata=metadata,
            progress=progress,
            status="completed",
            source_kind=mode,
            flush_stores=True,
            log_level="info",
            log_message="Completed session %s [%s]",
        )
    except (OSError, ValueError) as error:
        metadata, progress = _finalize_session_outcome(
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
    finally:
        reset_session_rule_state(resolved_session_id)

    return metadata


def discover_input_files(mode: InputMode, input_path: str | Path) -> list[Path]:
    """Resolve one source into concrete processable files for the chosen mode.

    For `video_segments`, playlist order wins over filesystem ordering when an
    HLS-style playlist is present. Direct malformed playlist inputs degrade to
    an empty segment list instead of being treated as playable media.
    """
    source = resolve_validated_local_input_path(mode, input_path)

    if mode == "video_segments":
        playlist_order = _discover_segment_files_from_playlist(source)
        if playlist_order:
            for segment_path in playlist_order:
                validate_local_media_size(segment_path)
            return playlist_order
        if source.is_file() and source.suffix.lower() == ".m3u8":
            return []

    patterns = SUPPORTED_PATTERNS[mode]
    if source.is_file():
        validate_local_media_size(source)
        return [source]

    discovered = sorted(
        [candidate for pattern in patterns for candidate in source.glob(pattern)],
        key=lambda item: item.stat().st_mtime,
    )
    for candidate in discovered:
        validate_local_media_size(candidate)
    return discovered


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
    if mode == "api_stream":
        return _discover_api_stream_slices(input_path, session_id=session_id)

    input_files = discover_input_files(mode, input_path)
    if mode != "video_files":
        return [
            AnalysisSlice(
                file_path=file_path,
                source_group=file_path.parent.name or file_path.name,
                source_name=file_path.name,
                window_index=index,
            )
            for index, file_path in enumerate(input_files)
        ]

    slices: list[AnalysisSlice] = []
    for file_path in input_files:
        duration_sec = _probe_video_duration(file_path)
        if duration_sec > config.LOCAL_VIDEO_MAX_DURATION_SEC:
            raise ValueError(
                f"Input video exceeds duration limit for local analysis: {file_path.name}"
            )
        if duration_sec <= 0:
            slices.append(
                AnalysisSlice(
                    file_path=file_path,
                    source_group=file_path.name,
                    source_name=f"{file_path.name} @ 00:00",
                    window_index=0,
                    window_start_sec=0.0,
                    window_duration_sec=1.0,
                )
            )
            continue

        full_windows = int(duration_sec)
        remainder = duration_sec - full_windows
        total_windows = full_windows + (1 if remainder > 1e-9 else 0)
        for window_index in range(total_windows):
            window_start_sec = float(window_index)
            window_duration_sec = min(1.0, max(0.1, duration_sec - window_start_sec))
            slices.append(
                AnalysisSlice(
                    file_path=file_path,
                    source_group=file_path.name,
                    source_name=f"{file_path.name} @ {_format_mm_ss(window_start_sec)}",
                    window_index=window_index,
                    window_start_sec=window_start_sec,
                    window_duration_sec=round(window_duration_sec, 3),
                )
            )

    return slices


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
                cleanup_result = _cleanup_processed_api_stream_slice(analysis_slice, "api_stream")
                cleanup_success_count += 1 if cleanup_result is True else 0
                cleanup_failure_count += 1 if cleanup_result is False else 0
                return _finalize_session_outcome(
                    metadata=metadata,
                    progress=progress,
                    status="cancelled",
                    source_kind="api_stream",
                    flush_stores=True,
                    log_level="info",
                    log_message="Cancelled session %s [%s]",
                    extra_fields=_build_api_stream_session_log_fields(
                        loader=loader,
                        processed_count=processed_count,
                        session_end_reason="cancel_requested_during_processing",
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
                progress = _build_slice_progress(
                    current=progress,
                    processed_count=processed_count,
                    total_count=max(loader.accepted_slice_count(), processed_count),
                    current_item=analysis_slice.source_name,
                    bundle=bundle,
                    status=metadata.status,
                )
                write_session_progress(progress)
            finally:
                cleanup_result = _cleanup_processed_api_stream_slice(analysis_slice, "api_stream")
                cleanup_success_count += 1 if cleanup_result is True else 0
                cleanup_failure_count += 1 if cleanup_result is False else 0
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
            extra_fields=_build_api_stream_session_log_fields(
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
            extra_fields=_build_api_stream_session_log_fields(
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
        extra_fields=_build_api_stream_session_log_fields(
            loader=loader,
            processed_count=processed_count,
            session_end_reason=loader.telemetry_snapshot().stop_reason or "completed",
            cleanup_success_count=cleanup_success_count,
            cleanup_failure_count=cleanup_failure_count,
        ),
    )


def _discover_segment_files_from_playlist(source: Path) -> list[Path]:
    """Return playlist-ordered `.ts` paths when an HLS playlist exists.

    Only segment entries that stay under the playlist root and resolve to an
    existing `.ts` file are accepted. Traversal-style entries are ignored so
    playlist discovery cannot escape the declared local input root.
    """
    playlist_path: Path | None = None

    if source.is_file() and source.suffix.lower() == ".m3u8":
        playlist_path = source
    elif source.is_dir():
        index_playlist = source / "index.m3u8"
        if index_playlist.exists():
            playlist_path = index_playlist

    if playlist_path is None or not playlist_path.exists():
        return []

    segment_paths: list[Path] = []
    for line in playlist_path.read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        segment_path = ensure_path_within_root(
            playlist_path.parent,
            playlist_path.parent / entry,
        )
        if segment_path and segment_path.exists() and segment_path.suffix.lower() == ".ts":
            segment_paths.append(segment_path)

    return segment_paths


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
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(file_path),
    ]
    try:
        probe = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            text=True,
            check=False,
            timeout=config.FFPROBE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe timed out while probing %s", file_path.name)
        return 0.0
    try:
        data = json.loads(probe.stdout)
        return float(data.get("format", {}).get("duration", 0.0) or 0.0)
    except (OSError, ValueError, json.JSONDecodeError):
        return 0.0


def _format_mm_ss(total_seconds: float) -> str:
    """Return a short `MM:SS` label for a slice start time."""
    safe_seconds = max(0, int(total_seconds))
    minutes = safe_seconds // 60
    seconds = safe_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def _build_progress_update(
    current: SessionProgress,
    *,
    status: SessionStatus,
    status_reason: str | None = None,
    status_detail: str | None = None,
) -> SessionProgress:
    """Return a copy of session progress with a validated lifecycle status update."""
    return SessionProgress(
        session_id=current.session_id,
        status=status,
        processed_count=current.processed_count,
        total_count=current.total_count,
        current_item=current.current_item,
        latest_result_detector=current.latest_result_detector,
        alert_count=current.alert_count,
        last_updated_utc=strftime("%Y-%m-%d %H:%M:%S", gmtime()),
        latest_result_detectors=current.latest_result_detectors,
        status_reason=status_reason or _default_progress_status_reason(status),
        status_detail=status_detail,
    )


def _build_slice_progress(
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
        last_updated_utc=strftime("%Y-%m-%d %H:%M:%S", gmtime()),
        latest_result_detectors=latest_result_detectors,
        status_reason=_default_progress_status_reason(status),
        status_detail=None,
    )


def _cleanup_processed_api_stream_slice(
    analysis_slice: AnalysisSlice,
    mode: InputMode,
) -> bool | None:
    """Remove temp media for processed live slices after analysis completes.

    Local source files remain untouched. This cleanup only applies to temp
    files created for `api_stream` loading and keeps media lifecycle outside
    detector and rule code.
    """
    if mode != "api_stream":
        return None
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
    terminal_status_reason, terminal_status_detail = _build_terminal_progress_status(
        status=status,
        source_kind=source_kind,
        error=error,
        extra_fields=extra_fields,
    )
    updated_progress = _build_progress_update(
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
            _build_session_log_context(
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
            _build_session_log_context(
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


def _build_session_log_context(
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


def _build_api_stream_session_log_fields(
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


def _default_progress_status_reason(status: SessionStatus) -> str:
    """Return the default stable reason label for non-terminal progress updates."""
    if status == "cancelled":
        return "cancel_requested"
    if status == "failed":
        return "session_runtime_error"
    return status


def _build_terminal_progress_status(
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
            # Keep the overall live-run outcome as completed while exposing
            # the bounded-idle stop as a more specific machine-readable reason.
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
            # Keep the stable failed-stream reason compact at the backend
            # contract layer. Loader/runtime specifics stay in
            # `terminal_failure_reason` and therefore surface through
            # `status_detail` until a future profile/policy branch proves that
            # a richer machine-readable split is worth the cross-layer churn.
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

    return _default_progress_status_reason(status), None


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
