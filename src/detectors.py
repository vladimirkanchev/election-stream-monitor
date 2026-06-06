"""Production detectors for local video inputs.

At the current project stage the production runtime supports a deliberately
small detector surface:

- ``video_metrics`` for black-screen intervals
- ``video_blur`` for strong blur and motion context

This module owns signal extraction only. Alert entry, suppression, recovery,
and operator wording live in ``alert_rules.py``. Public analyzers return typed
detector rows that are easy to reason about in memory and still flatten cleanly
at the processor/storage boundary.
"""

import json
import re
import subprocess  # nosec B404
import time
from dataclasses import dataclass
from math import floor
from pathlib import Path
from statistics import median

import config
from analyzer_contract import AnalyzerResult, DetectorRowBase, VideoBlurRow, VideoMetricsRow
from logger import logger
from source_validation import validate_local_media_size


@dataclass(frozen=True)
class BlurWindowMetrics:
    """Blur features derived once from one sampled grayscale window."""

    frame_scores: list[float]
    motion_scores: list[float]
    sharpness_p10: float
    sharpness_p90: float
    per_frame_blur_scores: list[float]

    @property
    def sample_count(self) -> int:
        """Return the number of usable frames in the analyzed window."""
        return len(self.frame_scores)

    @property
    def motion_mean(self) -> float:
        """Return the average frame-to-frame motion across the window."""
        return _mean(self.motion_scores)

    @property
    def motion_p90(self) -> float:
        """Return the upper-end motion level across the window."""
        return _percentile(self.motion_scores, 90) if self.motion_scores else 0.0


@dataclass(frozen=True)
class BlurScoreSummary:
    """Window-level blur summary ready for detector-row export."""

    window_size: int
    rolling_scores: list[float]
    blur_score: float
    consecutive_blurry_windows: int
    required_windows: int

    @property
    def detected(self) -> bool:
        """Return whether the summarized window crosses the blur entry threshold."""
        return (
            self.blur_score >= config.VIDEO_BLUR_ALERT_THRESHOLD
            and self.consecutive_blurry_windows >= self.required_windows
        )


def _build_detector_row(
    *,
    analyzer: str,
    source_group: str,
    source_name: str,
    window_index: int | None,
    window_start_sec: float | None,
    window_duration_sec: float | None,
    start_time: float,
) -> DetectorRowBase:
    """Return the shared detector metadata carried by every result row."""
    return DetectorRowBase(
        analyzer=analyzer,
        source_type="video",
        source_group=source_group,
        source_name=source_name,
        window_index=window_index,
        window_start_sec=_round_optional_seconds(window_start_sec),
        window_duration_sec=_round_optional_seconds(window_duration_sec),
        timestamp_utc=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        processing_sec=round(time.time() - start_time, 3),
    )


def _warn_blur_sample_extraction_failure(file_path: Path) -> None:
    """Log one consistent warning for blur sample extraction failures."""
    logger.warning("ffmpeg failed to extract blur samples for %s", file_path.name)


def _default_blur_sample_size() -> tuple[int, int]:
    """Return the fallback blur-analysis bounds when probing cannot resolve size."""
    return (
        config.VIDEO_BLUR_SAMPLE_MAX_WIDTH,
        config.VIDEO_BLUR_SAMPLE_MAX_HEIGHT,
    )


def _display_source_labels(
    video_path: Path,
    *,
    source_group: str | None,
    source_name: str | None,
) -> tuple[str, str]:
    """Return stable detector-facing source labels for one media input."""
    resolved_source_name = source_name or video_path.name
    resolved_source_group = source_group or video_path.parent.name or video_path.name
    return (resolved_source_name, resolved_source_group)


def _round_optional_seconds(value: float | None) -> float | None:
    """Round optional second-valued payload fields to the detector precision."""
    return round(value, 3) if value is not None else None


def _extend_timed_media_input_args(
    cmd: list[str],
    *,
    file_path: Path,
    window_start_sec: float | None,
    window_duration_sec: float | None,
) -> None:
    """Append optional slice bounds and the input path to one ffmpeg command."""
    if window_start_sec is not None:
        cmd.extend(["-ss", f"{window_start_sec:.3f}"])
    cmd.extend(["-i", str(file_path.resolve())])
    if window_duration_sec is not None:
        cmd.extend(["-t", f"{window_duration_sec:.3f}"])


