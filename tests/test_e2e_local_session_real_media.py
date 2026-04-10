"""Real-media end-to-end local session tests."""

from pathlib import Path

import config
import processor
import session_runner
from session_io import read_session_snapshot
from session_runner import run_local_session
from stores import BufferedCsvStore


def _install_isolated_stores(monkeypatch, tmp_path: Path) -> None:
    """Redirect result stores to temporary CSV files for one test run."""
    video_store = BufferedCsvStore(
        columns=config.VIDEO_METRICS_COLUMNS,
        file_path=tmp_path / "metrics" / "video_metrics.csv",
        buffer_size=1,
    )
    blur_store = BufferedCsvStore(
        columns=config.BLUR_METRICS_COLUMNS,
        file_path=tmp_path / "metrics" / "blur_metrics.csv",
        buffer_size=1,
    )

    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {
            "video_metrics": video_store,
            "blur_metrics": blur_store,
        },
    )
    monkeypatch.setattr(session_runner, "black_frame_store", video_store)
    monkeypatch.setattr(session_runner, "blur_metrics_store", blur_store)


def test_e2e_local_session_with_real_mp4_produces_alerts(
    monkeypatch,
    tmp_path: Path,
    media_fixture_dir: Path,
) -> None:
    """A real local mp4 run should persist readable results and at least one alert."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    _install_isolated_stores(monkeypatch, tmp_path)

    video_path = media_fixture_dir / "video_files" / "black_trigger.mp4"

    metadata = run_local_session(
        mode="video_files",
        input_path=video_path,
        selected_detectors=["video_metrics"],
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["session"]["status"] == "completed"
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
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    _install_isolated_stores(monkeypatch, tmp_path)

    segment_dir = media_fixture_dir / "video_segments" / "black_trigger"
    expected_segments = sorted(segment_dir.glob("segment_*.ts"))

    metadata = run_local_session(
        mode="video_segments",
        input_path=segment_dir,
        selected_detectors=["video_metrics"],
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["session"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == len(expected_segments)
    assert len(snapshot["results"]) == len(expected_segments)
    assert {
        event["payload"]["source_name"]
        for event in snapshot["results"]
    } == {path.name for path in expected_segments}
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
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    _install_isolated_stores(monkeypatch, tmp_path)

    video_path = media_fixture_dir / "video_files" / "clean_baseline_long.mp4"

    metadata = run_local_session(
        mode="video_files",
        input_path=video_path,
        selected_detectors=["video_metrics", "video_blur"],
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
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
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    _install_isolated_stores(monkeypatch, tmp_path)

    segment_dir = media_fixture_dir / "video_segments" / "clean_baseline_long"
    expected_segments = sorted(segment_dir.glob("segment_*.ts"))

    metadata = run_local_session(
        mode="video_segments",
        input_path=segment_dir,
        selected_detectors=["video_metrics", "video_blur"],
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == len(expected_segments)
    assert snapshot["progress"]["latest_result_detectors"] == ["video_metrics", "video_blur"]
    assert len(snapshot["results"]) == len(expected_segments) * 2
    assert {event["detector_id"] for event in snapshot["results"]} == {
        "video_metrics",
        "video_blur",
    }
    assert {
        event["payload"]["source_name"]
        for event in snapshot["results"]
        if event["detector_id"] == "video_metrics"
    } == {path.name for path in expected_segments}
