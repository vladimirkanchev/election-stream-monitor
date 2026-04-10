"""Tests for local playback source resolution."""

from pathlib import Path

import config
import pytest
from playback_sources import resolve_playback_source


def test_video_file_source_returns_absolute_path(tmp_path: Path) -> None:
    """Whole video files should resolve directly to their absolute path."""
    video_file = tmp_path / "sample.mp4"
    video_file.write_bytes(b"video")

    resolved = resolve_playback_source("video_files", video_file)

    assert resolved == str(video_file.resolve())


def test_video_file_source_from_folder_returns_first_mp4(tmp_path: Path) -> None:
    """A folder input should resolve to the first available mp4 file."""
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    first = video_dir / "a_sample.mp4"
    second = video_dir / "b_sample.mp4"
    first.write_bytes(b"video-a")
    second.write_bytes(b"video-b")

    resolved = resolve_playback_source("video_files", video_dir)

    assert resolved == str(first.resolve())


def test_video_segment_source_creates_cached_preview(
    monkeypatch, tmp_path: Path
) -> None:
    """Segment playback should resolve through the local HLS playlist."""
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)

    segment_dir = tmp_path / "segments"
    segment_dir.mkdir()
    (segment_dir / "segment_0001.ts").write_bytes(b"segment")
    (segment_dir / "index.m3u8").write_text("#EXTM3U\nsegment_0001.ts\n", encoding="utf-8")

    resolved = resolve_playback_source(
        "video_segments",
        segment_dir,
        current_item="segment_0001.ts",
    )

    assert resolved is not None
    assert resolved.endswith("index.m3u8")


def test_api_stream_source_returns_remote_url_verbatim() -> None:
    """Remote api_stream playback should pass through the original URL."""
    url = "https://example.com/live/playlist.m3u8"

    resolved = resolve_playback_source("api_stream", url)

    assert resolved == url


def test_api_stream_source_returns_none_for_blank_url() -> None:
    """Blank remote api_stream inputs should resolve to no playback source."""
    with pytest.raises(ValueError, match="Source input cannot be blank"):
        resolve_playback_source("api_stream", "   ")


def test_api_stream_source_rejects_unsupported_url_scheme() -> None:
    """Only explicit http/https api_stream URLs should be accepted."""
    with pytest.raises(ValueError, match="Unsupported api_stream URL scheme"):
        resolve_playback_source("api_stream", "file:///tmp/playlist.m3u8")


def test_video_file_source_rejects_current_item_path_traversal(tmp_path: Path) -> None:
    """Playback resolution should not allow current-item traversal outside the input root."""
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"video")

    resolved = resolve_playback_source(
        "video_files",
        video_dir,
        current_item="../outside.mp4",
    )

    assert resolved is None


def test_video_segment_source_rejects_playlist_entry_path_traversal(tmp_path: Path) -> None:
    """Segment playback should ignore playlist entries that try to escape the input root."""
    segment_dir = tmp_path / "segments"
    segment_dir.mkdir()
    outside = tmp_path / "outside.ts"
    outside.write_bytes(b"segment")
    (segment_dir / "index.m3u8").write_text(
        "#EXTM3U\n#EXTINF:1.0,\n../outside.ts\n",
        encoding="utf-8",
    )

    resolved = resolve_playback_source(
        "video_segments",
        segment_dir,
        current_item="../outside.ts",
    )

    assert resolved is not None
    assert resolved.endswith("index.m3u8")
