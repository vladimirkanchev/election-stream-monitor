"""Production detector tests for typed rows, media-tool fallbacks, and metric contracts.

These tests intentionally stay close to the production runtime surface:

- detector rows should expose the current typed in-memory contract
- ffprobe / ffmpeg failures should fail closed without surprising callers
- blur and black metrics should keep their current export semantics
"""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import config
from analyzer_contract import VideoBlurRow, VideoMetricsRow
from detectors import (
    BlurScoreSummary,
    BlurWindowMetrics,
    _bounded_sample_size,
    _frame_transition_motion_scores,
    _is_short_tail_window_without_samples,
    _resolve_blur_sample_fps,
    analyze_video_blur,
    analyze_video_metrics,
)


BLUR_SAMPLE_BOUNDS = (
    config.VIDEO_BLUR_SAMPLE_MAX_WIDTH,
    config.VIDEO_BLUR_SAMPLE_MAX_HEIGHT,
)


def test_analyze_video_metrics_returns_expected_schema(
    monkeypatch, tmp_path: Path
) -> None:
    """Black-screen analysis should return the current metrics row schema."""
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video-bytes")

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        _ = kwargs
        if cmd[0] == "ffprobe":
            return SimpleNamespace(stdout=json.dumps({"format": {"duration": "2.0"}}))
        return SimpleNamespace(
            stderr="black_start:0 black_end:1.5 black_duration:1.5\n",
        )

    monkeypatch.setattr("detectors.subprocess.run", fake_run)

    result = analyze_video_metrics(file_path=video_path)

    assert isinstance(result, VideoMetricsRow)
    assert set(result) == set(config.VIDEO_METRICS_COLUMNS)
    assert result["analyzer"] == "video_metrics"
    assert result["source_type"] == "video"
    assert result["source_group"] == video_path.parent.name
    assert result["source_name"] == video_path.name
    assert result["window_index"] is None
    assert result["window_start_sec"] is None
    assert result["window_duration_sec"] is None
    assert result["duration_sec"] == 2.0
    assert result["black_detected"] is True
    assert result["black_segment_count"] == 1
    assert result["total_black_sec"] == 1.5
    assert result["longest_black_sec"] == 1.5
    assert result["black_ratio"] == 0.75
    assert result["picture_threshold_used"] == config.VIDEO_BLACK_PICTURE_THRESHOLD
    assert result["pixel_threshold_used"] == config.VIDEO_BLACK_PIXEL_THRESHOLD
    assert result["min_duration_sec"] == config.VIDEO_BLACK_MIN_DURATION_SEC


def test_analyze_video_metrics_handles_invalid_ffprobe_output(
    monkeypatch, tmp_path: Path
) -> None:
    """Video metrics should fall back cleanly when ffprobe returns invalid output."""
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video-bytes")

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        _ = kwargs
        if cmd[0] == "ffprobe":
            return SimpleNamespace(stdout="not-json")
        return SimpleNamespace(stderr="")

    monkeypatch.setattr("detectors.subprocess.run", fake_run)

    result = analyze_video_metrics(file_path=video_path)

    assert result["duration_sec"] == 0.0
    assert result["black_detected"] is False
    assert result["black_ratio"] == 0.0
    assert result["total_black_sec"] == 0.0


def test_analyze_video_blur_returns_expected_schema(
    monkeypatch, tmp_path: Path
) -> None:
    """Blur analysis should produce the current rolling-window schema."""
    video_path = tmp_path / "sample.ts"
    video_path.write_bytes(b"video-bytes")

    width = 4
    height = 4
    sharp_frame = bytes(
        [
            0, 255, 0, 255,
            255, 0, 255, 0,
            0, 255, 0, 255,
            255, 0, 255, 0,
        ]
    )
    raw_frames = sharp_frame * 3

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        _ = kwargs
        if cmd[0] == "ffprobe":
            return SimpleNamespace(
                stdout=json.dumps({"streams": [{"width": width, "height": height}]})
            )
        return SimpleNamespace(returncode=0, stdout=raw_frames, stderr=b"")

    monkeypatch.setattr("detectors.subprocess.run", fake_run)

    result = analyze_video_blur(file_path=video_path)

    assert isinstance(result, VideoBlurRow)
    assert set(result) == set(config.BLUR_METRICS_COLUMNS)
    assert result["analyzer"] == "video_blur"
    assert result["source_type"] == "video"
    assert result["source_group"] == video_path.parent.name
    assert result["source_name"] == video_path.name
    assert result["window_index"] is None
    assert result["sample_count"] == 3
    assert result["motion_mean"] == 0.0
    assert result["motion_p90"] == 0.0
    assert result["blur_score"] == 0.0
    assert result["blur_detected"] is False
    assert result["window_size"] == 3
    assert result["consecutive_blurry_windows"] == 0


