"""Lifecycle-oriented session runner tests over the real local HTTP/HLS loader seam."""

from pathlib import Path
from typing import cast

from analyzer_contract import AnalyzerRegistration
from session_io import read_session_snapshot
from session_runner import run_local_session
from tests.session_runner_api_stream_test_support import (
    _build_blur_analyzer,
    _build_cancelling_blur_analyzer,
    _build_video_metrics_analyzer,
    _configure_http_hls_runner_test,
    _media_playlist,
    _patch_processor_with_analyzer,
    _patch_processor_with_analyzers,
    _segment_routes,
    _serve_local_hls,
)


def _progress(snapshot: dict[str, object]) -> dict[str, object]:
    """Return the progress payload from one persisted runner snapshot."""
    return cast(dict[str, object], snapshot["progress"])


def _results(snapshot: dict[str, object]) -> list[dict[str, object]]:
    """Return the persisted results list from one runner snapshot."""
    return cast(list[dict[str, object]], snapshot["results"])


def _alerts(snapshot: dict[str, object]) -> list[dict[str, object]]:
    """Return the persisted alerts list from one runner snapshot."""
    return cast(list[dict[str, object]], snapshot["alerts"])


def _session(snapshot: dict[str, object]) -> dict[str, object]:
    """Return the persisted session metadata section from one runner snapshot."""
    return cast(dict[str, object], snapshot["session"])


def _latest_result(snapshot: dict[str, object]) -> dict[str, object]:
    """Return the persisted latest-result section from one runner snapshot."""
    return cast(dict[str, object], snapshot["latest_result"])


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
        "segment_000.ts": 0.40,
        "segment_001.ts": 0.42,
        "segment_002.ts": 0.95,
        "segment_003.ts": 0.95,
        "segment_004.ts": 0.94,
        "segment_005.ts": 0.45,
        "segment_006.ts": 0.44,
        "segment_007.ts": 0.43,
        "segment_008.ts": 0.95,
        "segment_009.ts": 0.96,
        "segment_010.ts": 0.94,
    }
    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer(scores),
        supported_modes=("api_stream",),
    )

    routes: dict[str, object] = {
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
                _media_playlist(6, "segment_006.ts", "segment_007.ts", endlist=False),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                _media_playlist(8, "segment_008.ts", "segment_009.ts", endlist=False),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                _media_playlist(10, "segment_010.ts"),
                "application/vnd.apple.mpegurl",
            ),
        ],
    }
    routes.update(
        _segment_routes(*(f"segment_{index:03d}.ts" for index in range(11)))
    )

    with _serve_local_hls(routes) as base_url:
        metadata = run_local_session(
            mode="api_stream",
            input_path=f"{base_url}/live/index.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-http-complete",
        )

    snapshot = read_session_snapshot(metadata.session_id)
    session_data = _session(snapshot)
    progress_data = _progress(snapshot)
    results = _results(snapshot)
    alerts = _alerts(snapshot)

    assert metadata.status == "completed"
    assert session_data["status"] == "completed"
    assert progress_data["status"] == "completed"
    assert progress_data["processed_count"] == 11
    assert progress_data["current_item"] == "segment_010.ts"
    assert len(results) == 11
    assert progress_data["alert_count"] == 2
    assert len(alerts) == 2
    assert [alert["window_index"] for alert in alerts] == [4, 9]
    assert [alert["source_name"] for alert in alerts] == [
        "segment_004.ts",
        "segment_009.ts",
    ]


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
            analyzer=_build_video_metrics_analyzer(),
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

    routes: dict[str, object] = {
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
    progress_data = _progress(snapshot)
    latest_result = _latest_result(snapshot)

    assert metadata.status == "completed"
    assert progress_data["processed_count"] == 2
    assert progress_data["latest_result_detectors"] == [
        "video_metrics",
        "video_blur",
    ]
    assert progress_data["latest_result_detector"] == "video_blur"
    assert len(_results(snapshot)) == 4
    assert latest_result["detector_id"] == "video_blur"


def test_run_local_session_http_hls_api_stream_cancels_end_to_end(
    monkeypatch, tmp_path: Path
) -> None:
    """A real local HTTP HLS run should persist a cancelled snapshot once the user stops it."""
    _configure_http_hls_runner_test(
        monkeypatch,
        tmp_path,
        session_id="session-api-http-cancel",
    )

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_cancelling_blur_analyzer(session_id="session-api-http-cancel"),
        supported_modes=("api_stream",),
    )

    routes: dict[str, object] = {
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
    session_data = _session(snapshot)
    progress_data = _progress(snapshot)

    assert metadata.status == "cancelled"
    assert session_data["status"] == "cancelled"
    assert progress_data["status"] == "cancelled"
    assert progress_data["processed_count"] == 1
    assert len(_results(snapshot)) == 1
    assert progress_data["status_reason"] == "cancel_requested"
    assert progress_data["status_detail"] == "Cancellation requested after iteration"


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

    routes: dict[str, object] = {
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
    session_data = _session(snapshot)
    progress_data = _progress(snapshot)

    assert metadata.status == "completed"
    assert session_data["status"] == "completed"
    assert progress_data["status"] == "completed"
    assert progress_data["processed_count"] == 2
    assert progress_data["current_item"] == "segment_001.ts"
    assert len(_results(snapshot)) == 2
    assert progress_data["status_reason"] == "idle_poll_budget_exhausted"
    assert progress_data["status_detail"] == "Idle poll budget exhausted"
