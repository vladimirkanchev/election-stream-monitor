"""Integration tests for detectors using tiny real media fixtures."""

from pathlib import Path

from detectors import analyze_video_blur, analyze_video_metrics


def test_video_metrics_detects_black_screen_in_real_mp4(
    media_fixture_dir: Path,
) -> None:
    """Black-screen detector should flag the permanent black-trigger clip."""
    video_path = media_fixture_dir / "video_files" / "black_trigger.mp4"

    result = analyze_video_metrics(video_path)

    assert result["source_name"] == video_path.name
    assert result["duration_sec"] >= 5.0
    assert result["black_detected"] is True
    assert result["black_segment_count"] >= 1
    assert result["longest_black_sec"] >= 1.0
    assert result["black_ratio"] >= 0.2


def test_video_metrics_detects_black_screen_in_real_ts_segment(
    media_fixture_dir: Path,
) -> None:
    """Black-screen detector should work on the permanent black-trigger segment."""
    segment_path = (
        media_fixture_dir
        / "video_segments"
        / "black_trigger"
        / "segment_0006.ts"
    )

    result = analyze_video_metrics(segment_path)

    assert result["source_name"] == segment_path.name
    assert result["black_detected"] is True
    assert result["black_segment_count"] >= 1
    assert result["black_ratio"] >= 0.9


def test_video_blur_detects_real_blurry_video(media_fixture_dir: Path) -> None:
    """Blur detector should flag the permanent blurred clip."""
    blurry_video = media_fixture_dir / "video_files" / "blur_trigger.mp4"

    result = analyze_video_blur(blurry_video)

    assert result["sample_count"] >= 3
    assert result["blur_score"] >= result["threshold_used"]
    assert result["blur_detected"] is True
    assert result["consecutive_blurry_windows"] >= 1
