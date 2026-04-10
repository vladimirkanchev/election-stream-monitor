"""Helpers for resolving playable local media sources for the frontend."""

from __future__ import annotations

from pathlib import Path

from analyzer_contract import InputMode
from source_validation import (
    ensure_path_within_root,
    resolve_validated_local_input_path,
    validate_api_stream_url,
)


def resolve_playback_source(
    mode: InputMode,
    input_path: str | Path,
    current_item: str | None = None,
) -> str | None:
    """Return a playable local source path or remote URL for the frontend.

    For local `.ts` segments this function prefers the local ``index.m3u8``
    playlist so the frontend can play the sequence as HLS.

    `api_stream` playback is intentionally kept separate from live monitoring
    ingestion. The backend validates the remote URL and returns it unchanged for
    playback, while stream loading and chunk iteration stay in the dedicated
    `stream_loader` seam.
    """
    if mode == "api_stream":
        return validate_api_stream_url(input_path)

    base_path = resolve_validated_local_input_path(mode, input_path)

    if mode == "video_files":
        video_path = _resolve_local_item(base_path, current_item)
        return str(video_path.resolve()) if video_path and video_path.exists() else None

    if mode == "video_segments":
        playlist_path = _resolve_segment_playlist(base_path)
        if playlist_path is not None and playlist_path.exists():
            return str(playlist_path.resolve())

        segment_path = _resolve_local_item(base_path, current_item)
        return str(segment_path.resolve()) if segment_path and segment_path.exists() else None

    return None


def _resolve_local_item(base_path: Path, current_item: str | None) -> Path | None:
    """Resolve a file path from a base path plus optional current item."""
    if base_path.is_file():
        return base_path
    if current_item is None and base_path.is_dir():
        if any(base_path.glob("*.mp4")):
            return next(iter(sorted(base_path.glob("*.mp4"))))
        return None
    if current_item is None:
        return None
    safe_candidate = ensure_path_within_root(base_path, base_path / current_item)
    return safe_candidate


def _resolve_segment_playlist(base_path: Path) -> Path | None:
    """Return the local playlist for a segment directory when present."""
    if base_path.is_file() and base_path.suffix.lower() == ".m3u8":
        return base_path

    directory = base_path if base_path.is_dir() else base_path.parent
    index_playlist = directory / "index.m3u8"
    if index_playlist.exists():
        return index_playlist

    return next(iter(sorted(directory.glob("*.m3u8"))), None)
