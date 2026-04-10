"""Pure analyzer functions for local video files and HLS segment windows."""

import json
import re
import subprocess
import time
from pathlib import Path
from statistics import median

import config
from analyzer_contract import AnalyzerResult
from logger import logger
from source_validation import validate_local_media_size


def analyze_video_metrics(
    file_path: Path,
    prefix: str | None = None,
    source_group: str | None = None,
    source_name: str | None = None,
    window_index: int | None = None,
    window_start_sec: float | None = None,
    window_duration_sec: float | None = None,
) -> AnalyzerResult:
    """Analyze one video file for black-screen intervals.

    The detector keeps the historical ``video_metrics`` id so the current
    plugin/frontend wiring stays stable, but the implementation now performs a
    real black-screen pass over video inputs.
    """
    _ = prefix
    video_path = Path(file_path)
    validate_local_media_size(video_path)
    start_time = time.time()

    display_source_name = source_name or video_path.name
    display_source_group = source_group or video_path.parent.name or video_path.name
    duration_sec = (
        round(window_duration_sec, 3)
        if window_duration_sec is not None
        else _probe_video_duration(video_path)
    )
    picture_threshold = config.VIDEO_BLACK_PICTURE_THRESHOLD
    pixel_threshold = config.VIDEO_BLACK_PIXEL_THRESHOLD
    min_duration = config.VIDEO_BLACK_MIN_DURATION_SEC

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "info",
        "-nostats",
    ]
    if window_start_sec is not None:
        cmd.extend(["-ss", f"{window_start_sec:.3f}"])
    cmd.extend(["-i", str(video_path.resolve())])
    if window_duration_sec is not None:
        cmd.extend(["-t", f"{window_duration_sec:.3f}"])
    cmd.extend(
        [
            "-vf",
            (
                "blackdetect="
                f"d={min_duration}:pic_th={picture_threshold}:pix_th={pixel_threshold}"
            ),
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    proc = _run_media_command(
        cmd,
        stderr=subprocess.PIPE,
        text=True,
        timeout=config.FFMPEG_TIMEOUT_SEC,
        failure_label=f"ffmpeg blackdetect on {video_path.name}",
    )
    if proc is None:
        black_durations = []
    else:
        black_durations = _parse_blackdetect_durations(proc.stderr)
    total_black_sec = round(sum(black_durations), 3)
    longest_black_sec = round(max(black_durations, default=0.0), 3)
    black_ratio = round(total_black_sec / duration_sec, 3) if duration_sec > 0 else 0.0

    return {
        "analyzer": "video_metrics",
        "source_type": "video",
        "source_group": display_source_group,
        "source_name": display_source_name,
        "window_index": window_index,
        "window_start_sec": round(window_start_sec, 3) if window_start_sec is not None else None,
        "window_duration_sec": round(window_duration_sec, 3)
        if window_duration_sec is not None
        else None,
        "timestamp_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "processing_sec": round(time.time() - start_time, 3),
        "duration_sec": round(duration_sec, 3),
        "black_detected": bool(black_durations),
        "black_segment_count": len(black_durations),
        "total_black_sec": total_black_sec,
        "longest_black_sec": longest_black_sec,
        "black_ratio": black_ratio,
        "picture_threshold_used": picture_threshold,
        "pixel_threshold_used": pixel_threshold,
        "min_duration_sec": min_duration,
    }

def analyze_video_blur(
    file_path: Path,
    prefix: str | None = None,
    source_group: str | None = None,
    source_name: str | None = None,
    window_index: int | None = None,
    window_start_sec: float | None = None,
    window_duration_sec: float | None = None,
) -> AnalyzerResult:
    """Analyze one video using sampled frames and rolling blur windows.

    Per sampled frame:
    - compute a normalized sharpness estimate in ``0..1`` using strong local
      edge differences
    - derive a blur value from both absolute sharpness and robust percentile
      normalization inside the sampled clip

    The final ``blur_score`` is the maximum rolling median across sampled blur
    values, which gives a stable ``0..1`` metric for files, segments, and later
    API-stream chunks.
    """
    _ = prefix
    video_path = Path(file_path)
    validate_local_media_size(video_path)
    start_time = time.time()
    threshold = config.VIDEO_BLUR_ALERT_THRESHOLD
    display_source_name = source_name or video_path.name
    display_source_group = source_group or video_path.parent.name or video_path.name

    sample_width = config.VIDEO_BLUR_SAMPLE_WIDTH
    sample_height = config.VIDEO_BLUR_SAMPLE_HEIGHT
    raw_frames = _extract_sampled_gray_frames(
        file_path=video_path,
        width=sample_width,
        height=sample_height,
        fps=config.VIDEO_BLUR_SAMPLE_FPS,
        max_samples=config.VIDEO_BLUR_MAX_SAMPLES,
        window_start_sec=window_start_sec,
        window_duration_sec=window_duration_sec,
    )

    frame_scores = [
        _frame_sharpness_score(sample_width, sample_height, pixels)
        for pixels in raw_frames
    ]
    sharpness_p10 = _percentile(frame_scores, 10) if frame_scores else 0.0
    sharpness_p90 = _percentile(frame_scores, 90) if frame_scores else 0.0
    per_frame_blur_scores = [
        _combined_blur_score(score, sharpness_p10, sharpness_p90)
        for score in frame_scores
    ]
    window_size = min(
        config.VIDEO_BLUR_WINDOW_SIZE,
        len(per_frame_blur_scores) if per_frame_blur_scores else 1,
    )
    rolling_window_scores = _rolling_window_medians(per_frame_blur_scores, window_size)
    blur_score = round(max(rolling_window_scores, default=0.0), 3)
    consecutive_blurry_windows = _longest_threshold_run(rolling_window_scores, threshold)
    required_windows = min(
        config.VIDEO_BLUR_MIN_CONSECUTIVE_WINDOWS,
        len(rolling_window_scores) if rolling_window_scores else 1,
    )

    return {
        "analyzer": "video_blur",
        "source_type": "video",
        "source_group": display_source_group,
        "source_name": display_source_name,
        "window_index": window_index,
        "window_start_sec": round(window_start_sec, 3) if window_start_sec is not None else None,
        "window_duration_sec": round(window_duration_sec, 3)
        if window_duration_sec is not None
        else None,
        "timestamp_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "processing_sec": round(time.time() - start_time, 3),
        "sample_count": len(frame_scores),
        "sharpness_p10": round(sharpness_p10, 3),
        "sharpness_p90": round(sharpness_p90, 3),
        "blur_score": blur_score,
        "blur_detected": blur_score >= threshold
        and consecutive_blurry_windows >= required_windows,
        "threshold_used": threshold,
        "window_size": window_size,
        "consecutive_blurry_windows": consecutive_blurry_windows,
    }


def _probe_video_duration(file_path: Path) -> float:
    """Return the container duration in seconds or ``0.0`` on failure."""
    validate_local_media_size(file_path)
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(file_path),
    ]
    probe = _run_media_command(
        cmd,
        stdout=subprocess.PIPE,
        text=True,
        timeout=config.FFPROBE_TIMEOUT_SEC,
        failure_label=f"ffprobe duration probe on {file_path.name}",
    )
    if probe is None:
        return 0.0
    try:
        data = json.loads(probe.stdout)
        return float(data.get("format", {}).get("duration", 0.0) or 0.0)
    except (OSError, ValueError, json.JSONDecodeError):
        logger.warning("ffprobe failed to read duration for %s", file_path.name)
        return 0.0


def _parse_blackdetect_durations(stderr_output: str) -> list[float]:
    """Extract black interval durations from ffmpeg ``blackdetect`` output."""
    pattern = re.compile(
        r"black_start:(?P<start>[\d\.]+)\s+black_end:(?P<end>[\d\.]+)\s"
        r"+black_duration:(?P<dur>[\d\.]+)"
    )
    return [float(duration) for _, _, duration in pattern.findall(stderr_output)]


def _extract_sampled_gray_frames(
    file_path: Path,
    width: int,
    height: int,
    fps: float,
    max_samples: int,
    window_start_sec: float | None = None,
    window_duration_sec: float | None = None,
) -> list[bytes]:
    """Extract fixed-size grayscale samples as raw frame chunks."""
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostats",
    ]
    if window_start_sec is not None:
        cmd.extend(["-ss", f"{window_start_sec:.3f}"])
    cmd.extend(["-i", str(file_path.resolve())])
    if window_duration_sec is not None:
        cmd.extend(["-t", f"{window_duration_sec:.3f}"])
    cmd.extend(
        [
            "-vf",
            f"fps={fps},scale={width}:{height},format=gray",
            "-frames:v",
            str(max_samples),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ]
    )
    proc = _run_media_command(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=config.FFMPEG_TIMEOUT_SEC,
        failure_label=f"ffmpeg blur sample extraction on {file_path.name}",
    )
    if proc is None or proc.returncode != 0 or not proc.stdout:
        logger.warning("ffmpeg failed to extract blur samples for %s", file_path.name)
        return []

    frame_size = width * height
    if frame_size <= 0:
        return []

    frames: list[bytes] = []
    for index in range(0, len(proc.stdout), frame_size):
        chunk = proc.stdout[index : index + frame_size]
        if len(chunk) == frame_size:
            frames.append(chunk)
    return frames


