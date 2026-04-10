"""Tests for detector helpers, schemas, and media-tool failure fallbacks.

These tests intentionally cover both normal detector output shape and the
current degraded behavior when ffmpeg or ffprobe time out, fail, or return
unexpected payloads.
"""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import config
from detectors import analyze_video_blur, analyze_video_metrics


def test_analyze_video_metrics_returns_expected_schema(
    monkeypatch, tmp_path: Path
) -> None:
    """Video black-screen analysis should return the current metrics row schema."""
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video-bytes")

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None, timeout=None):  # noqa: ANN001
        _ = (stdout, stderr, text, check, timeout)
        if cmd[0] == "ffprobe":
            return SimpleNamespace(stdout=json.dumps({"format": {"duration": "2.0"}}))
        return SimpleNamespace(
            stderr="black_start:0 black_end:1.5 black_duration:1.5\n",
        )

    monkeypatch.setattr("detectors.subprocess.run", fake_run)

    result = analyze_video_metrics(file_path=video_path)

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

def test_analyze_video_metrics_handles_invalid_ffprobe_output(
    monkeypatch, tmp_path: Path
) -> None:
    """Video metrics should fall back cleanly when ffprobe returns invalid output."""
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video-bytes")

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None, timeout=None):  # noqa: ANN001
        _ = (stdout, stderr, text, check, timeout)
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
    """Blur analysis should produce the current normalized rolling-window schema."""
    video_path = tmp_path / "sample.ts"
    video_path.write_bytes(b"video-bytes")

    frame_size = config.VIDEO_BLUR_SAMPLE_WIDTH * config.VIDEO_BLUR_SAMPLE_HEIGHT
    flat_frame = bytes([0] * frame_size)
    raw_frames = flat_frame * 3

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None, timeout=None):  # noqa: ANN001
        _ = (cmd, stdout, stderr, text, check, timeout)
        return SimpleNamespace(returncode=0, stdout=raw_frames, stderr=b"")

    monkeypatch.setattr("detectors.subprocess.run", fake_run)

    result = analyze_video_blur(file_path=video_path)

    assert set(result) == set(config.BLUR_METRICS_COLUMNS)
    assert result["analyzer"] == "video_blur"
    assert result["source_type"] == "video"
    assert result["source_group"] == video_path.parent.name
    assert result["source_name"] == video_path.name
    assert result["window_index"] is None
    assert result["sample_count"] == 3
    assert result["blur_score"] == 1.0
    assert result["blur_detected"] is True
    assert result["window_size"] == 3
    assert result["consecutive_blurry_windows"] == 1


def test_analyze_video_metrics_handles_ffprobe_timeout(
    monkeypatch, tmp_path: Path
) -> None:
    """Video metrics should degrade safely when ffprobe times out."""
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video-bytes")

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None, timeout=None):  # noqa: ANN001
        _ = (stdout, stderr, text, check, timeout)
        if cmd[0] == "ffprobe":
            raise subprocess.TimeoutExpired(cmd, timeout=timeout or 10)
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

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None, timeout=None):  # noqa: ANN001
        _ = (stdout, stderr, text, check, timeout)
        raise subprocess.TimeoutExpired(cmd, timeout=timeout or 20)

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

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None, timeout=None):  # noqa: ANN001
        _ = (cmd, stderr, text, check, timeout)
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"decode failed")

    monkeypatch.setattr("detectors.subprocess.run", fake_run)

    result = analyze_video_blur(file_path=video_path)

    assert result["sample_count"] == 0
    assert result["blur_score"] == 0.0
    assert result["blur_detected"] is False
