"""Top-level session orchestration for the local-first monitoring runtime.

Read this module first when you need the end-to-end flow for one session:

1. create the pending session files
2. validate the chosen source
3. dispatch to local-slice or `api_stream` execution
4. reset session-local rule state and clean temp files on exit

This file stays intentionally small. Detailed responsibilities live in:

- `session_runner_lifecycle` for pending/running state transitions
- `session_runner_execution` for finite and live processing loops
- `session_runner_terminal` for terminal persistence, cleanup, and logs
- `session_runner_discovery` for local file and slice expansion
"""

from pathlib import Path
from time import gmtime, strftime
from uuid import uuid4

from alert_rules import reset_session_rule_state
from analyzer_contract import AnalysisSlice, InputMode
from processor import run_enabled_analyzers_bundle
from session_models import SessionMetadata, SessionProgress
import session_runner_discovery
import session_runner_execution
import session_runner_lifecycle
import session_runner_terminal
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

SUPPORTED_PATTERNS: dict[InputMode, tuple[str, ...]] = {
    "video_segments": ("*.ts",),
    "video_files": ("*.mp4",),
    "api_stream": (),
}

# Compatibility re-exports for existing test seams that still patch store flushes
# and logging via `session_runner.<name>`.
black_frame_store = session_runner_terminal.black_frame_store
blur_metrics_store = session_runner_terminal.blur_metrics_store
logger = session_runner_terminal.logger


def create_session_id() -> str:
    """Create a stable session id for one monitoring run.

    Keep this public helper on `session_runner` as a stable import seam for
    callers that need a runner-owned session id without depending on deeper
    helper-module placement.
    """
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
    metadata, progress = session_runner_lifecycle.initialize_pending_session(
        mode=mode,
        input_path=input_path,
        selected_detectors=selected_detectors,
        session_id=resolved_session_id,
    )
    reset_session_rule_state(resolved_session_id)
    validated_input_path = _validate_source_or_finalize(
        mode=mode,
        input_path=input_path,
        metadata=metadata,
        progress=progress,
    )

    metadata = session_runner_lifecycle.persist_pending_metadata(
        session_id=resolved_session_id,
        mode=mode,
        input_path=validated_input_path,
        selected_detectors=selected_detectors,
    )

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
        _cleanup_session_runtime(
            session_id=resolved_session_id,
            mode=mode,
        )


def _run_validated_api_stream_session(
    *,
    metadata: SessionMetadata,
    progress: SessionProgress,
    input_path: str | Path,
    session_id: str,
    selected_detectors: list[str],
) -> SessionMetadata:
    """Run one already-validated `api_stream` session."""
    running_metadata, running_progress = session_runner_lifecycle.start_running_session(
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
    """Run one already-validated local-file session."""
    input_slices = _discover_local_slices_or_finalize(
        metadata=metadata,
        progress=progress,
        input_path=input_path,
        session_id=session_id,
    )

    running_metadata, running_progress = session_runner_lifecycle.start_running_session(
        metadata,
        progress,
        total_count=len(input_slices),
    )
    updated_metadata, _ = session_runner_execution.process_discovered_slices(
        metadata=running_metadata,
        progress=running_progress,
        mode=metadata.mode,
        session_id=session_id,
        selected_detectors=selected_detectors,
        input_slices=input_slices,
        bundle_runner=run_enabled_analyzers_bundle,
    )
    return updated_metadata


def discover_input_files(mode: InputMode, input_path: str | Path) -> list[Path]:
    """Resolve one source into concrete processable files for the chosen mode.

    For `video_segments`, playlist order wins over filesystem ordering when an
    HLS-style playlist is present. Direct malformed playlist inputs degrade to
    an empty segment list instead of being treated as playable media.

    This public wrapper intentionally stays on `session_runner` so callers can
    keep using the historical session-layer entrypoint while discovery details
    live in the dedicated helper module.
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

    This public wrapper intentionally remains on `session_runner` even though
    the implementation lives in the focused discovery module.
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

    Keep this public wrapper stable on `session_runner` so tests and callers do
    not need to track the internal loader-module layout.
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
    return session_runner_execution.run_api_stream_session(
        metadata=metadata,
        progress=progress,
        session_id=session_id,
        selected_detectors=selected_detectors,
        source=source,
        loader=loader,
        bundle_runner=run_enabled_analyzers_bundle,
    )


def _probe_video_duration(file_path: Path) -> float:
    """Return container duration in seconds or ``0.0`` if probing fails."""
    return session_runner_discovery.probe_video_duration(file_path)


def _validate_source_or_finalize(
    *,
    mode: InputMode,
    input_path: str | Path,
    metadata: SessionMetadata,
    progress: SessionProgress,
) -> str | Path:
    """Validate the source and persist a failed pending session on error."""
    try:
        return validate_source_input(mode, input_path)
    except (OSError, ValueError) as error:
        session_runner_terminal.finalize_validation_failure(
            metadata=metadata,
            progress=progress,
            source_kind=mode,
            error=error,
        )
        raise


def _discover_local_slices_or_finalize(
    *,
    metadata: SessionMetadata,
    progress: SessionProgress,
    input_path: str | Path,
    session_id: str,
) -> list[AnalysisSlice]:
    """Discover local slices and persist a failed pending session on error."""
    try:
        return discover_input_slices(
            metadata.mode,
            input_path,
            session_id=session_id,
        )
    except (OSError, ValueError) as error:
        session_runner_terminal.finalize_validation_failure(
            metadata=metadata,
            progress=progress,
            source_kind=metadata.mode,
            error=error,
        )
        raise


def _cleanup_session_runtime(*, session_id: str, mode: InputMode) -> None:
    """Reset rule state and clean `api_stream` temp files after a run."""
    reset_session_rule_state(session_id)
    if mode == "api_stream":
        cleanup_api_stream_temp_session_dir(session_id)
