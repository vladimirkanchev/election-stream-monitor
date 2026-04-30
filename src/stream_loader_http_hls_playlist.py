"""Pure playlist helpers for the concrete HTTP/HLS api_stream loader.

Keep this module focused on interpreting playlist text and deriving
playlist-driven helper values. It should stay free of loader shell state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlparse

from stream_loader_contracts import ApiStreamMediaPlaylistSnapshot, ApiStreamPlaylistSegment


def _detect_hls_playlist_kind(playlist_text: str) -> Literal["master", "media", "unknown"]:
    if "#EXTM3U" not in playlist_text:
        return "unknown"
    if "#EXT-X-STREAM-INF" in playlist_text:
        return "master"
    if "#EXTINF" in playlist_text or "#EXT-X-TARGETDURATION" in playlist_text:
        return "media"
    return "unknown"


def _parse_master_playlist_variants(playlist_text: str, base_url: str) -> list[str]:
    variants: list[str] = []
    expect_uri = False
    for raw_line in playlist_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-STREAM-INF"):
            expect_uri = True
            continue
        if line.startswith("#"):
            continue
        if expect_uri:
            variants.append(urljoin(base_url, line))
            expect_uri = False
    return variants


def _parse_media_playlist(
    playlist_text: str,
    base_url: str,
) -> ApiStreamMediaPlaylistSnapshot:
    if "#EXTM3U" not in playlist_text:
        raise ValueError("api_stream media playlist is missing EXTM3U header")

    media_sequence = 0
    target_duration_sec: float | None = None
    current_duration: float | None = None
    next_sequence_offset = 0
    is_endlist = False
    segments: list[ApiStreamPlaylistSegment] = []

    for raw_line in playlist_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            value = line.split(":", 1)[1].strip()
            try:
                media_sequence = int(value or 0)
            except ValueError as error:
                raise ValueError("api_stream media playlist has invalid MEDIA-SEQUENCE") from error
            next_sequence_offset = 0
            continue
        if line.startswith("#EXT-X-TARGETDURATION:"):
            value = line.split(":", 1)[1].strip()
            try:
                target_duration_sec = float(value or 0.0)
            except ValueError as error:
                raise ValueError("api_stream media playlist has invalid TARGETDURATION") from error
            continue
        if line.startswith("#EXTINF:"):
            value = line.split(":", 1)[1].split(",", 1)[0].strip()
            try:
                current_duration = float(value or 0.0)
            except ValueError as error:
                raise ValueError("api_stream media playlist has invalid EXTINF duration") from error
            continue
        if line == "#EXT-X-ENDLIST":
            is_endlist = True
            continue
        if line.startswith("#"):
            continue

        duration_sec = current_duration if current_duration is not None else 1.0
        segments.append(
            ApiStreamPlaylistSegment(
                sequence=media_sequence + next_sequence_offset,
                uri=urljoin(base_url, line),
                duration_sec=max(duration_sec, 0.1),
            )
        )
        next_sequence_offset += 1
        current_duration = None

    return ApiStreamMediaPlaylistSnapshot(
        segments=segments,
        is_endlist=is_endlist,
        target_duration_sec=target_duration_sec if target_duration_sec and target_duration_sec > 0 else None,
    )


def _build_playlist_segment_key(segment: ApiStreamPlaylistSegment) -> tuple[int, str]:
    return (segment.sequence, Path(urlparse(segment.uri).path).name)


def _derive_api_stream_poll_interval(
    *,
    configured_poll_interval_sec: float,
    target_duration_sec: float | None,
) -> float:
    """Return the next playlist-poll delay while tolerating target-duration drift."""
    configured = max(configured_poll_interval_sec, 0.0)
    if target_duration_sec is None:
        return configured
    safe_target_duration = max(target_duration_sec, 0.1)
    return min(configured, safe_target_duration)
