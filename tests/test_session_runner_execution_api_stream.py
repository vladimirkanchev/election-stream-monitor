"""Focused tests for live api_stream execution helpers in session_runner_execution."""

import pytest
from typing import cast

import session_runner_execution
from tests.session_runner_execution_test_support import (
    build_live_slice,
    build_loader,
    build_metadata,
    build_progress,
    configure_session_output,
    persist_session_state,
)


def _prepare_api_stream_session(monkeypatch, tmp_path, *, session_id: str):
    """Persist one minimal api_stream session and a first live slice for runner tests."""
    configure_session_output(monkeypatch, tmp_path)
    metadata = build_metadata(session_id=session_id, mode="api_stream")
    progress = build_progress(session_id=metadata.session_id, total_count=0)
    persist_session_state(metadata, progress)
    live_slice = build_live_slice(tmp_path, "live-window-001.ts")
    return metadata, progress, live_slice


def test_run_api_stream_session_surfaces_terminal_failure_with_cleanup_counts(
    monkeypatch, tmp_path
) -> None:
    metadata, progress, live_slice = _prepare_api_stream_session(
        monkeypatch,
        tmp_path,
        session_id="session-execution-api-fail",
    )
    loader = build_loader()

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
    extra_fields = cast(dict[str, object], finalizer_calls[-1]["extra_fields"])
    assert extra_fields["session_end_reason"] == "terminal_failure"
    assert extra_fields["temp_cleanup_success_count"] == 1


def test_run_api_stream_session_uses_default_helper_wiring(
    monkeypatch, tmp_path
) -> None:
    metadata, progress, live_slice = _prepare_api_stream_session(
        monkeypatch,
        tmp_path,
        session_id="session-execution-api-default-helpers",
    )
    loader = build_loader(stop_reason="completed")

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
    monkeypatch, tmp_path
) -> None:
    metadata, progress, live_slice = _prepare_api_stream_session(
        monkeypatch,
        tmp_path,
        session_id="session-execution-api-cancel-during-processing",
    )
    loader = build_loader()

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
    extra_fields = cast(dict[str, object], finalizer_calls[-1]["extra_fields"])
    assert extra_fields["session_end_reason"] == "cancel_requested_during_processing"
    assert extra_fields["temp_cleanup_success_count"] == 1
    assert extra_fields["temp_cleanup_failure_count"] == 0


def test_run_api_stream_session_cancels_after_iteration_uses_log_fields_builder(
    monkeypatch, tmp_path
) -> None:
    configure_session_output(monkeypatch, tmp_path)
    metadata = build_metadata(
        session_id="session-execution-api-cancel-after-iteration",
        mode="api_stream",
    )
    progress = build_progress(session_id=metadata.session_id, total_count=0)
    persist_session_state(metadata, progress)

    live_slice = build_live_slice(tmp_path, "live-window-001.ts")
    loader = build_loader(stop_reason="completed")

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
        return build_progress(
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
