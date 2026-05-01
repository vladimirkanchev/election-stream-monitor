"""Input discovery and slice-expansion helpers for `session_runner`.

This module owns the local-input side of session preparation so the main runner
can stay focused on orchestration. It is responsible for:

- resolving validated local files for each supported local mode
- honoring playlist order for `video_segments`
- expanding `video_files` into the current one-second analysis windows

It does not own session lifecycle transitions or persistence.
"""

from __future__ import annotations

import json
import subprocess  # nosec B404
from pathlib import Path

from analyzer_contract import AnalysisSlice, InputMode
import config
from logger import get_logger
from source_validation import (
    ensure_path_within_root,
    resolve_validated_local_input_path,
    validate_local_media_size,
)


logger = get_logger(__name__)


def discover_input_files(
    mode: InputMode,
    input_path: str | Path,
    *,
    supported_patterns: dict[InputMode, tuple[str, ...]],
) -> list[Path]:
    """Resolve one source into concrete processable files for the chosen mode."""
    source = resolve_validated_local_input_path(mode, input_path)

    if mode == "video_segments":
        playlist_order = discover_segment_files_from_playlist(source)
        if playlist_order:
            for segment_path in playlist_order:
                validate_local_media_size(segment_path)
            return playlist_order
        if source.is_file() and source.suffix.lower() == ".m3u8":
            return []

    patterns = supported_patterns[mode]
    if source.is_file():
        validate_local_media_size(source)
        return [source]

    discovered = sorted(
        [candidate for pattern in patterns for candidate in source.glob(pattern)],
        key=lambda item: item.stat().st_mtime,
    )
    for candidate in discovered:
        validate_local_media_size(candidate)
    return discovered


def discover_input_slices(
    mode: InputMode,
    input_path: str | Path,
    *,
    supported_patterns: dict[InputMode, tuple[str, ...]],
    duration_probe,
    api_stream_slice_discoverer,
    session_id: str | None = None,
) -> list[AnalysisSlice]:
    """Expand one validated source into analysis slices for the runner."""
    if mode == "api_stream":
        return api_stream_slice_discoverer(input_path, session_id=session_id)

    input_files = discover_input_files(
        mode,
        input_path,
        supported_patterns=supported_patterns,
    )
    if mode != "video_files":
        return [
            AnalysisSlice(
                file_path=file_path,
                source_group=file_path.parent.name or file_path.name,
                source_name=file_path.name,
                window_index=index,
            )
            for index, file_path in enumerate(input_files)
        ]

    return _build_video_file_slices(input_files, duration_probe=duration_probe)


def discover_segment_files_from_playlist(source: Path) -> list[Path]:
    """Return playlist-ordered `.ts` paths when an HLS playlist exists."""
    playlist_path: Path | None = None

    if source.is_file() and source.suffix.lower() == ".m3u8":
        playlist_path = source
    elif source.is_dir():
        index_playlist = source / "index.m3u8"
        if index_playlist.exists():
            playlist_path = index_playlist

    if playlist_path is None or not playlist_path.exists():
        return []

    segment_paths: list[Path] = []
    for line in playlist_path.read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        segment_path = ensure_path_within_root(
            playlist_path.parent,
            playlist_path.parent / entry,
        )
        if segment_path and segment_path.exists() and segment_path.suffix.lower() == ".ts":
            segment_paths.append(segment_path)

    return segment_paths


def probe_video_duration(file_path: Path) -> float:
    """Return container duration in seconds or ``0.0`` if probing fails."""
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
    try:
        probe = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            text=True,
            check=False,
            shell=False,
            timeout=config.FFPROBE_TIMEOUT_SEC,
        )  # nosec B603
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe timed out while probing %s", file_path.name)
        return 0.0
    try:
        data = json.loads(probe.stdout)
        return float(data.get("format", {}).get("duration", 0.0) or 0.0)
    except (OSError, ValueError, json.JSONDecodeError):
        return 0.0


def format_mm_ss(total_seconds: float) -> str:
    """Return a short `MM:SS` label for a slice start time."""
    safe_seconds = max(0, int(total_seconds))
    minutes = safe_seconds // 60
    seconds = safe_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def _build_video_file_slices(
    input_files: list[Path],
    *,
    duration_probe,
) -> list[AnalysisSlice]:
    """Expand `.mp4` inputs into roughly one-second temporal slices."""
    slices: list[AnalysisSlice] = []
    for file_path in input_files:
        duration_sec = duration_probe(file_path)
        if duration_sec > config.LOCAL_VIDEO_MAX_DURATION_SEC:
            raise ValueError(
                f"Input video exceeds duration limit for local analysis: {file_path.name}"
            )
        if duration_sec <= 0:
            slices.append(
                AnalysisSlice(
                    file_path=file_path,
                    source_group=file_path.name,
                    source_name=f"{file_path.name} @ 00:00",
                    window_index=0,
                    window_start_sec=0.0,
                    window_duration_sec=1.0,
                )
            )
            continue

        full_windows = int(duration_sec)
        remainder = duration_sec - full_windows
        total_windows = full_windows + (1 if remainder > 1e-9 else 0)
        for window_index in range(total_windows):
            window_start_sec = float(window_index)
            window_duration_sec = min(1.0, max(0.1, duration_sec - window_start_sec))
            slices.append(
                AnalysisSlice(
                    file_path=file_path,
                    source_group=file_path.name,
                    source_name=f"{file_path.name} @ {format_mm_ss(window_start_sec)}",
                    window_index=window_index,
                    window_start_sec=window_start_sec,
                    window_duration_sec=round(window_duration_sec, 3),
                )
            )

    return slices
