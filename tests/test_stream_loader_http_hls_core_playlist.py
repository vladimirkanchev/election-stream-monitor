"""Tests for core HTTP/HLS playlist and variant-resolution behavior.

These cases cover the ordinary resolution path from one entry playlist to the
media playlist and accepted segments, without mixing in live refresh loops or
provider retry noise.
"""

from pathlib import Path

import pytest

from stream_loader import (
    HttpHlsApiStreamLoader,
    collect_api_stream_slices,
)
from tests.http_hls_test_support import (
    _HLS_CONTENT_TYPE,
    _TS_CONTENT_TYPE,
    assert_slice_identity,
    build_http_hls_source,
    cleanup_http_hls_session,
    collect_http_hls_slices,
    configure_http_hls_loader_test,
    media_playlist,
    playlist,
)
from tests.local_hls_test_support import _serve_local_hls


def test_http_hls_loader_collects_media_playlist_segments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The concrete loader should fetch a media playlist and materialize segment slices."""
    configure_http_hls_loader_test(monkeypatch, tmp_path)

    playlist_text = media_playlist(0, "segment_000.ts", "segment_001.ts")
    routes = {
        "/live/index.m3u8": (200, playlist_text, _HLS_CONTENT_TYPE),
        "/live/segment_000.ts": (200, b"ts-000", _TS_CONTENT_TYPE),
        "/live/segment_001.ts": (200, b"ts-001", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        slices = collect_http_hls_slices(base_url, "/live/index.m3u8", "session-http-media")

    assert_slice_identity(
        slices,
        source_names=["segment_000.ts", "segment_001.ts"],
        window_indexes=[0, 1],
    )
    assert all(slice_.file_path.exists() for slice_ in slices)
    cleanup_http_hls_session("session-http-media")


def test_http_hls_loader_selects_first_master_playlist_variant(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The first real loader should apply the explicit first-variant master-playlist policy."""
    configure_http_hls_loader_test(monkeypatch, tmp_path)

    master_text = playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360',
        "low/index.m3u8",
        '#EXT-X-STREAM-INF:BANDWIDTH=1200000,RESOLUTION=1280x720',
        "high/index.m3u8",
    )
    media_text = media_playlist(10, "segment_low_010.ts")
    routes = {
        "/master.m3u8": (200, master_text, _HLS_CONTENT_TYPE),
        "/low/index.m3u8": (200, media_text, _HLS_CONTENT_TYPE),
        "/high/index.m3u8": (
            200,
            media_text.replace("segment_low_010.ts", "segment_high_010.ts"),
            _HLS_CONTENT_TYPE,
        ),
        "/low/segment_low_010.ts": (200, b"low", _TS_CONTENT_TYPE),
        "/high/segment_high_010.ts": (200, b"high", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        slices = collect_http_hls_slices(base_url, "/master.m3u8", "session-http-master")

    assert_slice_identity(
        slices,
        source_names=["segment_low_010.ts"],
        window_indexes=[10],
    )
    cleanup_http_hls_session("session-http-master")


def test_http_hls_loader_uses_first_master_variant_even_when_it_is_weak_but_playable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """First-variant selection should remain predictable even for a low-quality playable stream."""
    configure_http_hls_loader_test(monkeypatch, tmp_path)

    master_text = playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=180000,RESOLUTION=320x180',
        "weak/index.m3u8",
        '#EXT-X-STREAM-INF:BANDWIDTH=2400000,RESOLUTION=1920x1080',
        "strong/index.m3u8",
    )
    weak_media = playlist(
        "#EXT-X-TARGETDURATION:2",
        "#EXT-X-MEDIA-SEQUENCE:20",
        "#EXTINF:2.0,",
        "segment_weak_020.ts",
        "#EXT-X-ENDLIST",
    )
    strong_media = weak_media.replace("segment_weak_020.ts", "segment_strong_020.ts")
    routes = {
        "/master.m3u8": (200, master_text, _HLS_CONTENT_TYPE),
        "/weak/index.m3u8": (200, weak_media, _HLS_CONTENT_TYPE),
        "/strong/index.m3u8": (200, strong_media, _HLS_CONTENT_TYPE),
        "/weak/segment_weak_020.ts": (200, b"weak", _TS_CONTENT_TYPE),
        "/strong/segment_strong_020.ts": (200, b"strong", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        slices = collect_http_hls_slices(
            base_url,
            "/master.m3u8",
            "session-http-master-weak-first",
        )

    assert_slice_identity(slices, source_names=["segment_weak_020.ts"])
    cleanup_http_hls_session("session-http-master-weak-first")


def test_http_hls_loader_resolves_nested_master_playlist_variants(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Nested master playlists should still resolve to a reachable media playlist."""
    configure_http_hls_loader_test(monkeypatch, tmp_path)

    outer_master = playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360',
        "variant/master.m3u8",
    )
    inner_master = playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=750000,RESOLUTION=960x540',
        "media/index.m3u8",
    )
    resolved_media_playlist = media_playlist(12, "segment_012.ts")
    routes = {
        "/master.m3u8": (200, outer_master, _HLS_CONTENT_TYPE),
        "/variant/master.m3u8": (200, inner_master, _HLS_CONTENT_TYPE),
        "/variant/media/index.m3u8": (200, resolved_media_playlist, _HLS_CONTENT_TYPE),
        "/variant/media/segment_012.ts": (200, b"012", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        slices = collect_http_hls_slices(
            base_url,
            "/master.m3u8",
            "session-http-nested-master",
        )

    assert_slice_identity(slices, window_indexes=[12])
    cleanup_http_hls_session("session-http-nested-master")


def test_http_hls_loader_ignores_malformed_master_variant_entries_and_uses_first_valid_one(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A malformed master entry without a URI should not prevent using the next valid variant."""
    configure_http_hls_loader_test(monkeypatch, tmp_path)

    master_text = playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=300000,RESOLUTION=426x240',
        "# malformed first variant entry has no URI",
        '#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=960x540',
        "valid/index.m3u8",
    )
    media_text = media_playlist(15, "segment_valid_015.ts")
    routes = {
        "/master.m3u8": (200, master_text, _HLS_CONTENT_TYPE),
        "/valid/index.m3u8": (200, media_text, _HLS_CONTENT_TYPE),
        "/valid/segment_valid_015.ts": (200, b"015", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        slices = collect_http_hls_slices(
            base_url,
            "/master.m3u8",
            "session-http-master-malformed-entry",
        )

    assert_slice_identity(
        slices,
        source_names=["segment_valid_015.ts"],
        window_indexes=[15],
    )
    cleanup_http_hls_session("session-http-master-malformed-entry")


def test_http_hls_loader_resolves_parent_relative_segment_paths_from_nested_media_playlist(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Segment URIs with .. should resolve relative to the nested media playlist location."""
    configure_http_hls_loader_test(monkeypatch, tmp_path)

    media_text = media_playlist(
        50,
        "../segments/segment_050.ts",
        "../segments/segment_051.ts",
    )
    routes = {
        "/nested/live/index.m3u8": (200, media_text, _HLS_CONTENT_TYPE),
        "/nested/segments/segment_050.ts": (200, b"050", _TS_CONTENT_TYPE),
        "/nested/segments/segment_051.ts": (200, b"051", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        slices = collect_http_hls_slices(
            base_url,
            "/nested/live/index.m3u8",
            "session-http-parent-relative-segments",
        )

    assert_slice_identity(
        slices,
        source_names=["segment_050.ts", "segment_051.ts"],
        window_indexes=[50, 51],
    )
    cleanup_http_hls_session("session-http-parent-relative-segments")


def test_http_hls_loader_rejects_master_playlist_that_exceeds_supported_nesting_depth(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Master playlists nested beyond the supported depth should fail clearly."""
    configure_http_hls_loader_test(monkeypatch, tmp_path)

    master_level_1 = playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=300000,RESOLUTION=426x240',
        "level-2/master.m3u8",
    )
    master_level_2 = playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360',
        "level-3/master.m3u8",
    )
    master_level_3 = playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=750000,RESOLUTION=960x540',
        "level-4/master.m3u8",
    )
    master_level_4 = playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=1200000,RESOLUTION=1280x720',
        "level-5/index.m3u8",
    )
    routes = {
        "/master.m3u8": (200, master_level_1, _HLS_CONTENT_TYPE),
        "/level-2/master.m3u8": (200, master_level_2, _HLS_CONTENT_TYPE),
        "/level-2/level-3/master.m3u8": (200, master_level_3, _HLS_CONTENT_TYPE),
        "/level-2/level-3/level-4/master.m3u8": (200, master_level_4, _HLS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/master.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-master-depth")
        with pytest.raises(ValueError, match="nesting exceeded supported depth"):
            collect_api_stream_slices(loader, source)

    cleanup_http_hls_session("session-http-master-depth")


def test_http_hls_loader_rejects_master_playlist_without_any_usable_variant_uri(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A master playlist with only malformed variant entries should fail clearly."""
    configure_http_hls_loader_test(monkeypatch, tmp_path)

    master_text = playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=300000,RESOLUTION=426x240',
        "# no usable variant URI here",
        '#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=960x540',
        "   ",
    )
    routes = {
        "/master.m3u8": (200, master_text, _HLS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/master.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-master-no-usable-variant")
        with pytest.raises(
            ValueError,
            match="api_stream master playlist requires at least one variant URL",
        ):
            collect_api_stream_slices(loader, source)

    cleanup_http_hls_session("session-http-master-no-usable-variant")


def test_http_hls_loader_follows_variant_redirect_before_resolving_media_playlist(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A master-playlist variant may redirect before it reaches the final media playlist."""
    configure_http_hls_loader_test(monkeypatch, tmp_path)

    master_text = playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360',
        "variant/index.m3u8",
    )
    routes = {
        "/master.m3u8": (200, master_text, _HLS_CONTENT_TYPE),
        "/variant/index.m3u8": (
            302,
            "",
            "text/plain",
            {"Location": "/media/index.m3u8"},
        ),
        "/media/index.m3u8": (
            200,
            media_playlist(61, "segment_061.ts"),
            _HLS_CONTENT_TYPE,
        ),
        "/media/segment_061.ts": (200, b"061", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        slices = collect_http_hls_slices(
            base_url,
            "/master.m3u8",
            "session-http-master-variant-redirect",
        )

    assert_slice_identity(
        slices,
        source_names=["segment_061.ts"],
        window_indexes=[61],
    )
    cleanup_http_hls_session("session-http-master-variant-redirect")
