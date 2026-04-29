"""Focused tests for finite and live execution helpers.

These tests cover the extracted execution seams directly so failures localize
faster than they would in the larger session-runner integration suites.
"""

from pathlib import Path
from types import SimpleNamespace

import config
import pytest
from analyzer_contract import AnalysisSlice
from session_io import initialize_session, read_session_snapshot, write_session_progress
from session_models import SessionMetadata, SessionProgress
import session_runner_execution
from stream_loader_contracts import ApiStreamTelemetrySnapshot


def _configure_session_output(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")


def _build_metadata(
    *,
    session_id: str,
    mode: str = "video_segments",
    status: str = "running",
) -> SessionMetadata:
    return SessionMetadata(
        session_id=session_id,
        mode=mode,
        input_path="input-path",
        selected_detectors=["video_metrics"],
        status=status,
    )


def _build_progress(
    *,
    session_id: str,
    status: str = "running",
    processed_count: int = 0,
    total_count: int = 0,
    current_item: str | None = None,
) -> SessionProgress:
    return SessionProgress(
        session_id=session_id,
        status=status,
        processed_count=processed_count,
        total_count=total_count,
        current_item=current_item,
        latest_result_detector=None,
        alert_count=0,
        last_updated_utc="2026-04-28 12:00:00",
        latest_result_detectors=[],
        status_reason=status,
        status_detail=None,
    )


def _persist_session_state(metadata: SessionMetadata, progress: SessionProgress) -> None:
    initialize_session(metadata)
    write_session_progress(progress)


def _build_slice(tmp_path: Path, name: str) -> AnalysisSlice:
    analysis_slice = AnalysisSlice(
        file_path=tmp_path / name,
        source_group="segments",
        source_name=name,
        window_index=0,
    )
    analysis_slice.file_path.write_bytes(b"ts")
    return analysis_slice


def _build_live_slice(
    tmp_path: Path,
    name: str,
    *,
    source_group: str = "stream-a",
    window_index: int = 0,
) -> AnalysisSlice:
    analysis_slice = AnalysisSlice(
        file_path=tmp_path / name,
        source_group=source_group,
        source_name=name,
        window_index=window_index,
    )
    analysis_slice.file_path.write_bytes(b"ts")
    return analysis_slice


def _build_loader(
    *,
    accepted_slice_count: int = 1,
    stop_reason: str | None = None,
    source_url_class: str = "hls_playlist_url",
    playlist_refresh_count: int = 0,
    skipped_replay_count: int = 0,
    reconnect_attempt_count: int = 0,
    reconnect_budget_exhaustion_count: int = 0,
    terminal_failure_reason: str | None = None,
):
    telemetry = ApiStreamTelemetrySnapshot(
        source_url_class=source_url_class,
        playlist_refresh_count=playlist_refresh_count,
        skipped_replay_count=skipped_replay_count,
        reconnect_attempt_count=reconnect_attempt_count,
        reconnect_budget_exhaustion_count=reconnect_budget_exhaustion_count,
        terminal_failure_reason=terminal_failure_reason,
        stop_reason=stop_reason,
    )
    return SimpleNamespace(
        accepted_slice_count=lambda: accepted_slice_count,
        telemetry_snapshot=lambda: telemetry,
    )


def test_run_analyzers_for_slice_filters_kwargs_for_simple_bundle_runner(
    tmp_path: Path,
) -> None:
    analysis_slice = _build_slice(tmp_path, "segment_0001.ts")
    observed: dict[str, object] = {}

    def simple_bundle_runner(file_path: Path, session_id: str) -> dict[str, list[dict[str, object]]]:
        observed["file_path"] = file_path
        observed["session_id"] = session_id
        return {"results": [], "alerts": []}

    bundle = session_runner_execution.run_analyzers_for_slice(
        analysis_slice=analysis_slice,
        mode="video_segments",
        session_id="session-execution-filtered",
        selected_detectors=["video_metrics"],
        bundle_runner=simple_bundle_runner,
    )

    assert bundle == {"results": [], "alerts": []}
    assert observed == {
        "file_path": analysis_slice.file_path,
        "session_id": "session-execution-filtered",
    }


def test_persist_bundle_events_appends_results_and_alerts(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_session_output(monkeypatch, tmp_path)
    metadata = _build_metadata(session_id="session-execution-persist", status="pending")
    initialize_session(metadata)

    session_runner_execution.persist_bundle_events(
        {
            "results": [
                {
                    "session_id": metadata.session_id,
                    "detector_id": "video_metrics",
                    "payload": {"source_name": "segment_0001.ts"},
                }
            ],
            "alerts": [
                {
                    "session_id": metadata.session_id,
                    "timestamp_utc": "2026-04-28 12:00:01",
                    "detector_id": "video_metrics",
                    "title": "Test Alert",
                    "message": "Something happened",
                    "severity": "warning",
                    "source_name": "segment_0001.ts",
                }
            ],
        }
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert len(snapshot["results"]) == 1
    assert len(snapshot["alerts"]) == 1
    assert snapshot["latest_result"]["detector_id"] == "video_metrics"


def test_process_discovered_slices_cancels_before_processing_next_slice(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_session_output(monkeypatch, tmp_path)
    metadata = _build_metadata(session_id="session-execution-cancel")
    progress = _build_progress(session_id=metadata.session_id)
    _persist_session_state(metadata, progress)

    slices = [_build_slice(tmp_path, "segment_0001.ts")]
    monkeypatch.setattr(
        session_runner_execution,
        "is_session_cancel_requested",
        lambda session_id: session_id == metadata.session_id,
    )

    finalizer_calls: list[dict[str, object]] = []

    def fake_finalizer(**kwargs):
        finalizer_calls.append(kwargs)
        return kwargs["metadata"], kwargs["progress"]

    bundle_called = {"value": False}

    def fake_bundle_runner(**kwargs):
        bundle_called["value"] = True
        return {"results": [], "alerts": []}

    updated_metadata, updated_progress = session_runner_execution.process_discovered_slices(
        metadata=metadata,
        progress=progress,
        mode="video_segments",
        session_id=metadata.session_id,
        selected_detectors=["video_metrics"],
        input_slices=slices,
        bundle_runner=fake_bundle_runner,
        progress_builder=lambda **kwargs: progress,
        finalizer=fake_finalizer,
    )

    assert updated_metadata is metadata
    assert updated_progress is progress
    assert bundle_called["value"] is False
    assert finalizer_calls
    assert finalizer_calls[0]["status"] == "cancelled"
    assert finalizer_calls[0]["flush_stores"] is True


def test_process_discovered_slices_completes_and_writes_slice_progress(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_session_output(monkeypatch, tmp_path)
    metadata = _build_metadata(session_id="session-execution-local-complete")
    progress = _build_progress(session_id=metadata.session_id)
    _persist_session_state(metadata, progress)

    slices = [_build_slice(tmp_path, "segment_0001.ts")]
    monkeypatch.setattr(session_runner_execution, "is_session_cancel_requested", lambda session_id: False)

    finalizer_calls: list[dict[str, object]] = []

    def fake_finalizer(**kwargs):
        finalizer_calls.append(kwargs)
        return kwargs["metadata"], kwargs["progress"]

    def fake_bundle_runner(**kwargs):
        return {
            "results": [
                {
                    "session_id": metadata.session_id,
                    "detector_id": "video_metrics",
                    "payload": {"source_name": "segment_0001.ts"},
                }
            ],
            "alerts": [],
        }

    def fake_progress_builder(**kwargs):
        return SessionProgress(
            session_id=metadata.session_id,
            status="running",
            processed_count=kwargs["processed_count"],
            total_count=kwargs["total_count"],
            current_item=kwargs["current_item"],
            latest_result_detector="video_metrics",
            alert_count=0,
            last_updated_utc="2026-04-28 12:00:02",
            latest_result_detectors=["video_metrics"],
            status_reason="running",
            status_detail=None,
        )

    session_runner_execution.process_discovered_slices(
        metadata=metadata,
        progress=progress,
        mode="video_segments",
        session_id=metadata.session_id,
        selected_detectors=["video_metrics"],
        input_slices=slices,
        bundle_runner=fake_bundle_runner,
        progress_builder=fake_progress_builder,
        finalizer=fake_finalizer,
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert snapshot["progress"]["processed_count"] == 1
    assert snapshot["progress"]["current_item"] == "segment_0001.ts"
    assert finalizer_calls[-1]["status"] == "completed"


def test_process_discovered_slices_uses_default_progress_and_finalizer_helpers(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_session_output(monkeypatch, tmp_path)
    metadata = _build_metadata(session_id="session-execution-default-helpers")
    progress = _build_progress(session_id=metadata.session_id)
    _persist_session_state(metadata, progress)
    slices = [_build_slice(tmp_path, "segment_0001.ts")]

    monkeypatch.setattr(session_runner_execution, "is_session_cancel_requested", lambda session_id: False)

    progress_builder_calls: list[dict[str, object]] = []
    finalizer_calls: list[dict[str, object]] = []

    def fake_progress_builder(**kwargs):
        progress_builder_calls.append(kwargs)
        return progress

    def fake_finalizer(**kwargs):
        finalizer_calls.append(kwargs)
        return kwargs["metadata"], kwargs["progress"]

    monkeypatch.setattr(
        session_runner_execution.session_runner_progress,
        "build_slice_progress",
        fake_progress_builder,
    )
    monkeypatch.setattr(
        session_runner_execution.session_runner_terminal,
        "finalize_session_outcome",
        fake_finalizer,
    )

    session_runner_execution.process_discovered_slices(
        metadata=metadata,
        progress=progress,
        mode="video_segments",
        session_id=metadata.session_id,
        selected_detectors=["video_metrics"],
        input_slices=slices,
        bundle_runner=lambda **kwargs: {"results": [], "alerts": []},
    )

    assert progress_builder_calls
    assert finalizer_calls[-1]["status"] == "completed"


def test_run_api_stream_session_surfaces_terminal_failure_with_cleanup_counts(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_session_output(monkeypatch, tmp_path)
    metadata = _build_metadata(
        session_id="session-execution-api-fail",
        mode="api_stream",
    )
    progress = _build_progress(session_id=metadata.session_id, total_count=0)
    _persist_session_state(metadata, progress)

    live_slice = _build_live_slice(tmp_path, "live-window-001.ts")
    loader = _build_loader()

    monkeypatch.setattr(
        session_runner_execution,
        "iter_api_stream_slices",
        lambda loader, source: iter([live_slice]),
    )
    monkeypatch.setattr(session_runner_execution, "is_session_cancel_requested", lambda session_id: False)

    finalizer_calls: list[dict[str, object]] = []

    def fake_finalizer(**kwargs):
        finalizer_calls.append(kwargs)
        return kwargs["metadata"], kwargs["progress"]

    cleanup_calls: list[tuple[int, int]] = []

    def fake_cleanup_recorder(
        analysis_slice,
        *,
        cleanup_success_count: int,
        cleanup_failure_count: int,
    ) -> tuple[int, int]:
        cleanup_calls.append((cleanup_success_count, cleanup_failure_count))
        return cleanup_success_count + 1, cleanup_failure_count

    def failing_bundle_runner(**kwargs):
        raise ValueError("stream reader disconnected")

    def fake_log_fields_builder(**kwargs):
        return {
            "session_end_reason": kwargs["session_end_reason"],
            "temp_cleanup_success_count": kwargs["cleanup_success_count"],
            "temp_cleanup_failure_count": kwargs["cleanup_failure_count"],
        }

    with pytest.raises(ValueError, match="stream reader disconnected"):
        session_runner_execution.run_api_stream_session(
            metadata=metadata,
            progress=progress,
            session_id=metadata.session_id,
            selected_detectors=["video_blur"],
            source=object(),
            loader=loader,
            bundle_runner=failing_bundle_runner,
            progress_builder=lambda **kwargs: progress,
            finalizer=fake_finalizer,
            api_stream_log_fields_builder=fake_log_fields_builder,
            api_stream_outcome_fields_builder=lambda **kwargs: {},
            cleanup_recorder=fake_cleanup_recorder,
        )

    assert cleanup_calls == [(0, 0)]
    assert finalizer_calls[-1]["status"] == "failed"
    assert finalizer_calls[-1]["extra_fields"]["session_end_reason"] == "terminal_failure"
    assert finalizer_calls[-1]["extra_fields"]["temp_cleanup_success_count"] == 1


def test_run_api_stream_session_uses_default_helper_wiring(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_session_output(monkeypatch, tmp_path)
    metadata = _build_metadata(
        session_id="session-execution-api-default-helpers",
        mode="api_stream",
    )
    progress = _build_progress(session_id=metadata.session_id, total_count=0)
    _persist_session_state(metadata, progress)

    live_slice = _build_live_slice(tmp_path, "live-window-001.ts")
    loader = _build_loader(stop_reason="completed")

    monkeypatch.setattr(
        session_runner_execution,
        "iter_api_stream_slices",
        lambda loader, source: iter([live_slice]),
    )
    monkeypatch.setattr(session_runner_execution, "is_session_cancel_requested", lambda session_id: False)

    progress_builder_calls: list[dict[str, object]] = []
    log_field_calls: list[dict[str, object]] = []
    finalizer_calls: list[dict[str, object]] = []
    cleanup_calls: list[tuple[int, int]] = []

    def fake_progress_builder(**kwargs):
        progress_builder_calls.append(kwargs)
        return progress

    def fake_log_fields_builder(**kwargs):
        log_field_calls.append(kwargs)
        return {"session_end_reason": kwargs["session_end_reason"]}

    def fake_finalizer(**kwargs):
        finalizer_calls.append(kwargs)
        return kwargs["metadata"], kwargs["progress"]

    def fake_cleanup_recorder(
        analysis_slice,
        *,
        cleanup_success_count: int,
        cleanup_failure_count: int,
    ) -> tuple[int, int]:
        cleanup_calls.append((cleanup_success_count, cleanup_failure_count))
        return cleanup_success_count + 1, cleanup_failure_count

    monkeypatch.setattr(
        session_runner_execution.session_runner_progress,
        "build_slice_progress",
        fake_progress_builder,
    )
    monkeypatch.setattr(
        session_runner_execution.session_runner_progress,
        "build_api_stream_session_log_fields",
        fake_log_fields_builder,
    )
    monkeypatch.setattr(
        session_runner_execution.session_runner_terminal,
        "finalize_session_outcome",
        fake_finalizer,
    )
    monkeypatch.setattr(
        session_runner_execution.session_runner_terminal,
        "record_api_stream_cleanup",
        fake_cleanup_recorder,
    )

    session_runner_execution.run_api_stream_session(
        metadata=metadata,
        progress=progress,
        session_id=metadata.session_id,
        selected_detectors=["video_blur"],
        source=object(),
        loader=loader,
        bundle_runner=lambda **kwargs: {"results": [], "alerts": []},
    )

    assert progress_builder_calls
    assert cleanup_calls == [(0, 0)]
    assert log_field_calls[-1]["session_end_reason"] == "completed"
    assert finalizer_calls[-1]["status"] == "completed"


def test_run_api_stream_session_cancel_during_processing_cleans_current_slice(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_session_output(monkeypatch, tmp_path)
    metadata = _build_metadata(
        session_id="session-execution-api-cancel-during-processing",
        mode="api_stream",
    )
    progress = _build_progress(session_id=metadata.session_id, total_count=0)
    _persist_session_state(metadata, progress)

    live_slice = _build_live_slice(tmp_path, "live-window-001.ts")
    loader = _build_loader()

    monkeypatch.setattr(
        session_runner_execution,
        "iter_api_stream_slices",
        lambda loader, source: iter([live_slice]),
    )
    monkeypatch.setattr(session_runner_execution, "is_session_cancel_requested", lambda session_id: True)

    finalizer_calls: list[dict[str, object]] = []

    def fake_finalizer(**kwargs):
        finalizer_calls.append(kwargs)
        return kwargs["metadata"], kwargs["progress"]

    updated_metadata, updated_progress = session_runner_execution.run_api_stream_session(
        metadata=metadata,
        progress=progress,
        session_id=metadata.session_id,
        selected_detectors=["video_blur"],
        source=object(),
        loader=loader,
        bundle_runner=lambda **kwargs: {"results": [], "alerts": []},
        finalizer=fake_finalizer,
    )

    assert updated_metadata is metadata
    assert updated_progress is progress
    assert not live_slice.file_path.exists()
    assert finalizer_calls[-1]["status"] == "cancelled"
    assert (
        finalizer_calls[-1]["extra_fields"]["session_end_reason"]
        == "cancel_requested_during_processing"
    )
    assert finalizer_calls[-1]["extra_fields"]["temp_cleanup_success_count"] == 1
    assert finalizer_calls[-1]["extra_fields"]["temp_cleanup_failure_count"] == 0


def test_run_api_stream_session_cancels_after_iteration_uses_log_fields_builder(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_session_output(monkeypatch, tmp_path)
    metadata = _build_metadata(
        session_id="session-execution-api-cancel-after-iteration",
        mode="api_stream",
    )
    progress = _build_progress(session_id=metadata.session_id, total_count=0)
    _persist_session_state(metadata, progress)

    live_slice = _build_live_slice(tmp_path, "live-window-001.ts")
    loader = _build_loader(stop_reason="completed")

    events = iter([False, True])
    monkeypatch.setattr(
        session_runner_execution,
        "is_session_cancel_requested",
        lambda session_id: next(events),
    )
    monkeypatch.setattr(
        session_runner_execution,
        "iter_api_stream_slices",
        lambda loader, source: iter([live_slice]),
    )

    finalizer_calls: list[dict[str, object]] = []

    def fake_finalizer(**kwargs):
        finalizer_calls.append(kwargs)
        return kwargs["metadata"], kwargs["progress"]

    def fake_bundle_runner(**kwargs):
        return {"results": [], "alerts": []}

    def fake_progress_builder(**kwargs):
        return _build_progress(
            session_id=metadata.session_id,
            processed_count=kwargs["processed_count"],
            total_count=kwargs["total_count"],
            current_item=kwargs["current_item"],
        )

    log_field_calls: list[dict[str, object]] = []

    def fake_log_fields_builder(**kwargs):
        log_field_calls.append(kwargs)
        return {"session_end_reason": kwargs["session_end_reason"]}

    session_runner_execution.run_api_stream_session(
        metadata=metadata,
        progress=progress,
        session_id=metadata.session_id,
        selected_detectors=["video_blur"],
        source=object(),
        loader=loader,
        bundle_runner=fake_bundle_runner,
        progress_builder=fake_progress_builder,
        finalizer=fake_finalizer,
        api_stream_log_fields_builder=fake_log_fields_builder,
        api_stream_outcome_fields_builder=lambda **kwargs: {},
        cleanup_recorder=lambda analysis_slice, **kwargs: (1, 0),
    )

    assert log_field_calls[-1]["session_end_reason"] == "cancel_requested_after_iteration"
    assert finalizer_calls[-1]["status"] == "cancelled"