def analyze_video_metrics(
    file_path: Path,
    prefix: str | None = None,
    source_group: str | None = None,
    source_name: str | None = None,
    window_index: int | None = None,
    window_start_sec: float | None = None,
    window_duration_sec: float | None = None,
) -> AnalyzerResult | VideoMetricsRow:
    """Measure black-screen intervals for one local input or time slice.

    This is the production black-screen detector. It stays intentionally narrow:
    ffmpeg blackdetect in, typed runtime row out, with no alert policy mixed in.
    """
    _ = prefix
    video_path = Path(file_path)
    validate_local_media_size(video_path)
    start_time = time.time()

    display_source_name, display_source_group = _display_source_labels(
        video_path,
        source_group=source_group,
        source_name=source_name,
    )
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
    _extend_timed_media_input_args(
        cmd,
        file_path=video_path,
        window_start_sec=window_start_sec,
        window_duration_sec=window_duration_sec,
    )
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

    base_row = _build_detector_row(
        analyzer="video_metrics",
        source_group=display_source_group,
        source_name=display_source_name,
        window_index=window_index,
        window_start_sec=window_start_sec,
        window_duration_sec=window_duration_sec,
        start_time=start_time,
    )
    return VideoMetricsRow(
        **base_row.shared_fields(),
        duration_sec=round(duration_sec, 3),
        black_detected=bool(black_durations),
        black_segment_count=len(black_durations),
        total_black_sec=total_black_sec,
        longest_black_sec=longest_black_sec,
        black_ratio=black_ratio,
        picture_threshold_used=picture_threshold,
        pixel_threshold_used=pixel_threshold,
        min_duration_sec=min_duration,
    )


def analyze_video_blur(
    file_path: Path,
    prefix: str | None = None,
    source_group: str | None = None,
    source_name: str | None = None,
    window_index: int | None = None,
    window_start_sec: float | None = None,
    window_duration_sec: float | None = None,
) -> AnalyzerResult | VideoBlurRow:
    """Measure blur and motion for one local input or time slice.

    The detector samples a bounded grayscale view, extracts per-frame
    sharpness and frame-transition motion, converts sharpness into blur
    evidence, and collapses the window into one stable ``blur_score``.
    Alert policy remains outside this module.
    """
    _ = prefix
    video_path = Path(file_path)
    validate_local_media_size(video_path)
    start_time = time.time()
    threshold = config.VIDEO_BLUR_ALERT_THRESHOLD
    display_source_name, display_source_group = _display_source_labels(
        video_path,
        source_group=source_group,
        source_name=source_name,
    )

    sample_width, sample_height = _resolve_blur_sample_size(video_path)
    sample_fps = _resolve_blur_sample_fps(window_duration_sec)
    raw_frames = _extract_sampled_gray_frames(
        file_path=video_path,
        width=sample_width,
        height=sample_height,
        fps=sample_fps,
        max_samples=config.VIDEO_BLUR_MAX_SAMPLES,
        window_start_sec=window_start_sec,
        window_duration_sec=window_duration_sec,
    )
    raw_frames = _select_blur_analysis_frames(raw_frames)

    metrics = _measure_blur_window(
        width=sample_width,
        height=sample_height,
        raw_frames=raw_frames,
    )
    summary = _summarize_blur_scores(
        metrics.per_frame_blur_scores,
        threshold=threshold,
    )

    base_row = _build_detector_row(
        analyzer="video_blur",
        source_group=display_source_group,
        source_name=display_source_name,
        window_index=window_index,
        window_start_sec=window_start_sec,
        window_duration_sec=window_duration_sec,
        start_time=start_time,
    )
    return VideoBlurRow(
        **base_row.shared_fields(),
        sample_count=metrics.sample_count,
        sharpness_p10=round(metrics.sharpness_p10, 3),
        sharpness_p90=round(metrics.sharpness_p90, 3),
        motion_mean=round(metrics.motion_mean, 3),
        motion_p90=round(metrics.motion_p90, 3),
        blur_score=summary.blur_score,
        blur_detected=summary.detected,
        threshold_used=threshold,
        window_size=summary.window_size,
        consecutive_blurry_windows=summary.consecutive_blurry_windows,
    )