def test_typed_detector_rows_serialize_to_flat_dict() -> None:
    """Typed detector rows should still expose a flat persistence-friendly dict."""
    blur_row = VideoBlurRow(
        analyzer="video_blur",
        source_type="video",
        source_group="fixtures",
        source_name="sample.mp4",
        window_index=0,
        window_start_sec=0.0,
        window_duration_sec=1.0,
        timestamp_utc="2026-06-05 12:00:00",
        processing_sec=0.01,
        sample_count=5,
        sharpness_p10=0.1,
        sharpness_p90=0.2,
        motion_mean=0.03,
        motion_p90=0.05,
        blur_score=0.4,
        blur_detected=False,
        threshold_used=0.88,
        window_size=3,
        consecutive_blurry_windows=0,
    )

    serialized = blur_row.to_dict()

    assert isinstance(serialized, dict)
    assert serialized["analyzer"] == "video_blur"
    assert serialized["source_name"] == "sample.mp4"
    assert serialized["blur_score"] == 0.4


def test_analyze_video_blur_ignores_effectively_black_frames(
    monkeypatch, tmp_path: Path
) -> None:
    """Black frames should be excluded from blur scoring."""
    video_path = tmp_path / "sample.ts"
    video_path.write_bytes(b"video-bytes")

    width = 4
    height = 4
    frame_size = width * height
    black_frame = bytes([0] * frame_size)
    raw_frames = black_frame * 3

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        _ = kwargs
        if cmd[0] == "ffprobe":
            return SimpleNamespace(
                stdout=json.dumps({"streams": [{"width": width, "height": height}]})
            )
        return SimpleNamespace(returncode=0, stdout=raw_frames, stderr=b"")

    monkeypatch.setattr("detectors.subprocess.run", fake_run)

    result = analyze_video_blur(file_path=video_path)

    assert result["sample_count"] == 0
    assert result["motion_mean"] == 0.0
    assert result["motion_p90"] == 0.0
    assert result["blur_score"] == 0.0
    assert result["blur_detected"] is False


def test_analyze_video_blur_preserves_zero_sample_fallback_contract(
    monkeypatch, tmp_path: Path
) -> None:
    """Blur analysis should stay stable when black filtering removes every sample."""
    video_path = tmp_path / "sample.ts"
    video_path.write_bytes(b"video-bytes")

    monkeypatch.setattr("detectors._resolve_blur_sample_size", lambda path: (4, 4))
    monkeypatch.setattr(
        "detectors._extract_sampled_gray_frames",
        lambda **kwargs: [bytes([0] * 16), bytes([1] * 16)],
    )
    monkeypatch.setattr("detectors._select_blur_analysis_frames", lambda frames: [])

    result = analyze_video_blur(file_path=video_path)

    assert result["sample_count"] == 0
    assert result["sharpness_p10"] == 0.0
    assert result["sharpness_p90"] == 0.0
    assert result["motion_mean"] == 0.0
    assert result["motion_p90"] == 0.0
    assert result["blur_score"] == 0.0
    assert result["blur_detected"] is False
    assert result["window_size"] == 1
    assert result["consecutive_blurry_windows"] == 0


def test_analyze_video_blur_filters_frames_at_exact_black_ratio_boundary(
    monkeypatch, tmp_path: Path
) -> None:
    """Frames at the exact black-picture boundary should be excluded from blur analysis."""
    video_path = tmp_path / "sample.ts"
    video_path.write_bytes(b"video-bytes")

    width = 10
    height = 10
    black_boundary_frame = bytes([0] * 98 + [255, 255])
    sharp_frame = bytes(
        [
            0,
            255,
            0,
            255,
            255,
            0,
            255,
            0,
            0,
            255,
        ]
        * 10
    )
    raw_frames = black_boundary_frame + sharp_frame + sharp_frame

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        _ = kwargs
        if cmd[0] == "ffprobe":
            return SimpleNamespace(
                stdout=json.dumps({"streams": [{"width": width, "height": height}]})
            )
        return SimpleNamespace(returncode=0, stdout=raw_frames, stderr=b"")

    monkeypatch.setattr("detectors.subprocess.run", fake_run)

    result = analyze_video_blur(file_path=video_path)

    assert result["sample_count"] == 2
    assert result["motion_mean"] == 0.0
    assert result["motion_p90"] == 0.0
    assert result["blur_detected"] is False


