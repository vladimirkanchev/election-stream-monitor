"""Focused tests for terminal persistence, cleanup, and logging helpers.

These cases cover the end-of-session behavior that is easiest to regress:

- terminal status persistence and flush policy
- `api_stream` cancel/failure status mapping
- temp-file cleanup behavior and cleanup counters
"""

from pathlib import Path
from types import SimpleNamespace

import config
import session_runner_terminal
from analyzer_contract import AnalysisSlice
from session_io import initialize_session, read_session_snapshot, write_session_progress
from session_models import SessionMetadata, SessionProgress
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
    latest_result_detector: str | None = None,
    alert_count: int = 0,
    latest_result_detectors: list[str] | None = None,
) -> SessionProgress:
    return SessionProgress(
        session_id=session_id,
        status=status,
        processed_count=processed_count,
        total_count=total_count,
        current_item=current_item,
        latest_result_detector=latest_result_detector,
        alert_count=alert_count,
        last_updated_utc="2026-04-28 12:00:00",
        latest_result_detectors=latest_result_detectors or [],
        status_reason=status,
        status_detail=None,
    )


def _persist_session_state(metadata: SessionMetadata, progress: SessionProgress) -> None:
    initialize_session(metadata)
    write_session_progress(progress)


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
    source_url_class: str = "hls_playlist_url",
    playlist_refresh_count: int = 3,
    skipped_replay_count: int = 1,
    reconnect_attempt_count: int = 2,
    reconnect_budget_exhaustion_count: int = 0,
    terminal_failure_reason: str | None = None,
    stop_reason: str | None = "completed",
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
    return SimpleNamespace(telemetry_snapshot=lambda: telemetry)


def _patch_metric_flushes(monkeypatch) -> list[str]:
    flush_calls: list[str] = []
    monkeypatch.setattr(
        session_runner_terminal.black_frame_store,
        "flush",
        lambda: flush_calls.append("black"),
    )
    monkeypatch.setattr(
        session_runner_terminal.blur_metrics_store,
        "flush",
        lambda: flush_calls.append("blur"),
    )
    return flush_calls


