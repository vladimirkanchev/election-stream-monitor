"""Failure-oriented session runner tests over the real local HTTP/HLS loader seam."""

from pathlib import Path
from typing import cast

import pytest
import session_runner
import stream_loader_http_hls
from session_io import read_session_snapshot
from session_runner import run_local_session
from tests.session_runner_api_stream_test_support import (
    _build_blur_analyzer,
    _configure_http_hls_runner_test,
    _media_playlist,
    _patch_processor_with_analyzer,
    _segment_routes,
    _serve_local_hls,
)


def _progress(snapshot: dict[str, object]) -> dict[str, object]:
    """Return the progress payload from one persisted failure snapshot."""
    return cast(dict[str, object], snapshot["progress"])


def _results(snapshot: dict[str, object]) -> list[dict[str, object]]:
    """Return the persisted results list from one persisted failure snapshot."""
    return cast(list[dict[str, object]], snapshot["results"])


def _alerts(snapshot: dict[str, object]) -> list[dict[str, object]]:
    """Return the persisted alerts list from one persisted failure snapshot."""
    return cast(list[dict[str, object]], snapshot["alerts"])


def _session(snapshot: dict[str, object]) -> dict[str, object]:
    """Return the persisted session metadata section from one failure snapshot."""
    return cast(dict[str, object], snapshot["session"])


def test_run_local_session_http_hls_api_stream_persists_failed_snapshot_on_loader_budget_exhaustion(
    monkeypatch, tmp_path: Path
) -> None:
    """A real local HTTP HLS loader failure should persist a failed live-session snapshot."""
    _configure_http_hls_runner_test(
        monkeypatch,
        tmp_path,
        session_id="session-api-http-failed",
        config_overrides={"API_STREAM_MAX_RECONNECT_ATTEMPTS": 1},
    )

    routes: dict[str, object] = {
        "/live/index.m3u8": [
            (503, "busy", "text/plain"),
            (503, "busy", "text/plain"),
        ],
    }

    with _serve_local_hls(routes) as base_url:
        with pytest.raises(ValueError, match="reconnect budget exhausted"):
            run_local_session(
                mode="api_stream",
                input_path=f"{base_url}/live/index.m3u8",
                selected_detectors=["video_blur"],
                session_id="session-api-http-failed",
            )

    snapshot = read_session_snapshot("session-api-http-failed")
    session_data = _session(snapshot)
    progress_data = _progress(snapshot)

    assert session_data["status"] == "failed"
    assert progress_data["status"] == "failed"
    assert progress_data["processed_count"] == 0
    assert _results(snapshot) == []
    assert _alerts(snapshot) == []
    assert progress_data["status_reason"] == "source_unreachable"
    assert "reconnect_budget_exhausted" in str(progress_data["status_detail"])


def test_run_local_session_http_hls_api_stream_preserves_partial_progress_before_terminal_failure(
    monkeypatch, tmp_path: Path
) -> None:
    """A live run should keep accepted partial progress even if a later outage becomes terminal."""
    _configure_http_hls_runner_test(
        monkeypatch,
        tmp_path,
        session_id="session-api-http-partial-then-failed",
        config_overrides={"API_STREAM_MAX_RECONNECT_ATTEMPTS": 1},
    )

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer({"segment_000.ts": 0.82}),
        supported_modes=("api_stream",),
    )

    routes: dict[str, object] = {
        "/live/index.m3u8": [
            (
                200,
                _media_playlist(0, "segment_000.ts", endlist=False),
                "application/vnd.apple.mpegurl",
            ),
            (503, "busy", "text/plain"),
            (503, "busy", "text/plain"),
        ],
    }
    routes.update(_segment_routes("segment_000.ts"))

    with _serve_local_hls(routes) as base_url:
        with pytest.raises(ValueError, match="reconnect budget exhausted"):
            run_local_session(
                mode="api_stream",
                input_path=f"{base_url}/live/index.m3u8",
                selected_detectors=["video_blur"],
                session_id="session-api-http-partial-then-failed",
            )

    snapshot = read_session_snapshot("session-api-http-partial-then-failed")
    session_data = _session(snapshot)
    progress_data = _progress(snapshot)

    assert session_data["status"] == "failed"
    assert progress_data["status"] == "failed"
    assert progress_data["processed_count"] == 1
    assert progress_data["current_item"] == "segment_000.ts"
    assert len(_results(snapshot)) == 1
    assert progress_data["status_reason"] == "source_unreachable"
    assert "reconnect_budget_exhausted" in str(progress_data["status_detail"])