def test_analyze_video_blur_exports_measured_sharpness_percentiles(
    monkeypatch, tmp_path: Path
) -> None:
    """Blur detector rows should preserve measured sharpness percentile values."""
    video_path = tmp_path / "sample.ts"
    video_path.write_bytes(b"video-bytes")

    monkeypatch.setattr("detectors._resolve_blur_sample_size", lambda path: (4, 4))
    monkeypatch.setattr("detectors._extract_sampled_gray_frames", lambda **kwargs: [b"frame"] * 3)
    monkeypatch.setattr("detectors._select_blur_analysis_frames", lambda frames: frames)
    monkeypatch.setattr(
        "detectors._measure_blur_window",
        lambda **kwargs: BlurWindowMetrics(
            frame_scores=[0.1, 0.5, 0.9],
            motion_scores=[0.0, 0.0, 0.0],
            sharpness_p10=0.15,
            sharpness_p90=0.85,
            per_frame_blur_scores=[0.2, 0.3, 0.4],
        ),
    )
    monkeypatch.setattr(
        "detectors._summarize_blur_scores",
        lambda per_frame_blur_scores, threshold: BlurScoreSummary(
            window_size=3,
            rolling_scores=[0.3],
            blur_score=0.3,
            consecutive_blurry_windows=0,
            required_windows=1,
        ),
    )

    result = analyze_video_blur(file_path=video_path)

    assert result["sharpness_p10"] == 0.15
    assert result["sharpness_p90"] == 0.85


def test_analyze_video_blur_exports_summary_window_fields(
    monkeypatch, tmp_path: Path
) -> None:
    """Blur detector rows should preserve summarized rolling-window blur fields."""
    video_path = tmp_path / "sample.ts"
    video_path.write_bytes(b"video-bytes")

    monkeypatch.setattr("detectors._resolve_blur_sample_size", lambda path: (4, 4))
    monkeypatch.setattr("detectors._extract_sampled_gray_frames", lambda **kwargs: [b"frame"] * 4)
    monkeypatch.setattr("detectors._select_blur_analysis_frames", lambda frames: frames)
    monkeypatch.setattr(
        "detectors._measure_blur_window",
        lambda **kwargs: BlurWindowMetrics(
            frame_scores=[0.2, 0.3, 0.4, 0.5],
            motion_scores=[0.0, 0.05, 0.05, 0.0],
            sharpness_p10=0.21,
            sharpness_p90=0.49,
            per_frame_blur_scores=[0.91, 0.92, 0.93, 0.94],
        ),
    )
    monkeypatch.setattr(
        "detectors._summarize_blur_scores",
        lambda per_frame_blur_scores, threshold: BlurScoreSummary(
            window_size=3,
            rolling_scores=[0.92, 0.93],
            blur_score=0.93,
            consecutive_blurry_windows=2,
            required_windows=2,
        ),
    )

    result = analyze_video_blur(file_path=video_path)

    assert result["blur_score"] == 0.93
    assert result["blur_detected"] is True
    assert result["window_size"] == 3
    assert result["consecutive_blurry_windows"] == 2


def test_analyze_video_metrics_aggregates_multiple_black_segments(
    monkeypatch, tmp_path: Path
) -> None:
    """Black-screen analysis should preserve counts and totals across multiple intervals."""
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video-bytes")

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        _ = kwargs
        if cmd[0] == "ffprobe":
            return SimpleNamespace(stdout=json.dumps({"format": {"duration": "4.0"}}))
        return SimpleNamespace(
            stderr=(
                "black_start:0 black_end:0.4 black_duration:0.4\n"
                "black_start:2.0 black_end:3.0 black_duration:1.0\n"
            ),
        )

    monkeypatch.setattr("detectors.subprocess.run", fake_run)

    result = analyze_video_metrics(file_path=video_path)

    assert result["black_segment_count"] == 2
    assert result["total_black_sec"] == 1.4
    assert result["longest_black_sec"] == 1.0
    assert result["black_ratio"] == 0.35


