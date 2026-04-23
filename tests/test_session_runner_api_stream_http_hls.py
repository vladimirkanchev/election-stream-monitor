"""Tests for session-runner behavior over the real local HTTP HLS loader seam.

This file holds the heavier end-to-end transport cases so ordinary local and
seam-based api_stream runner tests stay easier to scan and debug.
"""

from pathlib import Path

import pytest
from analyzer_contract import AnalyzerRegistration
import session_runner
from session_io import read_session_snapshot
from session_runner import run_local_session
from tests.session_runner_api_stream_test_support import (
    _build_blur_analyzer,
    _configure_http_hls_runner_test,
    _media_playlist,
    _patch_processor_with_analyzer,
    _patch_processor_with_analyzers,
    _segment_routes,
    _serve_local_hls,
)


def _build_metrics_analyzer():
    def analyzer(
        file_path: Path,
        prefix: str | None = None,
        source_group: str | None = None,
        source_name: str | None = None,
        window_index: int | None = None,
        window_start_sec: float | None = None,
        window_duration_sec: float | None = None,
    ) -> dict:
        _ = (file_path, prefix)
        return {
            "analyzer": "video_metrics",
            "source_type": "video",
            "source_name": str(source_name),
            "source_group": str(source_group),
            "timestamp_utc": f"2026-04-04 10:10:{int(window_index or 0):02d}",
            "processing_sec": 0.02,
            "black_ratio": 0.1,
            "longest_black_sec": 0.0,
            "window_index": window_index,
            "window_start_sec": window_start_sec,
            "window_duration_sec": window_duration_sec,
        }

    return analyzer


def test_run_local_session_http_hls_api_stream_completes_end_to_end(
    monkeypatch, tmp_path: Path
) -> None:
    """A real local HTTP HLS run should complete incrementally and persist results and alerts."""
    _configure_http_hls_runner_test(
        monkeypatch,
        tmp_path,
        session_id="session-api-http-complete",
    )

    scores = {
        "segment_000.ts": 0.82,
        "segment_001.ts": 0.79,
        "segment_002.ts": 0.60,
        "segment_003.ts": 0.40,
        "segment_004.ts": 0.42,
        "segment_005.ts": 0.45,
        "segment_006.ts": 0.81,
        "segment_007.ts": 0.77,
    }
    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer(scores),
        supported_modes=("api_stream",),
    )

    routes = {
        "/live/index.m3u8": [
            (
                200,
                _media_playlist(0, "segment_000.ts", "segment_001.ts", endlist=False),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                _media_playlist(2, "segment_002.ts", "segment_003.ts", endlist=False),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                _media_playlist(4, "segment_004.ts", "segment_005.ts", endlist=False),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                _media_playlist(6, "segment_006.ts", "segment_007.ts"),
                "application/vnd.apple.mpegurl",
            ),
        ],
    }
    routes.update(
        _segment_routes(*(f"segment_{index:03d}.ts" for index in range(8)))
    )

    with _serve_local_hls(routes) as base_url:
        metadata = run_local_session(
            mode="api_stream",
            input_path=f"{base_url}/live/index.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-http-complete",
        )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["session"]["status"] == "completed"
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == 8
    assert snapshot["progress"]["current_item"] == "segment_007.ts"
    assert len(snapshot["results"]) == 8
    assert snapshot["progress"]["alert_count"] == 2
    assert len(snapshot["alerts"]) == 2


def test_run_local_session_http_hls_api_stream_recovers_from_temporary_playlist_503_and_completes(
    monkeypatch, tmp_path: Path
) -> None:
    """A transient playlist 503 should still allow the runner to complete normally later."""
    _configure_http_hls_runner_test(
        monkeypatch,
        tmp_path,
        session_id="session-api-http-recover-complete",
    )

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer(
            {
                "segment_000.ts": 0.82,
                "segment_001.ts": 0.79,
                "segment_002.ts": 0.60,
                "segment_003.ts": 0.40,
            }
        ),
        supported_modes=("api_stream",),
    )

    routes = {
        "/live/index.m3u8": [
            (
                200,
                _media_playlist(0, "segment_000.ts", "segment_001.ts", endlist=False),
                "application/vnd.apple.mpegurl",
            ),
            (503, "busy", "text/plain"),
            (
                200,
                _media_playlist(2, "segment_002.ts", "segment_003.ts"),
                "application/vnd.apple.mpegurl",
            ),
        ],
    }
    routes.update(
        _segment_routes(
            "segment_000.ts",
            "segment_001.ts",
            "segment_002.ts",
            "segment_003.ts",
        )
    )

    with _serve_local_hls(routes) as base_url:
        metadata = run_local_session(
            mode="api_stream",
            input_path=f"{base_url}/live/index.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-http-recover-complete",
        )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["session"]["status"] == "completed"
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == 4
    assert snapshot["progress"]["current_item"] == "segment_003.ts"
    assert len(snapshot["results"]) == 4


