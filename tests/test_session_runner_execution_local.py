"""Focused tests for finite-slice execution helpers in session_runner_execution."""

from pathlib import Path
from typing import cast

from session_io import initialize_session, read_session_snapshot
from session_models import SessionProgress
import session_runner_execution
from tests.session_runner_execution_test_support import (
    build_metadata,
    build_progress,
    build_slice,
    configure_session_output,
    persist_session_state,
)


def test_run_analyzers_for_slice_filters_kwargs_for_simple_bundle_runner(
    tmp_path: Path,
) -> None:
    analysis_slice = build_slice(tmp_path, "segment_0001.ts")
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
    configure_session_output(monkeypatch, tmp_path)
    metadata = build_metadata(session_id="session-execution-persist", status="pending")
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
    results = cast(list[dict[str, object]], snapshot["results"])
    alerts = cast(list[dict[str, object]], snapshot["alerts"])
    latest_result = cast(dict[str, object], snapshot["latest_result"])

    assert len(results) == 1
    assert len(alerts) == 1
    assert latest_result["detector_id"] == "video_metrics"


def test_process_discovered_slices_cancels_before_processing_next_slice(
    monkeypatch, tmp_path: Path
) -> None:
    configure_session_output(monkeypatch, tmp_path)
    metadata = build_metadata(session_id="session-execution-cancel")
    progress = build_progress(session_id=metadata.session_id)
    persist_session_state(metadata, progress)

    slices = [build_slice(tmp_path, "segment_0001.ts")]
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
    configure_session_output(monkeypatch, tmp_path)
    metadata = build_metadata(session_id="session-execution-local-complete")
    progress = build_progress(session_id=metadata.session_id)
    persist_session_state(metadata, progress)

    slices = [build_slice(tmp_path, "segment_0001.ts")]
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
    progress_data = cast(dict[str, object], snapshot["progress"])

    assert progress_data["processed_count"] == 1
    assert progress_data["current_item"] == "segment_0001.ts"
    assert finalizer_calls[-1]["status"] == "completed"


def test_process_discovered_slices_uses_default_progress_and_finalizer_helpers(
    monkeypatch, tmp_path: Path
) -> None:
    configure_session_output(monkeypatch, tmp_path)
    metadata = build_metadata(session_id="session-execution-default-helpers")
    progress = build_progress(session_id=metadata.session_id)
    persist_session_state(metadata, progress)
    slices = [build_slice(tmp_path, "segment_0001.ts")]

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
