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


@pytest.mark.parametrize(
    "candidate_url",
    [
        "http://localhost:8080/live.m3u8",
        "http://127.0.0.1/live.m3u8",
        "http://[::1]/live.m3u8",
        "http://169.254.169.254/latest/meta-data.m3u8",
    ],
)
def test_validate_api_stream_url_rejects_local_network_targets_by_default(
    candidate_url: str,
) -> None:
    """Local mode should reject obvious internal-network probing targets by default."""
    with pytest.raises(ValueError, match="not allowed in local mode"):
        validate_api_stream_url(candidate_url)


def test_validate_api_stream_url_rejects_embedded_credentials() -> None:
    """Remote URLs should fail closed when credentials are embedded in the authority."""
    with pytest.raises(ValueError, match="must not include credentials"):
        validate_api_stream_url("https://operator:secret@streams.example.com/live.m3u8")


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


def test_validate_api_stream_url_rejects_suffix_confusion_hosts_when_allowlisted(
    monkeypatch,
) -> None:
    """Allowlists should accept exact hosts and real subdomains, not lookalike suffix hosts."""
    monkeypatch.setattr("config.API_STREAM_ALLOWED_HOSTS", ("streams.example.com",))

    assert validate_api_stream_url("https://edge.streams.example.com/live.m3u8") == (
        "https://edge.streams.example.com/live.m3u8"
    )

    with pytest.raises(ValueError, match="allowed host list"):
        validate_api_stream_url("https://streams.example.com.evil.test/live.m3u8")


@pytest.mark.parametrize(
    "resolved_ips",
    [
        {"127.0.0.1"},
        {"10.20.30.40"},
        {"93.184.216.34", "172.16.0.12"},
    ],
)
def test_validate_api_stream_url_rejects_local_network_dns_resolutions_when_dns_checks_are_enabled(
    monkeypatch,
    resolved_ips: set[str],
) -> None:
    monkeypatch.setattr("config.API_STREAM_VALIDATE_DNS_HOSTS", True)
    monkeypatch.setattr(
        "source_validation._resolve_api_stream_host_ips",
        lambda hostname: resolved_ips,
    )

    with pytest.raises(ValueError, match="resolves to a local-network target"):
        validate_api_stream_url("https://streams.example.com/live.m3u8")


def test_validate_api_stream_url_accepts_hosts_that_resolve_to_public_ips_when_dns_checks_are_enabled(
    monkeypatch,
) -> None:
    monkeypatch.setattr("config.API_STREAM_VALIDATE_DNS_HOSTS", True)
    monkeypatch.setattr(
        "source_validation._resolve_api_stream_host_ips",
        lambda hostname: {"93.184.216.34"},
    )

    assert validate_api_stream_url("https://streams.example.com/live.m3u8") == (
        "https://streams.example.com/live.m3u8"
    )


def test_ensure_path_within_root_rejects_traversal(tmp_path: Path) -> None:
    """Joined local item paths should stay under the declared root."""
    root = tmp_path / "segments"
    root.mkdir()
    outside = tmp_path / "outside.ts"
    outside.write_bytes(b"video")

    assert ensure_path_within_root(root, root / "../outside.ts") is None


def test_ensure_path_within_root_rejects_symlink_escape(tmp_path: Path) -> None:
    """Symlinked paths should be rejected when they resolve outside the allowed root."""
    root = tmp_path / "segments"
    root.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    escaped_segment = outside_dir / "segment_0001.ts"
    escaped_segment.write_bytes(b"video")
    symlinked_dir = root / "nested"
    symlinked_dir.symlink_to(outside_dir, target_is_directory=True)

    assert ensure_path_within_root(root, symlinked_dir / "segment_0001.ts") is None


def test_ensure_path_within_root_rejects_symlinked_file_escape(tmp_path: Path) -> None:
    """Symlinked files should not be accepted when they resolve outside the allowed root."""
    root = tmp_path / "segments"
    root.mkdir()
    outside_file = tmp_path / "outside.ts"
    outside_file.write_bytes(b"video")
    escaped_file = root / "segment_0001.ts"
    escaped_file.symlink_to(outside_file)

    assert ensure_path_within_root(root, escaped_file) is None


def test_ensure_path_within_root_accepts_normalized_nested_paths_inside_root(
    tmp_path: Path,
) -> None:
    """Repeated separators and `..` segments should still resolve when they stay inside the root."""
    root = tmp_path / "segments"
    nested_dir = root / "nested"
    nested_dir.mkdir(parents=True)
    segment = root / "segment_0001.ts"
    segment.write_bytes(b"video")

    candidate = nested_dir / ".." / "segment_0001.ts"

    assert ensure_path_within_root(root, candidate) == segment.resolve()


def test_ensure_path_within_root_rejects_mixed_parent_segments_that_escape_root(
    tmp_path: Path,
) -> None:
    """Mixed nested paths should still fail closed when normalization escapes the declared root."""
    root = tmp_path / "segments"
    nested_dir = root / "nested"
    nested_dir.mkdir(parents=True)
    outside_file = tmp_path / "outside.ts"
    outside_file.write_bytes(b"video")

    candidate = nested_dir / ".." / ".." / "outside.ts"

    assert ensure_path_within_root(root, candidate) is None