def test_run_local_session_http_hls_api_stream_retries_http_429_then_completes(
    monkeypatch, tmp_path: Path
) -> None:
    """A transient 429 throttle should be recoverable at the real runner seam."""
    _configure_http_hls_runner_test(
        monkeypatch,
        tmp_path,
        session_id="session-api-http-429-complete",
    )

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer(
            {
                "segment_000.ts": 0.82,
                "segment_001.ts": 0.79,
            }
        ),
        supported_modes=("api_stream",),
    )

    routes = {
        "/live/index.m3u8": [
            (429, "slow down", "text/plain"),
            (
                200,
                _media_playlist(0, "segment_000.ts", "segment_001.ts"),
                "application/vnd.apple.mpegurl",
            ),
        ],
    }
    routes.update(_segment_routes("segment_000.ts", "segment_001.ts"))

    with _serve_local_hls(routes) as base_url:
        metadata = run_local_session(
            mode="api_stream",
            input_path=f"{base_url}/live/index.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-http-429-complete",
        )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["session"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == 2
    assert snapshot["progress"]["current_item"] == "segment_001.ts"
    assert len(snapshot["results"]) == 2


def test_run_local_session_http_hls_api_stream_persists_two_detector_progress(
    monkeypatch, tmp_path: Path
) -> None:
    """A real HTTP HLS run with two detectors should keep multi-detector progress fields coherent."""
    _configure_http_hls_runner_test(
        monkeypatch,
        tmp_path,
        session_id="session-api-http-two-detectors",
    )

    registrations = [
        AnalyzerRegistration(
            name="video_metrics",
            analyzer=_build_metrics_analyzer(),
            store_name="video_metrics",
            supported_modes=("api_stream",),
            supported_suffixes=(".ts",),
            display_name="Metrics Analyzer",
            description="HTTP HLS metrics test detector",
            produces_alerts=True,
        ),
        AnalyzerRegistration(
            name="video_blur",
            analyzer=_build_blur_analyzer(
                {
                    "segment_000.ts": 0.82,
                    "segment_001.ts": 0.79,
                }
            ),
            store_name="blur_metrics",
            supported_modes=("api_stream",),
            supported_suffixes=(".ts",),
            display_name="Blur Analyzer",
            description="HTTP HLS blur test detector",
            produces_alerts=True,
        ),
    ]
    _patch_processor_with_analyzers(
        monkeypatch,
        registrations=registrations,
    )

    routes = {
        "/live/index.m3u8": (
            200,
            _media_playlist(0, "segment_000.ts", "segment_001.ts"),
            "application/vnd.apple.mpegurl",
        ),
    }
    routes.update(_segment_routes("segment_000.ts", "segment_001.ts"))

    with _serve_local_hls(routes) as base_url:
        metadata = run_local_session(
            mode="api_stream",
            input_path=f"{base_url}/live/index.m3u8",
            selected_detectors=["video_metrics", "video_blur"],
            session_id="session-api-http-two-detectors",
        )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["progress"]["processed_count"] == 2
    assert snapshot["progress"]["latest_result_detectors"] == [
        "video_metrics",
        "video_blur",
    ]
    assert snapshot["progress"]["latest_result_detector"] == "video_blur"
    assert len(snapshot["results"]) == 4
    assert snapshot["latest_result"]["detector_id"] == "video_blur"


def test_run_local_session_http_hls_api_stream_cancels_end_to_end(
    monkeypatch, tmp_path: Path
) -> None:
    """A real local HTTP HLS run should persist a cancelled snapshot once the user stops it."""
    _configure_http_hls_runner_test(
        monkeypatch,
        tmp_path,
        session_id="session-api-http-cancel",
    )

    cancel_requested = {"done": False}

    def cancelling_blur_analyzer(
        file_path: Path,
        prefix: str | None = None,
        source_group: str | None = None,
        source_name: str | None = None,
        window_index: int | None = None,
        window_start_sec: float | None = None,
        window_duration_sec: float | None = None,
    ) -> dict:
        _ = (file_path, prefix, source_group)
        if not cancel_requested["done"]:
            cancel_requested["done"] = True
            from session_io import request_session_cancel

            request_session_cancel("session-api-http-cancel")
        return {
            "analyzer": "video_blur",
            "source_type": "video",
            "source_name": str(source_name),
            "source_group": str(source_group),
            "timestamp_utc": f"2026-04-04 10:00:{int(window_index or 0):02d}",
            "processing_sec": 0.01,
            "blur_detected": False,
            "blur_score": 0.2,
            "threshold_used": 0.72,
            "window_index": window_index,
            "window_start_sec": window_start_sec,
            "window_duration_sec": window_duration_sec,
        }

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=cancelling_blur_analyzer,
        supported_modes=("api_stream",),
    )

    routes = {
        "/live/index.m3u8": (
            200,
            _media_playlist(0, "segment_000.ts", "segment_001.ts", "segment_002.ts"),
            "application/vnd.apple.mpegurl",
        ),
    }
    routes.update(_segment_routes("segment_000.ts", "segment_001.ts", "segment_002.ts"))

    with _serve_local_hls(routes) as base_url:
        metadata = run_local_session(
            mode="api_stream",
            input_path=f"{base_url}/live/index.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-http-cancel",
        )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "cancelled"
    assert snapshot["session"]["status"] == "cancelled"
    assert snapshot["progress"]["status"] == "cancelled"
    assert snapshot["progress"]["processed_count"] == 1
    assert len(snapshot["results"]) == 1
    assert snapshot["progress"]["status_reason"] == "cancel_requested"
    assert (
        snapshot["progress"]["status_detail"]
        == "Cancellation requested after iteration"
    )


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

    routes = {
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

    assert snapshot["session"]["status"] == "failed"
    assert snapshot["progress"]["status"] == "failed"
    assert snapshot["progress"]["processed_count"] == 0
    assert snapshot["results"] == []
    assert snapshot["alerts"] == []
    assert snapshot["progress"]["status_reason"] == "source_unreachable"
    assert "reconnect_budget_exhausted" in str(snapshot["progress"]["status_detail"])


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

    routes = {
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

    assert snapshot["session"]["status"] == "failed"
    assert snapshot["progress"]["status"] == "failed"
    assert snapshot["progress"]["processed_count"] == 1
    assert snapshot["progress"]["current_item"] == "segment_000.ts"
    assert len(snapshot["results"]) == 1
    assert snapshot["progress"]["status_reason"] == "source_unreachable"
    assert "reconnect_budget_exhausted" in str(snapshot["progress"]["status_detail"])


def test_run_local_session_http_hls_api_stream_preserves_progress_across_temporary_outage_before_terminal_failure(
    monkeypatch, tmp_path: Path
) -> None:
    """Accepted work should survive a temporary segment outage before a later terminal reconnect failure."""
    _configure_http_hls_runner_test(
        monkeypatch,
        tmp_path,
        session_id="session-api-http-temp-then-terminal",
        config_overrides={"API_STREAM_MAX_RECONNECT_ATTEMPTS": 1},
    )

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer(
            {
                "segment_000.ts": 0.82,
                "segment_002.ts": 0.79,
            }
        ),
        supported_modes=("api_stream",),
    )

    routes = {
        "/live/index.m3u8": [
            (
                200,
                _media_playlist(
                    0,
                    "segment_000.ts",
                    "segment_001.ts",
                    "segment_002.ts",
                    endlist=False,
                ),
                "application/vnd.apple.mpegurl",
            ),
            (503, "busy", "text/plain"),
            (503, "busy", "text/plain"),
        ],
        "/live/segment_000.ts": (200, b"000", "video/mp2t"),
        "/live/segment_001.ts": (503, "temporarily busy", "text/plain"),
        "/live/segment_002.ts": (200, b"002", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        with pytest.raises(ValueError, match="reconnect budget exhausted"):
            run_local_session(
                mode="api_stream",
                input_path=f"{base_url}/live/index.m3u8",
                selected_detectors=["video_blur"],
                session_id="session-api-http-temp-then-terminal",
            )

    snapshot = read_session_snapshot("session-api-http-temp-then-terminal")

    assert snapshot["session"]["status"] == "failed"
    assert snapshot["progress"]["status"] == "failed"
    assert snapshot["progress"]["processed_count"] == 2
    assert snapshot["progress"]["current_item"] == "segment_002.ts"
    assert len(snapshot["results"]) == 2
    assert snapshot["progress"]["status_reason"] == "source_unreachable"
    assert "reconnect_budget_exhausted" in str(snapshot["progress"]["status_detail"])


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
    monkeypatch.setattr("stream_loader.time.monotonic", lambda: next(ticks))

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer({"segment_000.ts": 0.82}),
        supported_modes=("api_stream",),
    )

    routes = {
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

    assert snapshot["session"]["status"] == "failed"
    assert snapshot["progress"]["status"] == "failed"
    assert snapshot["progress"]["processed_count"] == 1
    assert snapshot["progress"]["current_item"] == "segment_000.ts"
    assert len(snapshot["results"]) == 1
    assert snapshot["progress"]["status_reason"] == "source_unreachable"
    assert "session runtime exceeded max duration" in str(snapshot["progress"]["status_detail"])


def test_run_local_session_logs_api_stream_failure_summary(
    monkeypatch, tmp_path: Path
) -> None:
    """Failed api_stream runs should log one terminal transport/session summary for operators."""
    _configure_http_hls_runner_test(
        monkeypatch,
        tmp_path,
        session_id="session-api-log-failed",
        config_overrides={"API_STREAM_MAX_RECONNECT_ATTEMPTS": 1},
    )

    error_logs: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(session_runner.logger, "error", lambda message, *args: error_logs.append((message, args)))

    routes = {
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
                session_id="session-api-log-failed",
            )

    failure_logs = [
        args[2]
        for message, args in error_logs
        if message == "Session %s failed: %s [%s]"
    ]
    assert failure_logs
    assert any("session_end_reason='terminal_failure'" in str(entry) for entry in failure_logs)
    assert any("source_url_class='hls_playlist_url'" in str(entry) for entry in failure_logs)
    assert any("reconnect_budget_exhaustion_count=1" in str(entry) for entry in failure_logs)
    assert any(
        "terminal_failure_reason='reconnect_budget_exhausted:api_stream upstream returned HTTP 503'"
        in str(entry)
        for entry in failure_logs
    )
    assert any("temp_cleanup_success_count=0" in str(entry) for entry in failure_logs)
    assert any("temp_cleanup_failure_count=0" in str(entry) for entry in failure_logs)


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

    routes = {
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


def test_run_local_session_http_hls_api_stream_stops_cleanly_after_idle_poll_budget(
    monkeypatch, tmp_path: Path
) -> None:
    """A non-ENDLIST live run should complete cleanly once the bounded idle poll policy is exhausted."""
    _configure_http_hls_runner_test(
        monkeypatch,
        tmp_path,
        session_id="session-api-http-idle-stop",
        config_overrides={"API_STREAM_MAX_IDLE_PLAYLIST_POLLS": 1},
    )

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer(
            {
                "segment_000.ts": 0.82,
                "segment_001.ts": 0.79,
            }
        ),
        supported_modes=("api_stream",),
    )

    routes = {
        "/live/index.m3u8": [
            (
                200,
                _media_playlist(0, "segment_000.ts", "segment_001.ts", endlist=False),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                _media_playlist(0, "segment_000.ts", "segment_001.ts", endlist=False),
                "application/vnd.apple.mpegurl",
            ),
        ],
    }
    routes.update(_segment_routes("segment_000.ts", "segment_001.ts"))

    with _serve_local_hls(routes) as base_url:
        metadata = run_local_session(
            mode="api_stream",
            input_path=f"{base_url}/live/index.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-http-idle-stop",
        )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["session"]["status"] == "completed"
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == 2
    assert snapshot["progress"]["current_item"] == "segment_001.ts"
    assert len(snapshot["results"]) == 2
    assert snapshot["progress"]["status_reason"] == "idle_poll_budget_exhausted"
    assert snapshot["progress"]["status_detail"] == "Idle poll budget exhausted"


def test_run_local_session_http_hls_api_stream_completes_after_reconnecting_then_going_idle(
    monkeypatch, tmp_path: Path
) -> None:
    """A transient reconnect followed by a quiet live stream should still settle as idle-bounded completion."""
    _configure_http_hls_runner_test(
        monkeypatch,
        tmp_path,
        session_id="session-api-http-reconnect-then-idle",
        config_overrides={"API_STREAM_MAX_IDLE_PLAYLIST_POLLS": 1},
    )

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer(
            {
                "segment_000.ts": 0.82,
                "segment_001.ts": 0.79,
            }
        ),
        supported_modes=("api_stream",),
    )

    routes = {
        "/live/index.m3u8": [
            (
                200,
                _media_playlist(0, "segment_000.ts", "segment_001.ts", endlist=False),
                "application/vnd.apple.mpegurl",
            ),
            (503, "busy", "text/plain"),
            (
                200,
                _media_playlist(0, "segment_000.ts", "segment_001.ts", endlist=False),
                "application/vnd.apple.mpegurl",
            ),
        ],
    }
    routes.update(_segment_routes("segment_000.ts", "segment_001.ts"))

    with _serve_local_hls(routes) as base_url:
        metadata = run_local_session(
            mode="api_stream",
            input_path=f"{base_url}/live/index.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-http-reconnect-then-idle",
        )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["session"]["status"] == "completed"
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == 2
    assert snapshot["progress"]["current_item"] == "segment_001.ts"
    assert snapshot["progress"]["status_reason"] == "idle_poll_budget_exhausted"
    assert snapshot["progress"]["status_detail"] == "Idle poll budget exhausted"
