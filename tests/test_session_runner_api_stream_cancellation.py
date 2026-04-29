"""Cancellation-oriented seam tests for `api_stream` session runs.

Read this file when you want the cancellation contract for the live runner.
It keeps the different cancel timing cases together so we can reason about:
- cancel before processing a yielded chunk
- cancel during slice processing
- cancel after earlier temporary loader noise
"""

from pathlib import Path

from analyzer_contract import AnalysisSlice
from session_io import read_session_snapshot
from session_runner import run_local_session
from stream_loader import FakeApiStreamLoader, StaticApiStreamLoader
from tests.session_runner_api_stream_test_support import (
    _assert_basic_cancelled_snapshot,
    _build_cancelling_blur_analyzer,
    _configure_api_stream_runner_test,
    _fake_chunk_event,
    _fake_temporary_failure_event,
    _install_api_stream_loader,
    _install_static_api_stream_loader,
    _patch_processor_with_analyzer,
)


def test_run_local_session_deletes_current_api_stream_temp_file_on_cancel(
    monkeypatch, tmp_path: Path
) -> None:
    """A yielded live chunk should be deleted immediately when cancel stops the session."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)
    live_file = tmp_path / "live-window-000.ts"
    live_file.write_bytes(b"ts")

    slice_ = AnalysisSlice(
        file_path=live_file,
        source_group="https://example.com/live/playlist.m3u8",
        source_name="live-window-000.ts",
        window_index=0,
        window_start_sec=0.0,
        window_duration_sec=1.0,
    )
    _install_api_stream_loader(monkeypatch, StaticApiStreamLoader([slice_]))

    from session_io import request_session_cancel

    request_session_cancel("session-api-cancel-before-processing")
    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-cancel-before-processing",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "cancelled"
    _assert_basic_cancelled_snapshot(
        snapshot,
        processed_count=0,
        current_item=None,
        result_count=0,
    )
    assert not live_file.exists()


def test_run_local_session_cancels_after_temporary_loader_noise_before_next_accepted_chunk(
    monkeypatch, tmp_path: Path
) -> None:
    """A cancel request should still settle cleanly if a temporary loader failure happens first."""
    fake_loader = FakeApiStreamLoader(
        [
            _fake_chunk_event(tmp_path, chunk_index=0, current_item="live-window-001.ts"),
            _fake_temporary_failure_event(
                chunk_index=1,
                current_item="live-window-002.ts",
                message="temporary upstream stall",
            ),
            _fake_chunk_event(tmp_path, chunk_index=1, current_item="live-window-002.ts"),
        ]
    )
    _configure_api_stream_runner_test(monkeypatch, tmp_path, loader=fake_loader)

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_cancelling_blur_analyzer(
            session_id="session-api-cancel-after-noise"
        ),
        supported_modes=("api_stream",),
    )

    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-cancel-after-noise",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "cancelled"
    _assert_basic_cancelled_snapshot(
        snapshot,
        processed_count=1,
        current_item="live-window-001.ts",
        result_count=1,
    )
    assert snapshot["progress"]["status_reason"] == "cancel_requested"
    assert (
        snapshot["progress"]["status_detail"]
        == "Cancellation requested during slice processing"
    )


def test_run_local_session_cancels_incremental_api_stream_cleanly(
    monkeypatch, tmp_path: Path
) -> None:
    """An explicit cancel request should stop the live loop after the current chunk."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)

    _install_static_api_stream_loader(
        monkeypatch,
        tmp_path,
        source_group="stream-a",
        names=["live-window-001.ts", "live-window-002.ts", "live-window-003.ts"],
    )

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_cancelling_blur_analyzer(session_id="session-api-cancelled"),
        supported_modes=("api_stream",),
    )

    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-cancelled",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "cancelled"
    _assert_basic_cancelled_snapshot(
        snapshot,
        processed_count=1,
        current_item="live-window-001.ts",
        result_count=1,
    )