def test_analyze_video_metrics_ignores_malformed_blackdetect_lines(
    monkeypatch, tmp_path: Path
) -> None:
    """Black-screen parsing should ignore malformed stderr lines and keep valid intervals."""
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video-bytes")

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        _ = kwargs
        if cmd[0] == "ffprobe":
            return SimpleNamespace(stdout=json.dumps({"format": {"duration": "4.0"}}))
        return SimpleNamespace(
            stderr=(
                "noise that should be ignored\n"
                "black_start:oops black_end:1.0 black_duration:broken\n"
                "black_start:1.0 black_end:2.0 black_duration:1.0\n"
            ),
        )

    monkeypatch.setattr("detectors.subprocess.run", fake_run)

    result = analyze_video_metrics(file_path=video_path)

    assert result["black_segment_count"] == 1
    assert result["total_black_sec"] == 1.0
    assert result["longest_black_sec"] == 1.0
    assert result["black_ratio"] == 0.25


def test_frame_transition_motion_scores_capture_normalized_frame_deltas() -> None:
    """Motion scoring should distinguish still and changing sampled frames."""
    first = bytes([0, 0, 0, 0])
    second = bytes([255, 255, 255, 255])
    third = bytes([255, 255, 255, 255])

    assert _frame_transition_motion_scores([first, second, third]) == [0.0, 1.0, 0.0]


def test_frame_transition_motion_scores_fail_closed_for_mismatched_frame_lengths() -> None:
    """Motion scoring should fail closed when adjacent sampled frames do not align."""
    first = bytes([0, 0, 0, 0])
    second = bytes([255, 255, 255])

    assert _frame_transition_motion_scores([first, second]) == [0.0, 0.0]


def test_bounded_sample_size_preserves_aspect_ratio_within_limits() -> None:
    """Blur sampling should keep source aspect while staying inside configured bounds."""
    assert _bounded_sample_size(
        source_width=1920,
        source_height=1080,
        max_width=BLUR_SAMPLE_BOUNDS[0],
        max_height=BLUR_SAMPLE_BOUNDS[1],
    ) == (320, 180)

    assert _bounded_sample_size(
        source_width=640,
        source_height=360,
        max_width=BLUR_SAMPLE_BOUNDS[0],
        max_height=BLUR_SAMPLE_BOUNDS[1],
    ) == (320, 180)

    assert _bounded_sample_size(
        source_width=240,
        source_height=135,
        max_width=BLUR_SAMPLE_BOUNDS[0],
        max_height=BLUR_SAMPLE_BOUNDS[1],
    ) == (240, 135)


def test_resolve_blur_sample_fps_keeps_short_windows_motion_aware() -> None:
    """Short local windows should be sampled densely enough for motion guards."""
    assert _resolve_blur_sample_fps(None) == config.VIDEO_BLUR_SAMPLE_FPS
    assert _resolve_blur_sample_fps(3.0) == config.VIDEO_BLUR_SAMPLE_FPS
    assert _resolve_blur_sample_fps(1.0) == config.VIDEO_BLUR_MAX_MOTION_SAMPLE_FPS


def test_analyze_video_blur_contracts_rolling_window_to_available_samples(
    monkeypatch, tmp_path: Path
) -> None:
    """Blur summary should contract the rolling window when fewer samples are available."""
    video_path = tmp_path / "sample.ts"
    video_path.write_bytes(b"video-bytes")

    monkeypatch.setattr("detectors._resolve_blur_sample_size", lambda path: (4, 4))
    monkeypatch.setattr("detectors._extract_sampled_gray_frames", lambda **kwargs: [b"frame"] * 2)
    monkeypatch.setattr("detectors._select_blur_analysis_frames", lambda frames: frames)
    monkeypatch.setattr(
        "detectors._measure_blur_window",
        lambda **kwargs: BlurWindowMetrics(
            frame_scores=[0.2, 0.3],
            motion_scores=[0.0, 0.05],
            sharpness_p10=0.21,
            sharpness_p90=0.29,
            per_frame_blur_scores=[0.91, 0.92],
        ),
    )

    result = analyze_video_blur(file_path=video_path)

    assert result["sample_count"] == 2
    assert result["window_size"] == 2
    assert result["consecutive_blurry_windows"] == 1


