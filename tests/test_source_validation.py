"""Tests for centralized source trust-boundary validation.

This suite documents the current source policy before full `api_stream`
implementation exists:

- only explicitly allowed remote schemes are accepted
- local modes reject URL-like inputs
- obvious local-network targets are rejected by default for remote sources
- local path joins must stay inside the declared input root
"""

from pathlib import Path

import pytest

from source_validation import (
    ensure_path_within_root,
    validate_api_stream_url,
    validate_source_input,
)


def test_validate_api_stream_url_accepts_http_and_https() -> None:
    """`api_stream` validation should explicitly allow the currently supported schemes."""
    assert validate_api_stream_url("https://example.com/live/playlist.m3u8") == (
        "https://example.com/live/playlist.m3u8"
    )
    assert validate_api_stream_url("http://streams.example.com/live.m3u8") == (
        "http://streams.example.com/live.m3u8"
    )
    assert validate_api_stream_url("https://example.com/archive/recording.mp4") == (
        "https://example.com/archive/recording.mp4"
    )


def test_validate_api_stream_url_rejects_unsupported_schemes() -> None:
    """Unsupported remote schemes should be rejected before any later fetch logic exists."""
    with pytest.raises(ValueError, match="Unsupported api_stream URL scheme"):
        validate_api_stream_url("file:///tmp/playlist.m3u8")
    with pytest.raises(ValueError, match="Unsupported api_stream URL scheme"):
        validate_api_stream_url("data:text/plain;base64,SGVsbG8=")


def test_validate_api_stream_url_requires_direct_media_path() -> None:
    """Page-wrapper URLs should be rejected before playback or loader fetches begin."""
    with pytest.raises(ValueError, match="direct \\.m3u8 or \\.mp4 URL"):
        validate_api_stream_url("https://video-platform.example/live/channel")
    with pytest.raises(ValueError, match="direct \\.m3u8 or \\.mp4 URL"):
        validate_api_stream_url("https://portal.example/player.html")


def test_validate_api_stream_url_accepts_direct_media_suffixes_case_insensitively() -> None:
    """Direct media URLs should remain valid even when providers use uppercase suffixes."""
    assert validate_api_stream_url("https://example.com/live/PLAYLIST.M3U8") == (
        "https://example.com/live/PLAYLIST.M3U8"
    )
    assert validate_api_stream_url("https://example.com/archive/RECORDING.MP4") == (
        "https://example.com/archive/RECORDING.MP4"
    )


def test_validate_source_input_rejects_url_like_values_for_local_modes() -> None:
    """Local source modes should reject URL-like strings instead of treating them as paths."""
    with pytest.raises(ValueError, match="Unsupported local input scheme"):
        validate_source_input("video_files", "ftp://example.com/video.mp4")
    with pytest.raises(ValueError, match="Unsupported local input scheme"):
        validate_source_input("video_files", "javascript:alert(1)")


def test_validate_api_stream_url_rejects_private_network_targets_by_default() -> None:
    """Local mode should reject obvious internal-network probing targets by default."""
    with pytest.raises(ValueError, match="not allowed in local mode"):
        validate_api_stream_url("http://localhost:8080/live.m3u8")

    with pytest.raises(ValueError, match="not allowed in local mode"):
        validate_api_stream_url("http://127.0.0.1/live.m3u8")


def test_validate_api_stream_url_requires_explicit_allowlist_in_service_mode(
    monkeypatch,
) -> None:
    """Service mode should require an explicit public-host allowlist before remote fetching is allowed."""
    monkeypatch.setattr("config.API_STREAM_TRUST_MODE", "service")
    monkeypatch.setattr("config.API_STREAM_SERVICE_ALLOWED_HOSTS", ())

    with pytest.raises(ValueError, match="service mode requires an explicit allowed host list"):
        validate_api_stream_url("https://streams.example.com/live.m3u8")


def test_validate_api_stream_url_enforces_service_mode_allowlist_and_private_host_policy(
    monkeypatch,
) -> None:
    """Service mode should restrict remote fetching to explicitly allowed public hosts."""
    monkeypatch.setattr("config.API_STREAM_TRUST_MODE", "service")
    monkeypatch.setattr("config.API_STREAM_SERVICE_ALLOWED_HOSTS", ("streams.example.com",))
    monkeypatch.setattr("config.API_STREAM_SERVICE_ALLOW_PRIVATE_HOSTS", False)

    assert validate_api_stream_url("https://streams.example.com/live.m3u8") == (
        "https://streams.example.com/live.m3u8"
    )

    with pytest.raises(ValueError, match="allowed host list"):
        validate_api_stream_url("https://other.example.com/live.m3u8")

    with pytest.raises(ValueError, match="not allowed in service mode"):
        validate_api_stream_url("http://localhost/live.m3u8")


def test_validate_api_stream_url_requires_allowed_host_when_allowlist_is_configured(
    monkeypatch,
) -> None:
    """Optional allowlists should narrow accepted remote hosts before runtime fetching exists."""
    monkeypatch.setattr("config.API_STREAM_ALLOWED_HOSTS", ("streams.example.com",))

    assert validate_api_stream_url("https://streams.example.com/live.m3u8") == (
        "https://streams.example.com/live.m3u8"
    )

    with pytest.raises(ValueError, match="allowed host list"):
        validate_api_stream_url("https://other.example.com/live.m3u8")


def test_ensure_path_within_root_rejects_traversal(tmp_path: Path) -> None:
    """Joined local item paths should stay under the declared root."""
    root = tmp_path / "segments"
    root.mkdir()
    outside = tmp_path / "outside.ts"
    outside.write_bytes(b"video")

    assert ensure_path_within_root(root, root / "../outside.ts") is None