def _measure_blur_window(
    *,
    width: int,
    height: int,
    raw_frames: list[bytes],
) -> BlurWindowMetrics:
    """Collect reusable blur features from sampled grayscale frames.

    The returned metrics are detector-facing building blocks. They are reused
    by the production blur detector and by detector-lab experiments so the
    project compares policy ideas on top of the same base measurements.
    """
    frame_scores = [
        _frame_sharpness_score(width, height, pixels)
        for pixels in raw_frames
    ]
    motion_scores = _frame_transition_motion_scores(raw_frames)
    sharpness_p10 = _percentile(frame_scores, 10) if frame_scores else 0.0
    sharpness_p90 = _percentile(frame_scores, 90) if frame_scores else 0.0
    per_frame_blur_scores = [
        _combined_blur_score(score, sharpness_p10, sharpness_p90)
        for score in frame_scores
    ]
    return BlurWindowMetrics(
        frame_scores=frame_scores,
        motion_scores=motion_scores,
        sharpness_p10=sharpness_p10,
        sharpness_p90=sharpness_p90,
        per_frame_blur_scores=per_frame_blur_scores,
    )


def _select_blur_analysis_frames(raw_frames: list[bytes]) -> list[bytes]:
    """Drop sampled frames that belong to the black-screen failure lane.

    Production blur detection should not spend blur budget on frames that the
    black-screen lane already explains more accurately.
    """
    return [
        pixels
        for pixels in raw_frames
        if not _is_effectively_black_frame(pixels)
    ]


def _summarize_blur_scores(
    per_frame_blur_scores: list[float],
    *,
    threshold: float,
) -> BlurScoreSummary:
    """Collapse per-frame blur scores into one detector-facing window summary."""
    window_size = min(
        config.VIDEO_BLUR_WINDOW_SIZE,
        len(per_frame_blur_scores) if per_frame_blur_scores else 1,
    )
    rolling_scores = _rolling_window_medians(per_frame_blur_scores, window_size)
    consecutive_blurry_windows = _longest_threshold_run(rolling_scores, threshold)
    required_windows = min(
        config.VIDEO_BLUR_MIN_CONSECUTIVE_WINDOWS,
        len(rolling_scores) if rolling_scores else 1,
    )
    return BlurScoreSummary(
        window_size=window_size,
        rolling_scores=rolling_scores,
        blur_score=round(max(rolling_scores, default=0.0), 3),
        consecutive_blurry_windows=consecutive_blurry_windows,
        required_windows=required_windows,
    )


def _probe_video_duration(file_path: Path) -> float:
    """Return container duration in seconds, or ``0.0`` on probe failure."""
    data = _probe_ffprobe_json(
        file_path,
        show_entries="format=duration",
        failure_label=f"ffprobe duration probe on {file_path.name}",
    )
    if data is None:
        return 0.0
    try:
        return float(data.get("format", {}).get("duration", 0.0) or 0.0)
    except (TypeError, ValueError, AttributeError):
        logger.warning("ffprobe failed to read duration for %s", file_path.name)
        return 0.0