def test_analyze_video_blur_exports_zero_motion_for_single_usable_frame(
    monkeypatch, tmp_path: Path
) -> None:
    """A single usable blur frame should export an empty-transition motion series as zeros."""
    video_path = tmp_path / "sample.ts"
    video_path.write_bytes(b"video-bytes")

    width = 4
    height = 4
    sharp_frame = bytes(
        [
            0, 255, 0, 255,
            255, 0, 255, 0,
            0, 255, 0, 255,
            255, 0, 255, 0,
        ]
    )

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        _ = kwargs
        if cmd[0] == "ffprobe":
            return SimpleNamespace(
                stdout=json.dumps({"streams": [{"width": width, "height": height}]})
            )
        return SimpleNamespace(returncode=0, stdout=sharp_frame, stderr=b"")

    monkeypatch.setattr("detectors.subprocess.run", fake_run)

    result = analyze_video_blur(file_path=video_path)

    assert result["sample_count"] == 1
    assert result["motion_mean"] == 0.0
    assert result["motion_p90"] == 0.0
    assert _resolve_blur_sample_fps(0.5) == config.VIDEO_BLUR_MAX_MOTION_SAMPLE_FPS


def test_analyze_video_metrics_handles_ffprobe_timeout(
    monkeypatch, tmp_path: Path
) -> None:
    """Video metrics should degrade safely when ffprobe times out."""
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video-bytes")

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        _ = kwargs
        if cmd[0] == "ffprobe":
            raise subprocess.TimeoutExpired(cmd, timeout=kwargs.get("timeout") or 10)
        return SimpleNamespace(stderr="")

    monkeypatch.setattr("detectors.subprocess.run", fake_run)

    result = analyze_video_metrics(file_path=video_path)

    assert result["duration_sec"] == 0.0
    assert result["black_detected"] is False


def test_analyze_video_blur_handles_ffmpeg_timeout(
    monkeypatch, tmp_path: Path
) -> None:
    """Blur analysis should degrade safely when ffmpeg sample extraction times out."""
    video_path = tmp_path / "sample.ts"
    video_path.write_bytes(b"video-bytes")

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        _ = kwargs
        raise subprocess.TimeoutExpired(cmd, timeout=kwargs.get("timeout") or 20)

    monkeypatch.setattr("detectors.subprocess.run", fake_run)

    result = analyze_video_blur(file_path=video_path)

    assert result["sample_count"] == 0
    assert result["blur_score"] == 0.0
    assert result["blur_detected"] is False


def test_analyze_video_blur_handles_ffmpeg_non_zero_exit(
    monkeypatch, tmp_path: Path
) -> None:
    """Blur analysis should degrade safely when ffmpeg exits with a failure status."""
    video_path = tmp_path / "sample.ts"
    video_path.write_bytes(b"video-bytes")

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        _ = (cmd, kwargs)
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"decode failed")

    monkeypatch.setattr("detectors.subprocess.run", fake_run)

    result = analyze_video_blur(file_path=video_path)

    assert result["sample_count"] == 0
    assert result["blur_score"] == 0.0
    assert result["blur_detected"] is False


def test_analyze_video_blur_ignores_empty_short_tail_window_without_warning(
    monkeypatch, tmp_path: Path
) -> None:
    """A valid very short tail slice should not log a failure when ffmpeg returns no frames."""
    video_path = tmp_path / "sample.ts"
    video_path.write_bytes(b"video-bytes")
    warnings: list[str] = []

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        _ = kwargs
        if cmd[0] == "ffprobe":
            return SimpleNamespace(
                stdout=json.dumps({"streams": [{"width": 4, "height": 4}]})
            )
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("detectors.subprocess.run", fake_run)
    monkeypatch.setattr("detectors.logger.warning", lambda message, *args: warnings.append(message % args))

    result = analyze_video_blur(
        file_path=video_path,
        window_start_sec=4.0,
        window_duration_sec=0.1,
    )

    assert result["sample_count"] == 0
    assert result["blur_score"] == 0.0
    assert warnings == []


def test_short_tail_window_without_samples_matches_blur_sampling_interval() -> None:
    """The short-tail helper should only mark slices shorter than one sample interval."""
    assert _is_short_tail_window_without_samples(window_duration_sec=0.1, fps=6.0) is True
    assert _is_short_tail_window_without_samples(window_duration_sec=0.2, fps=6.0) is False
