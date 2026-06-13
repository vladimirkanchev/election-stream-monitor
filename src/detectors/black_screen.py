"""Production black-screen detector for local files and time slices."""

import re
import subprocess  # nosec B404
import time
from pathlib import Path

import config
from analyzer_contract import DetectorResult, VideoMetricsRow
from source_validation import validate_local_media_size

from ._shared import (
    build_detector_row,
    display_source_labels,
    extend_timed_media_input_args,
    probe_ffprobe_json,
    run_media_command,
)


def analyze_video_metrics(
    file_path: Path,
    prefix: str | None = None,
    source_group: str | None = None,
    source_name: str | None = None,
    window_index: int | None = None,
    window_start_sec: float | None = None,
    window_duration_sec: float | None = None,
) -> DetectorResult:
    """Measure black-screen intervals for one local input or time slice."""
    _ = prefix
    video_path = Path(file_path)
    validate_local_media_size(video_path)
    start_time = time.time()

    display_source_name, display_source_group = display_source_labels(
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
    extend_timed_media_input_args(
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
    proc = run_media_command(
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

    base_row = build_detector_row(
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


def _probe_video_duration(file_path: Path) -> float:
    """Return container duration in seconds, or ``0.0`` on probe failure."""
    data = probe_ffprobe_json(
        file_path,
        show_entries="format=duration",
        failure_label=f"ffprobe duration probe on {file_path.name}",
    )
    if data is None:
        return 0.0
    try:
        return float(data.get("format", {}).get("duration", 0.0) or 0.0)
    except (TypeError, ValueError, AttributeError):
        from logger import logger

        logger.warning("ffprobe failed to read duration for %s", file_path.name)
        return 0.0


def _parse_blackdetect_durations(stderr_output: str) -> list[float]:
    """Extract black interval durations from ffmpeg ``blackdetect`` output."""
    pattern = re.compile(
        r"black_start:(?P<start>[\d\.]+)\s+black_end:(?P<end>[\d\.]+)\s"
        r"+black_duration:(?P<dur>[\d\.]+)"
    )
    durations: list[float] = []
    for match in pattern.finditer(stderr_output):
        try:
            durations.append(float(match.group("dur")))
        except (TypeError, ValueError):
            continue
    return durations
