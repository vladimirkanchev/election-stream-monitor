"""Finite and live execution loops for `session_runner`.

This module owns the repeated "process one slice, persist its outputs, update
progress" behavior used by both local inputs and `api_stream`.

Keep orchestration decisions in `session_runner.py`.
Keep terminal persistence and cleanup policy in `session_runner_terminal.py`.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable

from analyzer_contract import AnalysisSlice, InputMode
from session_io import append_alert, append_result, is_session_cancel_requested, write_session_progress
from session_models import AlertEvent, ResultEvent, SessionMetadata, SessionProgress
import session_runner_progress
import session_runner_terminal
from stream_loader import ApiStreamLoader, iter_api_stream_slices

BundlePayload = dict[str, list[dict[str, object]]]
BundleRunner = Callable[..., BundlePayload]
ProgressBuilder = Callable[..., SessionProgress]
Finalizer = Callable[..., tuple[SessionMetadata, SessionProgress]]
ApiStreamFieldsBuilder = Callable[..., dict[str, object]]
CleanupRecorder = Callable[..., tuple[int, int]]


def run_analyzers_for_slice(
    *,
    analysis_slice: AnalysisSlice,
    mode: InputMode,
    session_id: str,
    selected_detectors: list[str],
    bundle_runner: BundleRunner,
) -> BundlePayload:
    """Run the analyzer bundle for one slice.

    The filtered kwargs keep older tests and simpler doubles working even when
    they accept only a subset of the full analyzer-bundle call signature.
    """
    kwargs = {
        "file_path": analysis_slice.file_path,
        "prefix": analysis_slice.file_path.parent.name,
        "mode": mode,
        "session_id": session_id,
        "selected_analyzers": set(selected_detectors),
        "persist_to_store": True,
        "analysis_slice": analysis_slice,
    }
    accepted = inspect.signature(bundle_runner).parameters
    filtered_kwargs = {
        key: value
        for key, value in kwargs.items()
        if key in accepted
    }
    return bundle_runner(**filtered_kwargs)


def persist_bundle_events(bundle: BundlePayload) -> None:
    """Persist one analyzer bundle into the results and alerts logs."""
    for result_payload in bundle["results"]:
        append_result(ResultEvent(**result_payload))

    for alert_payload in bundle["alerts"]:
        append_alert(AlertEvent(**alert_payload))


def process_discovered_slices(
    *,
    metadata: SessionMetadata,
    progress: SessionProgress,
    mode: InputMode,
    session_id: str,
    selected_detectors: list[str],
    input_slices: list[AnalysisSlice],
    bundle_runner: BundleRunner,
    progress_builder: ProgressBuilder | None = None,
    finalizer: Finalizer | None = None,
) -> tuple[SessionMetadata, SessionProgress]:
    """Process a finite list of local slices from start to finish."""
    progress_builder = progress_builder or session_runner_progress.build_slice_progress
    finalizer = finalizer or session_runner_terminal.finalize_session_outcome

    try:
        for processed_count, analysis_slice in enumerate(input_slices, start=1):
            if is_session_cancel_requested(session_id):
                return finalizer(
                    metadata=metadata,
                    progress=progress,
                    status="cancelled",
                    source_kind=mode,
                    flush_stores=True,
                    log_level="info",
                    log_message="Cancelled session %s [%s]",
                )

            bundle = run_analyzers_for_slice(
                analysis_slice=analysis_slice,
                mode=mode,
                session_id=session_id,
                selected_detectors=selected_detectors,
                bundle_runner=bundle_runner,
            )

            persist_bundle_events(bundle)
            progress = progress_builder(
                current=progress,
                processed_count=processed_count,
                total_count=len(input_slices),
                current_item=analysis_slice.source_name,
                bundle=bundle,
                status=metadata.status,
            )
            write_session_progress(progress)

        return finalizer(
            metadata=metadata,
            progress=progress,
            status="completed",
            source_kind=mode,
            flush_stores=True,
            log_level="info",
            log_message="Completed session %s [%s]",
        )
    except (OSError, ValueError) as error:
        finalizer(
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


def run_api_stream_session(
    *,
    metadata: SessionMetadata,
    progress: SessionProgress,
    session_id: str,
    selected_detectors: list[str],
    source,
    loader: ApiStreamLoader,
    bundle_runner: BundleRunner,
    progress_builder: ProgressBuilder | None = None,
    finalizer: Finalizer | None = None,
    api_stream_log_fields_builder: ApiStreamFieldsBuilder | None = None,
    api_stream_outcome_fields_builder: ApiStreamFieldsBuilder | None = None,
    cleanup_recorder: CleanupRecorder | None = None,
) -> tuple[SessionMetadata, SessionProgress]:
    """Process live slices incrementally as the loader yields them."""
    progress_builder = progress_builder or session_runner_progress.build_slice_progress
    finalizer = finalizer or session_runner_terminal.finalize_session_outcome
    api_stream_log_fields_builder = (
        api_stream_log_fields_builder
        or session_runner_progress.build_api_stream_session_log_fields
    )
    api_stream_outcome_fields_builder = (
        api_stream_outcome_fields_builder
        or session_runner_terminal.build_api_stream_outcome_fields
    )
    cleanup_recorder = cleanup_recorder or session_runner_terminal.record_api_stream_cleanup

    processed_count = progress.processed_count
    cleanup_success_count = 0
    cleanup_failure_count = 0
    try:
        for analysis_slice in iter_api_stream_slices(loader, source):
            if is_session_cancel_requested(session_id):
                return finalizer(
                    metadata=metadata,
                    progress=progress,
                    status="cancelled",
                    source_kind="api_stream",
                    flush_stores=True,
                    log_level="info",
                    log_message="Cancelled session %s [%s]",
                    extra_fields=api_stream_outcome_fields_builder(
                        loader=loader,
                        processed_count=processed_count,
                        session_end_reason="cancel_requested_during_processing",
                        analysis_slice=analysis_slice,
                        cleanup_success_count=cleanup_success_count,
                        cleanup_failure_count=cleanup_failure_count,
                    ),
                )

            try:
                bundle = run_analyzers_for_slice(
                    analysis_slice=analysis_slice,
                    mode="api_stream",
                    session_id=session_id,
                    selected_detectors=selected_detectors,
                    bundle_runner=bundle_runner,
                )
                processed_count += 1
                persist_bundle_events(bundle)
                progress = progress_builder(
                    current=progress,
                    processed_count=processed_count,
                    total_count=max(loader.accepted_slice_count(), processed_count),
                    current_item=analysis_slice.source_name,
                    bundle=bundle,
                    status=metadata.status,
                )
                write_session_progress(progress)
            finally:
                cleanup_success_count, cleanup_failure_count = cleanup_recorder(
                    analysis_slice,
                    cleanup_success_count=cleanup_success_count,
                    cleanup_failure_count=cleanup_failure_count,
                )
    except (OSError, ValueError) as error:
        metadata, progress = finalizer(
            metadata=metadata,
            progress=progress,
            status="failed",
            source_kind="api_stream",
            flush_stores=False,
            log_level="error",
            log_message="Session %s failed: %s [%s]",
            error=error,
            extra_fields=api_stream_log_fields_builder(
                loader=loader,
                processed_count=processed_count,
                session_end_reason="terminal_failure",
                cleanup_success_count=cleanup_success_count,
                cleanup_failure_count=cleanup_failure_count,
            ),
        )
        raise

    if is_session_cancel_requested(session_id):
        return finalizer(
            metadata=metadata,
            progress=progress,
            status="cancelled",
            source_kind="api_stream",
            flush_stores=True,
            log_level="info",
            log_message="Cancelled session %s [%s]",
            extra_fields=api_stream_log_fields_builder(
                loader=loader,
                processed_count=processed_count,
                session_end_reason="cancel_requested_after_iteration",
                cleanup_success_count=cleanup_success_count,
                cleanup_failure_count=cleanup_failure_count,
            ),
        )

    return finalizer(
        metadata=metadata,
        progress=progress,
        status="completed",
        source_kind="api_stream",
        flush_stores=True,
        log_level="info",
        log_message="Completed session %s [%s]",
        extra_fields=api_stream_log_fields_builder(
            loader=loader,
            processed_count=processed_count,
            session_end_reason=loader.telemetry_snapshot().stop_reason or "completed",
            cleanup_success_count=cleanup_success_count,
            cleanup_failure_count=cleanup_failure_count,
        ),
    )
