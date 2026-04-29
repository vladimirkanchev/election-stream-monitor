"""Progress- and multi-detector-oriented seam tests for `api_stream` session runs.

Read this file when you want the progress-shaping side of the live runner.
These cases keep longer-running and multi-detector behavior together:
- repeated temporary detector failures with eventual completion
- alert re-entry across a longer blur sequence
- multi-detector progress fields and latest-result coherence
"""

from pathlib import Path

from analyzer_contract import AnalyzerRegistration
from session_io import read_session_snapshot
from session_runner import run_local_session
from tests.session_runner_api_stream_test_support import (
    _assert_basic_completed_snapshot,
    _build_blur_analyzer,
    _build_flaky_blur_analyzer,
    _build_video_metrics_analyzer,
    _configure_api_stream_runner_test,
    _install_static_api_stream_loader,
    _patch_processor_with_analyzer,
    _patch_processor_with_analyzers,
)


def test_run_local_session_tolerates_repeated_temporary_live_chunk_failures(
    monkeypatch, tmp_path: Path
) -> None:
    """Repeated live-chunk detector failures should still allow the session to complete."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)

    _install_static_api_stream_loader(
        monkeypatch,
        tmp_path,
        source_group="stream-a",
        names=[f"live-window-{index:03d}.ts" for index in range(1, 9)],
    )

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_flaky_blur_analyzer(failing_windows={1, 3, 5}),
        supported_modes=("api_stream",),
    )

    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-repeated-flaky",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    _assert_basic_completed_snapshot(
        snapshot,
        processed_count=8,
        current_item="live-window-008.ts",
        result_count=5,
    )


def test_run_local_session_live_like_blur_progression_tracks_alert_reentry(
    monkeypatch, tmp_path: Path
) -> None:
    """Live-like slice sequences should persist progress and timed blur alerts."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)

    names = [
        "live-window-001.ts",
        "live-window-002.ts",
        "live-window-003.ts",
        "live-window-004.ts",
        "live-window-005.ts",
        "live-window-006.ts",
        "live-window-007.ts",
        "live-window-008.ts",
    ]
    scores = {
        "live-window-001.ts": 0.82,
        "live-window-002.ts": 0.79,
        "live-window-003.ts": 0.60,
        "live-window-004.ts": 0.40,
        "live-window-005.ts": 0.42,
        "live-window-006.ts": 0.45,
        "live-window-007.ts": 0.81,
        "live-window-008.ts": 0.77,
    }
    _install_static_api_stream_loader(
        monkeypatch,
        tmp_path,
        source_group="stream-a",
        names=names,
    )

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer(scores),
        supported_modes=("api_stream",),
    )

    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-blur",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["progress"]["processed_count"] == 8
    assert snapshot["progress"]["alert_count"] == 2
    assert [alert["window_index"] for alert in snapshot["alerts"]] == [2, 7]
    assert [alert["source_name"] for alert in snapshot["alerts"]] == [
        "live-window-003.ts",
        "live-window-008.ts",
    ]


def test_run_local_session_persists_two_detector_progress_for_api_stream(
    monkeypatch, tmp_path: Path
) -> None:
    """A fake live run with two detectors should keep multi-detector progress fields coherent."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)

    _install_static_api_stream_loader(
        monkeypatch,
        tmp_path,
        source_group="stream-a",
        names=["live-window-001.ts", "live-window-002.ts"],
    )

    registrations = [
        AnalyzerRegistration(
            name="video_metrics",
            analyzer=_build_video_metrics_analyzer(),
            store_name="video_metrics",
            supported_modes=("api_stream",),
            supported_suffixes=(".ts",),
            display_name="Metrics Analyzer",
            description="Live metrics test detector",
            produces_alerts=True,
        ),
        AnalyzerRegistration(
            name="video_blur",
            analyzer=_build_blur_analyzer(
                {
                    "live-window-001.ts": 0.2,
                    "live-window-002.ts": 0.25,
                }
            ),
            store_name="blur_metrics",
            supported_modes=("api_stream",),
            supported_suffixes=(".ts",),
            display_name="Blur Analyzer",
            description="Live blur test detector",
            produces_alerts=True,
        ),
    ]
    _patch_processor_with_analyzers(monkeypatch, registrations=registrations)

    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_metrics", "video_blur"],
        session_id="session-api-two-detectors",
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