def _run_media_command(
    cmd: list[str],
    *,
    timeout: float,
    failure_label: str,
    **kwargs,
):
    """Run one ffmpeg/ffprobe command with timeout-aware failure handling."""
    try:
        return subprocess.run(
            cmd,
            check=False,
            timeout=timeout,
            **kwargs,
        )
    except subprocess.TimeoutExpired:
        logger.warning("%s timed out after %.1f sec", failure_label, timeout)
        return None


def _frame_sharpness_score(width: int, height: int, pixels: bytes) -> float:
    """Return a normalized sharpness estimate in ``0..1`` for one frame."""
    if width < 2 or height < 2 or not pixels:
        return 0.0

    diffs: list[int] = []
    row_stride = width

    for row in range(height - 1):
        base_index = row * row_stride
        next_row = (row + 1) * row_stride
        for col in range(width - 1):
            index = base_index + col
            diffs.append(abs(pixels[index] - pixels[index + 1]))
            diffs.append(abs(pixels[index] - pixels[next_row + col]))

    if not diffs:
        return 0.0
    return round(_percentile(diffs, 90) / 255.0, 6)


def _combined_blur_score(score: float, p10: float, p90: float) -> float:
    """Blend absolute and percentile-normalized blur into a ``0..1`` score."""
    absolute_blur = 1.0 - _clamp(score)
    dynamic_sharpness = _robust_normalize(score, p10, p90)
    dynamic_blur = 1.0 - dynamic_sharpness
    return round(max(absolute_blur, dynamic_blur), 6)


