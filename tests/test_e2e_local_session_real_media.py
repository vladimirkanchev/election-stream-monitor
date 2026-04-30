"""Curated real-media end-to-end local session tests.

This file stays intentionally smaller than the ground-truth matrix. It protects
high-signal local-session behaviors with real fixtures while the broader case
matrix lives in the dedicated ground-truth suites.
"""

from pathlib import Path

import pytest

from tests.e2e_session_test_support import (
    assert_completed_session,
    configure_session_output,
    install_isolated_csv_stores,
    run_and_read_local_session,
)


pytestmark = [pytest.mark.e2e, pytest.mark.slow]


def _run_real_local_session(
    monkeypatch,
    tmp_path: Path,
    *,
    mode: str,
    input_path: Path,
    selected_detectors: list[str],
):
    """Run one real-media local session with isolated persistence.

    This keeps the individual tests focused on behavior, not setup plumbing.
    """
    configure_session_output(monkeypatch, tmp_path)
    install_isolated_csv_stores(monkeypatch, tmp_path)
    return run_and_read_local_session(
        mode=mode,
        input_path=input_path,
        selected_detectors=selected_detectors,
    )


def _assert_video_metric_sources(
    snapshot: dict[str, object],
    expected_source_names: set[str],
) -> None:
    """Assert the `video_metrics` rows cover the expected source names."""
    assert {
        event["payload"]["source_name"]
        for event in snapshot["results"]
        if event["detector_id"] == "video_metrics"
    } == expected_source_names


def test_e2e_local_session_with_real_mp4_produces_alerts(
    monkeypatch,
    tmp_path: Path,
    media_fixture_dir: Path,
) -> None:
    """A real local mp4 run should persist readable results and at least one alert."""
    video_path = media_fixture_dir / "video_files" / "black_trigger.mp4"

    metadata, snapshot = _run_real_local_session(
        monkeypatch,
        tmp_path,
        mode="video_files",
        input_path=video_path,
        selected_detectors=["video_metrics"],
    )

    assert_completed_session(metadata, snapshot)
    assert snapshot["progress"]["processed_count"] >= 5
    assert len(snapshot["results"]) >= 5
    assert len(snapshot["alerts"]) >= 1
    assert snapshot["latest_result"]["payload"]["source_group"] == video_path.name
    assert snapshot["latest_result"]["payload"]["window_index"] is not None
    assert any(
        event["payload"]["black_detected"]
        for event in snapshot["results"]
    )


def test_e2e_local_session_with_real_hls_segments_processes_playlist_order(
    monkeypatch,
    tmp_path: Path,
    media_fixture_dir: Path,
) -> None:
    """A real HLS folder run should process playlist-ordered segments and capture detections."""
    segment_dir = media_fixture_dir / "video_segments" / "black_trigger"
    expected_segments = sorted(segment_dir.glob("segment_*.ts"))

    metadata, snapshot = _run_real_local_session(
        monkeypatch,
        tmp_path,
        mode="video_segments",
        input_path=segment_dir,
        selected_detectors=["video_metrics"],
    )

    assert_completed_session(metadata, snapshot)
    assert snapshot["progress"]["processed_count"] == len(expected_segments)
    assert len(snapshot["results"]) == len(expected_segments)
    _assert_video_metric_sources(snapshot, {path.name for path in expected_segments})
    assert any(
        event["payload"]["black_detected"]
        for event in snapshot["results"]
    )


def test_e2e_local_session_with_long_mp4_runs_dual_detectors_across_all_windows(
    monkeypatch,
    tmp_path: Path,
    media_fixture_dir: Path,
) -> None:
    """Long mp4 fixtures should exercise both detectors across a full multi-window run."""
    video_path = media_fixture_dir / "video_files" / "clean_baseline_long.mp4"

    metadata, snapshot = _run_real_local_session(
        monkeypatch,
        tmp_path,
        mode="video_files",
        input_path=video_path,
        selected_detectors=["video_metrics", "video_blur"],
    )

    assert_completed_session(metadata, snapshot)
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == 10
    assert snapshot["progress"]["latest_result_detectors"] == ["video_metrics", "video_blur"]
    assert len(snapshot["results"]) == 20
    assert {event["detector_id"] for event in snapshot["results"]} == {
        "video_metrics",
        "video_blur",
    }


def test_e2e_local_session_with_long_hls_runs_dual_detectors_across_playlist(
    monkeypatch,
    tmp_path: Path,
    media_fixture_dir: Path,
) -> None:
    """Long HLS fixtures should exercise both detectors across the full segment set."""
    segment_dir = media_fixture_dir / "video_segments" / "clean_baseline_long"
    expected_segments = sorted(segment_dir.glob("segment_*.ts"))

    metadata, snapshot = _run_real_local_session(
        monkeypatch,
        tmp_path,
        mode="video_segments",
        input_path=segment_dir,
        selected_detectors=["video_metrics", "video_blur"],
    )

    assert_completed_session(metadata, snapshot)
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == len(expected_segments)
    assert snapshot["progress"]["latest_result_detectors"] == ["video_metrics", "video_blur"]
    assert len(snapshot["results"]) == len(expected_segments) * 2
    assert {event["detector_id"] for event in snapshot["results"]} == {
        "video_metrics",
        "video_blur",
    }
    _assert_video_metric_sources(snapshot, {path.name for path in expected_segments})