def _probe_ffprobe_json(
    file_path: Path,
    *,
    show_entries: str,
    failure_label: str,
    select_streams: str | None = None,
) -> dict[str, object] | None:
    """Return parsed ffprobe JSON output, or ``None`` when probing fails."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
    ]
    if select_streams is not None:
        cmd.extend(["-select_streams", select_streams])
    cmd.extend(
        [
            "-show_entries",
            show_entries,
            "-of",
            "json",
            str(file_path),
        ]
    )
    probe = _run_media_command(
        cmd,
        stdout=subprocess.PIPE,
        text=True,
        timeout=config.FFPROBE_TIMEOUT_SEC,
        failure_label=failure_label,
    )
    if probe is None:
        return None
    try:
        data = json.loads(probe.stdout)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return None


def _probe_video_dimensions(file_path: Path) -> tuple[int, int] | None:
    """Return the source frame size, or ``None`` when it cannot be resolved."""
    data = _probe_ffprobe_json(
        file_path,
        show_entries="stream=width,height",
        select_streams="v:0",
        failure_label=f"ffprobe dimension probe on {file_path.name}",
    )
    if data is None:
        return None
    try:
        stream = (data.get("streams") or [{}])[0]
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        if width < 2 or height < 2:
            return None
        return (width, height)
    except (OSError, ValueError, json.JSONDecodeError, TypeError, IndexError):
        logger.warning("ffprobe failed to read dimensions for %s", file_path.name)
        return None


def _resolve_blur_sample_size(file_path: Path) -> tuple[int, int]:
    """Choose a bounded, aspect-preserving blur sample size."""
    dimensions = _probe_video_dimensions(file_path)
    if dimensions is None:
        return _default_blur_sample_size()

    source_width, source_height = dimensions
    return _bounded_sample_size(
        source_width=source_width,
        source_height=source_height,
        max_width=config.VIDEO_BLUR_SAMPLE_MAX_WIDTH,
        max_height=config.VIDEO_BLUR_SAMPLE_MAX_HEIGHT,
    )


def _bounded_sample_size(
    *,
    source_width: int,
    source_height: int,
    max_width: int,
    max_height: int,
) -> tuple[int, int]:
    """Scale a source size into configured bounds without upscaling."""
    if source_width < 2 or source_height < 2:
        return (max_width, max_height)

    scale = min(
        max_width / source_width,
        max_height / source_height,
        1.0,
    )
    scaled_width = max(2, floor(source_width * scale))
    scaled_height = max(2, floor(source_height * scale))
    return (scaled_width, scaled_height)


def _resolve_blur_sample_fps(window_duration_sec: float | None) -> float:
    """Choose a blur sampling rate that preserves motion cues in short slices."""
    if window_duration_sec is None or window_duration_sec <= 0 or window_duration_sec > 1.0:
        return config.VIDEO_BLUR_SAMPLE_FPS

    minimum_fps_for_motion = (
        config.VIDEO_BLUR_MIN_MOTION_SAMPLES / window_duration_sec
    )
    return min(
        config.VIDEO_BLUR_MAX_MOTION_SAMPLE_FPS,
        max(config.VIDEO_BLUR_SAMPLE_FPS, minimum_fps_for_motion),
    )


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
    """Extract grayscale sample frames as raw bytes."""
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostats",
    ]
    _extend_timed_media_input_args(
        cmd,
        file_path=file_path,
        window_start_sec=window_start_sec,
        window_duration_sec=window_duration_sec,
    )
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
    if proc is None or proc.returncode != 0:
        _warn_blur_sample_extraction_failure(file_path)
        return []
    if not proc.stdout:
        if _is_short_tail_window_without_samples(window_duration_sec=window_duration_sec, fps=fps):
            return []
        _warn_blur_sample_extraction_failure(file_path)
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


def _is_short_tail_window_without_samples(
    *,
    window_duration_sec: float | None,
    fps: float,
) -> bool:
    """Return whether a short valid tail slice can legitimately yield zero frames."""
    if window_duration_sec is None or window_duration_sec <= 0 or fps <= 0:
        return False
    return window_duration_sec < (1.0 / fps)


def _run_media_command(
    cmd: list[str],
    *,
    timeout: float,
    failure_label: str,
    **kwargs,
):
    """Run one media command with timeout-aware error handling."""
    try:
        return subprocess.run(
            cmd,
            check=False,
            shell=False,
            timeout=timeout,
            **kwargs,
        )  # nosec B603
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


def _frame_transition_motion_scores(frames: list[bytes]) -> list[float]:
    """Return normalized frame-to-frame motion estimates for sampled frames."""
    if not frames:
        return []

    motion_scores = [0.0]
    for previous, current in zip(frames, frames[1:], strict=False):
        motion_scores.append(_frame_difference_mean(previous, current))
    return motion_scores


def _is_effectively_black_frame(pixels: bytes) -> bool:
    """Return whether a grayscale frame should be excluded from blur scoring."""
    if not pixels:
        return False

    dark_threshold = int(config.VIDEO_BLACK_PIXEL_THRESHOLD * 255.0)
    dark_pixels = sum(1 for pixel in pixels if pixel <= dark_threshold)
    dark_ratio = dark_pixels / len(pixels)
    return dark_ratio >= config.VIDEO_BLACK_PICTURE_THRESHOLD


def _frame_difference_mean(previous: bytes, current: bytes) -> float:
    """Return the normalized mean absolute pixel delta for one frame pair."""
    if not previous or not current or len(previous) != len(current):
        return 0.0

    absolute_difference_sum = sum(
        abs(current_pixel - previous_pixel)
        for previous_pixel, current_pixel in zip(previous, current, strict=False)
    )
    mean_difference = absolute_difference_sum / len(previous)
    return round(mean_difference / 255.0, 6)


def _combined_blur_score(score: float, p10: float, p90: float) -> float:
    """Blend absolute and clip-relative blur into one ``0..1`` score."""
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
    """Normalize a sharpness value into ``0..1`` using robust percentiles."""
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


def _mean(values: list[float]) -> float:
    """Return the arithmetic mean for one numeric series."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _clamp(value: float) -> float:
    """Clamp one floating-point value into the ``0..1`` interval."""
    return max(0.0, min(1.0, value))