def _rolling_window_medians(values: list[float], window_size: int) -> list[float]:
    """Return rolling medians for the supplied window size."""
    if not values:
        return []
    if window_size <= 1:
        return values[:]
    return [
        round(median(values[index : index + window_size]), 6)
        for index in range(0, len(values) - window_size + 1)
    ]


def _longest_threshold_run(values: list[float], threshold: float) -> int:
    """Return the longest consecutive run whose values meet the threshold."""
    longest = 0
    current = 0
    for value in values:
        if value >= threshold:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _robust_normalize(value: float, p10: float, p90: float) -> float:
    """Normalize one sharpness value into ``0..1`` using robust percentiles."""
    span = p90 - p10
    if span <= 1e-6:
        return _clamp(value)
    return _clamp((value - p10) / span)


def _percentile(values: list[float] | list[int], percentile: float) -> float:
    """Compute a linear percentile without adding a numpy dependency."""
    if not values:
        return 0.0
    sorted_values = sorted(float(value) for value in values)
    if len(sorted_values) == 1:
        return sorted_values[0]

    rank = (len(sorted_values) - 1) * percentile / 100.0
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return (
        sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight
    )


def _clamp(value: float) -> float:
    """Clamp one floating-point value into the ``0..1`` interval."""
    return max(0.0, min(1.0, value))
