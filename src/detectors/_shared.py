"""Shared row-building and ffmpeg/ffprobe helpers for production detectors."""

import json
import subprocess  # nosec B404
import time
from pathlib import Path

import config
from analyzer_contract import DetectorRowBase
from logger import logger


def build_detector_row(
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
        window_start_sec=round_optional_seconds(window_start_sec),
        window_duration_sec=round_optional_seconds(window_duration_sec),
        timestamp_utc=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        processing_sec=round(time.time() - start_time, 3),
    )


def display_source_labels(
    video_path: Path,
    *,
    source_group: str | None,
    source_name: str | None,
) -> tuple[str, str]:
    """Return stable detector-facing source labels for one media input."""
    resolved_source_name = source_name or video_path.name
    resolved_source_group = source_group or video_path.parent.name or video_path.name
    return (resolved_source_name, resolved_source_group)


def round_optional_seconds(value: float | None) -> float | None:
    """Round optional second-valued payload fields to the detector precision."""
    return round(value, 3) if value is not None else None


def extend_timed_media_input_args(
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


def probe_ffprobe_json(
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
    probe = run_media_command(
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


def run_media_command(
    cmd: list[str],
    *,
    timeout: float,
    failure_label: str,
    **kwargs,
):
    """Run one ffmpeg or ffprobe command and fail closed on tool errors."""
    try:
        return subprocess.run(  # nosec B603
            cmd,
            check=False,
            shell=False,
            timeout=timeout,
            **kwargs,
        )
    except subprocess.TimeoutExpired:
        logger.warning("%s timed out after %.1f sec", failure_label, timeout)
        return None
    except OSError:
        logger.warning("%s could not start", failure_label)
        return None
