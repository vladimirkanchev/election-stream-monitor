"""Completion-oriented seam tests for `api_stream` session runs.

Read this file when you want the happy-path and clean-settle contract for the
live runner without the noise of failure or cancellation scenarios.

These cases focus on:
- completed snapshots and progress
- completion-side logging
- accepted-chunk temp-file cleanup
- zero-progress completion when the loader only emits temporary noise
"""

from pathlib import Path

import session_runner
from session_io import read_session_snapshot
from session_runner import run_local_session
from stream_loader import FakeApiStreamLoader, build_api_stream_source_contract
from tests.session_runner_api_stream_test_support import (
    _assert_basic_completed_snapshot,
    _build_blur_analyzer,
    _configure_api_stream_runner_test,
    _fake_chunk_event,
    _fake_malformed_chunk_event,
    _fake_temporary_failure_event,
    _install_api_stream_loader,
    _install_static_api_stream_loader,
    _patch_processor_with_analyzer,
)


def test_run_local_session_keeps_snapshot_contract_when_fake_loader_skips_bad_live_events(
    monkeypatch, tmp_path: Path
) -> None:
    """Live ingestion changes should not change the persisted session snapshot model."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)

    stream_source = build_api_stream_source_contract(
        "https://example.com/live/playlist.m3u8"
    )
    fake_loader = FakeApiStreamLoader(
        [
            _fake_chunk_event(tmp_path, chunk_index=0, current_item="live-window-000.ts"),
            _fake_temporary_failure_event(
                chunk_index=1,
                current_item="live-window-001.ts",
                message="temporary fetch timeout",
            ),
            _fake_chunk_event(tmp_path, chunk_index=1, current_item="live-window-001.ts"),
            _fake_chunk_event(tmp_path, chunk_index=1, current_item="live-window-001.ts"),
            _fake_malformed_chunk_event(
                tmp_path,
                chunk_index=3,
                current_item="bad-window.ts",
                file_name="live-window-002.ts",
            ),
            _fake_chunk_event(tmp_path, chunk_index=2, current_item="live-window-002.ts"),
        ]
    )
    _install_api_stream_loader(monkeypatch, fake_loader)

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer(
            {
                "live-window-000.ts": 0.2,
                "live-window-001.ts": 0.25,
                "live-window-002.ts": 0.3,
            }
        ),
        supported_modes=("api_stream",),
    )

    metadata = run_local_session(
        mode="api_stream",
        input_path=stream_source.input_path,
        selected_detectors=["video_blur"],
        session_id="session-api-fake-loader",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["session"]["mode"] == "api_stream"
    _assert_basic_completed_snapshot(
        snapshot,
        processed_count=3,
        current_item="live-window-002.ts",
        result_count=3,
    )
    assert snapshot["alerts"] == []


def test_run_local_session_logs_api_stream_completion_summary(
    monkeypatch, tmp_path: Path
) -> None:
    """Completed api_stream runs should log one transport/session summary for operators."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)
    info_logs: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        session_runner.logger,
        "info",
        lambda message, *args: info_logs.append((message, args)),
    )

    fake_loader = FakeApiStreamLoader(
        [
            _fake_chunk_event(
                tmp_path,
                chunk_index=0,
                current_item="live-window-000.ts",
                payload=b"000",
            ),
            _fake_chunk_event(
                tmp_path,
                chunk_index=1,
                current_item="live-window-001.ts",
                payload=b"001",
            ),
        ]
    )
    _install_api_stream_loader(monkeypatch, fake_loader)

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer(
            {
                "live-window-000.ts": 0.2,
                "live-window-001.ts": 0.25,
            }
        ),
        supported_modes=("api_stream",),
    )

    run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-log-complete",
    )

    completion_logs = [
        args[1] for message, args in info_logs if message == "Completed session %s [%s]"
    ]
    assert completion_logs
    assert any("session_end_reason='completed'" in str(entry) for entry in completion_logs)
    assert any("source_url_class='hls_playlist_url'" in str(entry) for entry in completion_logs)
    assert any("processed_chunk_count=2" in str(entry) for entry in completion_logs)
    assert any("temp_cleanup_success_count=2" in str(entry) for entry in completion_logs)
    assert any("temp_cleanup_failure_count=0" in str(entry) for entry in completion_logs)


def test_run_local_session_deletes_processed_api_stream_temp_files(
    monkeypatch, tmp_path: Path
) -> None:
    """Processed live temp media should be deleted by the runner after each slice."""
    live_file = tmp_path / "live-window-000.ts"
    live_file.write_bytes(b"ts")

    fake_loader = FakeApiStreamLoader(
        [_fake_chunk_event(tmp_path, chunk_index=0, current_item="live-window-000.ts")]
    )
    _configure_api_stream_runner_test(monkeypatch, tmp_path, loader=fake_loader)

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer({"live-window-000.ts": 0.2}),
        supported_modes=("api_stream",),
    )

    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-temp-cleanup",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    _assert_basic_completed_snapshot(
        snapshot,
        processed_count=1,
        current_item="live-window-000.ts",
        result_count=1,
    )
    assert not live_file.exists()


def test_run_local_session_completes_remote_api_stream_like_session(
    monkeypatch, tmp_path: Path
) -> None:
    """Remote api-stream inputs should progress through live-like slices and complete."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)
    remote_url = "https://example.com/live/playlist.m3u8"

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
        analyzer=_build_blur_analyzer(
            {
                "live-window-001.ts": 0.20,
                "live-window-002.ts": 0.25,
                "live-window-003.ts": 0.30,
            }
        ),
        supported_modes=("api_stream",),
    )

    metadata = run_local_session(
        mode="api_stream",
        input_path=remote_url,
        selected_detectors=["video_blur"],
        session_id="session-api-remote",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert metadata.mode == "api_stream"
    assert metadata.input_path == remote_url
    _assert_basic_completed_snapshot(
        snapshot,
        processed_count=3,
        current_item="live-window-003.ts",
        result_count=3,
    )
    assert snapshot["alerts"] == []


def test_run_local_session_completes_with_zero_progress_when_fake_loader_only_emits_temporary_failures(
    monkeypatch, tmp_path: Path
) -> None:
    """A fake live run with only temporary failures should settle cleanly without persisted results."""
    fake_loader = FakeApiStreamLoader(
        [
            _fake_temporary_failure_event(
                chunk_index=0,
                current_item="live-window-000.ts",
                message="temporary fetch timeout",
            ),
            _fake_temporary_failure_event(
                chunk_index=1,
                current_item="live-window-001.ts",
                message="temporary upstream stall",
            ),
        ]
    )
    _configure_api_stream_runner_test(monkeypatch, tmp_path, loader=fake_loader)

    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-zero-progress",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["session"]["status"] == "completed"
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == 0
    assert snapshot["progress"]["current_item"] is None
    assert snapshot["progress"]["status_reason"] == "completed"
    assert snapshot["progress"]["status_detail"] is None
    assert snapshot["results"] == []
    assert snapshot["alerts"] == []