def test_run_local_session_http_hls_api_stream_persists_missing_segment_404_as_terminal_failure(
    monkeypatch, tmp_path: Path
) -> None:
    """A missing advertised segment should fail honestly after preserving earlier accepted work."""
    _configure_http_hls_runner_test(
        monkeypatch,
        tmp_path,
        session_id="session-api-http-missing-segment-404",
    )

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer({"segment_000.ts": 0.82}),
        supported_modes=("api_stream",),
    )

    routes: dict[str, object] = {
        "/live/index.m3u8": (
            200,
            _media_playlist(
                0,
                "segment_000.ts",
                "segment_001.ts",
                endlist=False,
            ),
            "application/vnd.apple.mpegurl",
        ),
        "/live/segment_000.ts": (200, b"000", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        with pytest.raises(ValueError, match="upstream returned HTTP 404"):
            run_local_session(
                mode="api_stream",
                input_path=f"{base_url}/live/index.m3u8",
                selected_detectors=["video_blur"],
                session_id="session-api-http-missing-segment-404",
            )

    snapshot = read_session_snapshot("session-api-http-missing-segment-404")
    session_data = _session(snapshot)
    progress_data = _progress(snapshot)

    assert session_data["status"] == "failed"
    assert progress_data["status"] == "failed"
    assert progress_data["processed_count"] == 1
    assert progress_data["current_item"] == "segment_000.ts"
    assert len(_results(snapshot)) == 1
    assert _alerts(snapshot) == []
    assert progress_data["status_reason"] == "source_unreachable"
    assert "api_stream upstream returned HTTP 404" in str(progress_data["status_detail"])


def test_run_local_session_http_hls_api_stream_preserves_partial_progress_before_runtime_limit_failure(
    monkeypatch, tmp_path: Path
) -> None:
    """A runtime safety stop should keep already accepted progress and results."""
    _configure_http_hls_runner_test(
        monkeypatch,
        tmp_path,
        session_id="session-api-http-runtime-after-progress",
        config_overrides={
            "API_STREAM_MAX_IDLE_PLAYLIST_POLLS": 10,
            "API_STREAM_MAX_SESSION_RUNTIME_SEC": 5.0,
        },
    )
    ticks = iter([0.0, 0.0, 6.0, 6.0, 6.0])
    monkeypatch.setattr(stream_loader_http_hls.time, "monotonic", lambda: next(ticks))

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer({"segment_000.ts": 0.82}),
        supported_modes=("api_stream",),
    )

    routes: dict[str, object] = {
        "/live/index.m3u8": (
            200,
            _media_playlist(0, "segment_000.ts", endlist=False),
            "application/vnd.apple.mpegurl",
        ),
    }
    routes.update(_segment_routes("segment_000.ts"))

    with _serve_local_hls(routes) as base_url:
        with pytest.raises(ValueError, match="session runtime exceeded max duration"):
            run_local_session(
                mode="api_stream",
                input_path=f"{base_url}/live/index.m3u8",
                selected_detectors=["video_blur"],
                session_id="session-api-http-runtime-after-progress",
            )

    snapshot = read_session_snapshot("session-api-http-runtime-after-progress")
    session_data = _session(snapshot)
    progress_data = _progress(snapshot)

    assert session_data["status"] == "failed"
    assert progress_data["status"] == "failed"
    assert progress_data["processed_count"] == 1
    assert progress_data["current_item"] == "segment_000.ts"
    assert len(_results(snapshot)) == 1
    assert progress_data["status_reason"] == "source_unreachable"
    assert "session runtime exceeded max duration" in str(progress_data["status_detail"])


def test_run_local_session_logs_api_stream_failure_summary_after_partial_progress(
    monkeypatch, tmp_path: Path
) -> None:
    """Terminal failure logging should still include accepted progress that happened before the outage."""
    _configure_http_hls_runner_test(
        monkeypatch,
        tmp_path,
        session_id="session-api-log-failed-after-progress",
        config_overrides={"API_STREAM_MAX_RECONNECT_ATTEMPTS": 1},
    )

    error_logs: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        session_runner.logger,
        "error",
        lambda message, *args: error_logs.append((message, args)),
    )

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer({"segment_000.ts": 0.82}),
        supported_modes=("api_stream",),
    )

    routes: dict[str, object] = {
        "/live/index.m3u8": [
            (
                200,
                _media_playlist(0, "segment_000.ts", endlist=False),
                "application/vnd.apple.mpegurl",
            ),
            (503, "busy", "text/plain"),
            (503, "busy", "text/plain"),
        ],
    }
    routes.update(_segment_routes("segment_000.ts"))

    with _serve_local_hls(routes) as base_url:
        with pytest.raises(ValueError, match="reconnect budget exhausted"):
            run_local_session(
                mode="api_stream",
                input_path=f"{base_url}/live/index.m3u8",
                selected_detectors=["video_blur"],
                session_id="session-api-log-failed-after-progress",
            )

    failure_logs = [
        args[2]
        for message, args in error_logs
        if message == "Session %s failed: %s [%s]"
    ]
    assert failure_logs
    assert any("processed_chunk_count=1" in str(entry) for entry in failure_logs)
    assert any("temp_cleanup_success_count=1" in str(entry) for entry in failure_logs)
    assert any(
        "terminal_failure_reason='reconnect_budget_exhausted:api_stream upstream returned HTTP 503'"
        in str(entry)
        for entry in failure_logs
    )
