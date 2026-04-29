"""Failure-oriented seam tests for `api_stream` session runs.

Read this file when you want the failed-session contract for the live runner.
It groups the cases where work has to end in `failed`, including:
- loader terminal failures
- partial-progress terminal failures
- temporary per-chunk detector failures that are tolerated
- unrecoverable processing failures that must surface and persist
"""

from pathlib import Path

import pytest
import session_runner
from session_io import read_session_snapshot
from session_runner import run_local_session
from stream_loader import FakeApiStreamLoader
from tests.session_runner_api_stream_test_support import (
    _assert_basic_completed_snapshot,
    _build_blur_analyzer,
    _build_flaky_blur_analyzer,
    _build_result_only_bundle,
    _configure_api_stream_runner_test,
    _fake_chunk_event,
    _fake_terminal_failure_event,
    _fake_temporary_failure_event,
    _install_static_api_stream_loader,
    _patch_runner_bundle,
    _patch_processor_with_analyzer,
)


def test_run_local_session_persists_failed_api_stream_when_loader_hits_terminal_error(
    monkeypatch, tmp_path: Path
) -> None:
    """A terminal loader failure should create a failed live-session snapshot."""
    fake_loader = FakeApiStreamLoader(
        [_fake_terminal_failure_event(message="playlist permanently unavailable")]
    )
    _configure_api_stream_runner_test(monkeypatch, tmp_path, loader=fake_loader)

    with pytest.raises(ValueError, match="playlist permanently unavailable"):
        run_local_session(
            mode="api_stream",
            input_path="https://example.com/live/playlist.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-loader-terminal",
        )

    snapshot = read_session_snapshot("session-api-loader-terminal")

    assert snapshot["session"]["status"] == "failed"
    assert snapshot["progress"]["status"] == "failed"
    assert snapshot["progress"]["processed_count"] == 0
    assert snapshot["progress"]["total_count"] == 0
    assert snapshot["results"] == []
    assert snapshot["alerts"] == []


def test_run_local_session_preserves_partial_progress_before_fake_loader_terminal_failure(
    monkeypatch, tmp_path: Path
) -> None:
    """Accepted live chunks should remain persisted if a later fake-loader failure becomes terminal."""
    fake_loader = FakeApiStreamLoader(
        [
            _fake_chunk_event(tmp_path, chunk_index=0, current_item="live-window-000.ts"),
            _fake_chunk_event(tmp_path, chunk_index=1, current_item="live-window-001.ts"),
            _fake_terminal_failure_event(
                message="seam loader disconnected after partial progress"
            ),
        ]
    )
    _configure_api_stream_runner_test(monkeypatch, tmp_path, loader=fake_loader)

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

    with pytest.raises(
        ValueError, match="seam loader disconnected after partial progress"
    ):
        run_local_session(
            mode="api_stream",
            input_path="https://example.com/live/playlist.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-partial-then-terminal",
        )

    snapshot = read_session_snapshot("session-api-partial-then-terminal")

    assert snapshot["session"]["status"] == "failed"
    assert snapshot["progress"]["status"] == "failed"
    assert snapshot["progress"]["processed_count"] == 2
    assert snapshot["progress"]["current_item"] == "live-window-001.ts"
    assert snapshot["progress"]["status_reason"] == "source_unreachable"
    assert (
        snapshot["progress"]["status_detail"]
        == "seam loader disconnected after partial progress"
    )
    assert len(snapshot["results"]) == 2
    assert snapshot["alerts"] == []


def test_run_local_session_continues_after_temporary_live_chunk_detector_failure(
    monkeypatch, tmp_path: Path
) -> None:
    """One bad live chunk should not fail the whole api-stream session."""
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
        analyzer=_build_flaky_blur_analyzer(
            failing_windows={1},
            failure_message_factory=lambda _window_index: "temporary chunk decode failure",
        ),
        supported_modes=("api_stream",),
    )

    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-flaky",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    _assert_basic_completed_snapshot(
        snapshot,
        processed_count=3,
        current_item="live-window-003.ts",
        result_count=2,
    )


def test_run_local_session_fails_processing_after_earlier_skipped_temporary_chunk(
    monkeypatch, tmp_path: Path
) -> None:
    """A later analyzer failure should still persist a failed run even after earlier temporary loader noise."""
    fake_loader = FakeApiStreamLoader(
        [
            _fake_chunk_event(tmp_path, chunk_index=0, current_item="live-window-000.ts"),
            _fake_temporary_failure_event(
                chunk_index=1,
                current_item="live-window-001.ts",
                message="temporary fetch timeout",
            ),
            _fake_chunk_event(tmp_path, chunk_index=1, current_item="live-window-001.ts"),
        ]
    )
    _configure_api_stream_runner_test(monkeypatch, tmp_path, loader=fake_loader)

    _patch_runner_bundle(
        monkeypatch,
        _build_result_only_bundle(
            fail_on_call=2,
            failure_message="processing failed after temporary chunk",
        ),
    )

    with pytest.raises(ValueError, match="processing failed after temporary chunk"):
        run_local_session(
            mode="api_stream",
            input_path="https://example.com/live/playlist.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-fail-after-noise",
        )

    snapshot = read_session_snapshot("session-api-fail-after-noise")

    assert snapshot["session"]["status"] == "failed"
    assert snapshot["progress"]["status"] == "failed"
    assert snapshot["progress"]["processed_count"] == 1
    assert snapshot["progress"]["status_reason"] == "source_unreachable"
    assert "processing failed after temporary chunk" in str(
        snapshot["progress"]["status_detail"]
    )
    assert len(snapshot["results"]) == 1


def test_run_local_session_marks_remote_api_stream_failed_when_processing_raises(
    monkeypatch, tmp_path: Path
) -> None:
    """Unrecoverable live processing errors should persist failed session state."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)
    logged: list[tuple[str, tuple[object, ...]]] = []

    _install_static_api_stream_loader(
        monkeypatch,
        tmp_path,
        source_group="stream-a",
        names=["live-window-001.ts", "live-window-002.ts", "live-window-003.ts"],
    )
    _patch_runner_bundle(
        monkeypatch,
        _build_result_only_bundle(
            fail_on_call=2,
            failure_message="stream reader disconnected",
        ),
    )
    monkeypatch.setattr(
        session_runner.logger,
        "error",
        lambda message, *args: logged.append((message, args)),
    )

    try:
        run_local_session(
            mode="api_stream",
            input_path="https://example.com/live/playlist.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-failed",
        )
    except ValueError:
        snapshot = read_session_snapshot("session-api-failed")
        assert snapshot["session"]["status"] == "failed"
        assert snapshot["progress"]["status"] == "failed"
        assert snapshot["progress"]["processed_count"] == 1
        assert len(snapshot["results"]) == 1
        assert logged
        message, args = logged[0]
        assert message == "Session %s failed: %s [%s]"
        assert args[0] == "session-api-failed"
        assert "stream reader disconnected" in str(args[1])
        assert "session_id='session-api-failed'" in str(args[2])
        assert "source_kind='api_stream'" in str(args[2])
        assert "current_item='live-window-001.ts'" in str(args[2])
        assert "session_end_reason='terminal_failure'" in str(args[2])
        assert "processed_chunk_count=1" in str(args[2])
        assert "temp_cleanup_success_count=2" in str(args[2])
    else:
        raise AssertionError(
            "Expected the session runner to surface the processing failure"
        )