def test_finalize_session_outcome_completed_flushes_stores_and_persists_progress(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_session_output(monkeypatch, tmp_path)

    metadata = _build_metadata(session_id="session-terminal-completed")
    progress = _build_progress(
        session_id=metadata.session_id,
        processed_count=2,
        total_count=2,
        current_item="segment_0002.ts",
        latest_result_detector="video_metrics",
        alert_count=1,
        latest_result_detectors=["video_metrics"],
    )
    _persist_session_state(metadata, progress)

    flush_calls = _patch_metric_flushes(monkeypatch)
    log_calls: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        session_runner_terminal.logger,
        "info",
        lambda message, *args: log_calls.append((message, args)),
    )

    session_runner_terminal.finalize_session_outcome(
        metadata=metadata,
        progress=progress,
        status="completed",
        source_kind="video_segments",
        flush_stores=True,
        log_level="info",
        log_message="Completed session %s [%s]",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert flush_calls == ["black", "blur"]
    assert snapshot["session"]["status"] == "completed"
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["status_reason"] == "completed"
    assert snapshot["progress"]["status_detail"] is None
    assert log_calls
    assert log_calls[0][0] == "Completed session %s [%s]"


def test_finalize_validation_failure_persists_validation_failed_details(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_session_output(monkeypatch, tmp_path)

    metadata = _build_metadata(
        session_id="session-terminal-validation-failure",
        status="pending",
    )
    progress = SessionProgress.initial(session_id=metadata.session_id, total_count=0)
    _persist_session_state(metadata, progress)

    session_runner_terminal.finalize_validation_failure(
        metadata=metadata,
        progress=progress,
        source_kind="video_segments",
        error=OSError("Input path does not exist"),
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert snapshot["session"]["status"] == "failed"
    assert snapshot["progress"]["status"] == "failed"
    assert snapshot["progress"]["status_reason"] == "validation_failed"
    assert snapshot["progress"]["status_detail"] == "Input path does not exist"


def test_finalize_session_outcome_api_stream_cancel_after_iteration_keeps_detail(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_session_output(monkeypatch, tmp_path)

    metadata = _build_metadata(
        session_id="session-terminal-api-cancel-after-iteration",
        mode="api_stream",
    )
    progress = _build_progress(
        session_id=metadata.session_id,
        processed_count=1,
        total_count=1,
        current_item="live-window-001.ts",
    )
    _persist_session_state(metadata, progress)

    flush_calls = _patch_metric_flushes(monkeypatch)

    session_runner_terminal.finalize_session_outcome(
        metadata=metadata,
        progress=progress,
        status="cancelled",
        source_kind="api_stream",
        flush_stores=True,
        log_level="info",
        log_message="Cancelled session %s [%s]",
        extra_fields={"session_end_reason": "cancel_requested_after_iteration"},
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert flush_calls == ["black", "blur"]
    assert snapshot["session"]["status"] == "cancelled"
    assert snapshot["progress"]["status"] == "cancelled"
    assert snapshot["progress"]["status_reason"] == "cancel_requested"
    assert (
        snapshot["progress"]["status_detail"]
        == "Cancellation requested after iteration"
    )


def test_finalize_session_outcome_api_stream_failure_preserves_partial_progress(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_session_output(monkeypatch, tmp_path)

    metadata = _build_metadata(
        session_id="session-terminal-api-failure",
        mode="api_stream",
    )
    progress = _build_progress(
        session_id=metadata.session_id,
        processed_count=2,
        total_count=2,
        current_item="live-window-002.ts",
    )
    _persist_session_state(metadata, progress)

    flush_calls = _patch_metric_flushes(monkeypatch)

    session_runner_terminal.finalize_session_outcome(
        metadata=metadata,
        progress=progress,
        status="failed",
        source_kind="api_stream",
        flush_stores=False,
        log_level="error",
        log_message="Session %s failed: %s [%s]",
        error=ValueError("stream reader disconnected"),
        extra_fields={
            "session_end_reason": "terminal_failure",
            "terminal_failure_reason": "reconnect_budget_exhausted",
        },
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert flush_calls == []
    assert snapshot["session"]["status"] == "failed"
    assert snapshot["progress"]["status"] == "failed"
    assert snapshot["progress"]["processed_count"] == 2
    assert snapshot["progress"]["current_item"] == "live-window-002.ts"
    assert snapshot["progress"]["status_reason"] == "source_unreachable"
    assert snapshot["progress"]["status_detail"] == "reconnect_budget_exhausted"


def test_cleanup_processed_api_stream_slice_deletes_temp_file(tmp_path: Path) -> None:
    analysis_slice = _build_live_slice(tmp_path, "live-window-001.ts")
    live_file = analysis_slice.file_path

    result = session_runner_terminal.cleanup_processed_api_stream_slice(analysis_slice)

    assert result is True
    assert not live_file.exists()


def test_cleanup_processed_api_stream_slice_logs_warning_on_unlink_failure(
    monkeypatch, tmp_path: Path
) -> None:
    analysis_slice = _build_live_slice(tmp_path, "live-window-001.ts")
    live_file = analysis_slice.file_path

    warnings: list[tuple[str, tuple[object, ...]]] = []
    original_unlink = Path.unlink

    def failing_unlink(self: Path, *args, **kwargs) -> None:
        if self == live_file:
            raise OSError("permission denied")
        original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", failing_unlink)
    monkeypatch.setattr(
        session_runner_terminal.logger,
        "warning",
        lambda message, *args: warnings.append((message, args)),
    )

    result = session_runner_terminal.cleanup_processed_api_stream_slice(analysis_slice)

    assert result is False
    assert live_file.exists()
    assert warnings
    assert warnings[0][0] == "Failed to delete processed api_stream temp file [%s]"


def test_build_api_stream_outcome_fields_cleans_current_slice_and_tracks_counts(
    tmp_path: Path,
) -> None:
    analysis_slice = _build_live_slice(
        tmp_path,
        "live-window-007.ts",
        window_index=7,
    )
    live_file = analysis_slice.file_path

    fields = session_runner_terminal.build_api_stream_outcome_fields(
        loader=_build_loader(),
        processed_count=4,
        session_end_reason="cancel_requested_during_processing",
        analysis_slice=analysis_slice,
        cleanup_success_count=1,
        cleanup_failure_count=0,
    )

    assert not live_file.exists()
    assert fields["session_end_reason"] == "cancel_requested_during_processing"
    assert fields["processed_chunk_count"] == 4
    assert fields["source_url_class"] == "hls_playlist_url"
    assert fields["temp_cleanup_success_count"] == 2
    assert fields["temp_cleanup_failure_count"] == 0
