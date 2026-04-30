"""Tests for core HTTP/HLS provider oddities and malformed refresh recovery."""

from pathlib import Path

import pytest

import config
import stream_loader
from stream_loader import (
    HttpHlsApiStreamLoader,
    collect_api_stream_slices,
    iter_api_stream_slices,
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
    no_sleep,
    playlist,
    serve_dynamic_local_hls,
)
from tests.local_hls_test_support import _serve_local_hls


def test_http_hls_loader_treats_temporarily_malformed_refresh_as_retryable_noise(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A malformed 200 OK refresh should be skipped so later valid media can still continue."""
    configure_http_hls_loader_test(monkeypatch, tmp_path, sleep=no_sleep)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    warning_logs: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        stream_loader.logger,
        "warning",
        lambda message, *args: warning_logs.append((message, args)),
    )

    first_playlist = media_playlist(90, "segment_090.ts", endlist=False)
    final_playlist = media_playlist(90, "segment_090.ts", "segment_091.ts")
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, _HLS_CONTENT_TYPE),
            (200, "temporary html error", "text/plain"),
            (200, final_playlist, _HLS_CONTENT_TYPE),
        ],
        "/live/segment_090.ts": (200, b"090", _TS_CONTENT_TYPE),
        "/live/segment_091.ts": (200, b"091", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-malformed-refresh")
        slices = collect_api_stream_slices(loader, source)

    assert_slice_identity(slices, window_indexes=[90, 91])
    assert any(message == "Retryable api_stream failure [%s]" for message, _ in warning_logs)
    assert any(
        "session_id='session-http-malformed-refresh'" in str(args[0])
        and "reconnect_attempt=1" in str(args[0])
        for message, args in warning_logs
        if message == "Retryable api_stream failure [%s]"
    )
    cleanup_http_hls_session("session-http-malformed-refresh")


def test_http_hls_loader_surfaces_late_terminal_refresh_failure_after_emitting_early_segments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Already accepted segments should still be emitted before a later fatal refresh stops loading."""
    configure_http_hls_loader_test(monkeypatch, tmp_path, sleep=no_sleep)

    first_playlist = media_playlist(96, "segment_096.ts", endlist=False)
    fatal_refresh = playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=300000,RESOLUTION=426x240',
        "   ",
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, _HLS_CONTENT_TYPE),
            (200, fatal_refresh, _HLS_CONTENT_TYPE),
        ],
        "/live/segment_096.ts": (200, b"096", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-late-terminal-refresh")
        iterator = iter_api_stream_slices(loader, source)

        first_slice = next(iterator)
        assert first_slice.window_index == 96
        assert first_slice.source_name == "segment_096.ts"

        with pytest.raises(
            ValueError,
            match="api_stream master playlist requires at least one variant URL",
        ):
            next(iterator)

    cleanup_http_hls_session("session-http-late-terminal-refresh")


def test_http_hls_loader_treats_invalid_target_duration_tag_as_retryable_refresh_noise(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A refresh with a malformed TARGETDURATION tag should be skipped until a valid playlist appears."""
    configure_http_hls_loader_test(monkeypatch, tmp_path, sleep=no_sleep)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)

    first_playlist = media_playlist(92, "segment_092.ts", endlist=False)
    malformed_refresh = playlist(
        "#EXT-X-TARGETDURATION:not-a-number",
        "#EXT-X-MEDIA-SEQUENCE:92",
        "#EXTINF:1.0,",
        "segment_092.ts",
    )
    final_playlist = media_playlist(92, "segment_092.ts", "segment_093.ts")
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, _HLS_CONTENT_TYPE),
            (200, malformed_refresh, _HLS_CONTENT_TYPE),
            (200, final_playlist, _HLS_CONTENT_TYPE),
        ],
        "/live/segment_092.ts": (200, b"092", _TS_CONTENT_TYPE),
        "/live/segment_093.ts": (200, b"093", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-malformed-target-duration")
        slices = collect_api_stream_slices(loader, source)

    assert_slice_identity(slices, window_indexes=[92, 93])
    cleanup_http_hls_session("session-http-malformed-target-duration")


def test_http_hls_loader_recovers_from_partial_refresh_missing_segment_uri(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A partial refresh with a dangling EXTINF should recover once the next valid playlist arrives."""
    configure_http_hls_loader_test(monkeypatch, tmp_path, sleep=no_sleep)

    first_playlist = media_playlist(94, "segment_094.ts", endlist=False)
    partial_refresh = playlist(
        "#EXT-X-TARGETDURATION:1",
        "#EXT-X-MEDIA-SEQUENCE:94",
        "#EXTINF:1.0,",
        "segment_094.ts",
        "#EXTINF:1.0,",
    )
    final_playlist = media_playlist(94, "segment_094.ts", "segment_095.ts")
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, _HLS_CONTENT_TYPE),
            (200, partial_refresh, _HLS_CONTENT_TYPE),
            (200, final_playlist, _HLS_CONTENT_TYPE),
        ],
        "/live/segment_094.ts": (200, b"094", _TS_CONTENT_TYPE),
        "/live/segment_095.ts": (200, b"095", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-partial-refresh-recovery")
        slices = collect_api_stream_slices(loader, source)

    assert_slice_identity(slices, window_indexes=[94, 95])
    cleanup_http_hls_session("session-http-partial-refresh-recovery")


def test_http_hls_loader_continues_when_missing_segment_disappears_from_later_window(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A missing segment that falls out of the live window should not block later visible segments."""
    configure_http_hls_loader_test(monkeypatch, tmp_path, sleep=no_sleep)

    first_playlist = media_playlist(400, "segment_400.ts", "segment_401.ts", endlist=False)
    advanced_playlist = media_playlist(402, "segment_402.ts")
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, _HLS_CONTENT_TYPE),
            (200, advanced_playlist, _HLS_CONTENT_TYPE),
        ],
        "/live/segment_400.ts": (200, b"400", _TS_CONTENT_TYPE),
        "/live/segment_401.ts": (503, "busy", "text/plain"),
        "/live/segment_402.ts": (200, b"402", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-disappearing-segment")
        slices = collect_api_stream_slices(loader, source)

    assert_slice_identity(slices, window_indexes=[400, 402])
    cleanup_http_hls_session("session-http-disappearing-segment")


def test_http_hls_loader_handles_mixed_relative_and_absolute_segment_uris(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A media playlist may mix relative paths with absolute segment URLs."""
    configure_http_hls_loader_test(monkeypatch, tmp_path)

    def build_routes(base_url: str) -> dict[str, object]:
        playlist_text = playlist(
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:60",
            "#EXTINF:1.0,",
            "relative_060.ts",
            "#EXTINF:1.0,",
            f"{base_url}/cdn/segment_061.ts",
            "#EXT-X-ENDLIST",
        )
        return {
            "/live/index.m3u8": (200, playlist_text, _HLS_CONTENT_TYPE),
            "/live/relative_060.ts": (200, b"060", _TS_CONTENT_TYPE),
            "/cdn/segment_061.ts": (200, b"061", _TS_CONTENT_TYPE),
        }

    with serve_dynamic_local_hls(build_routes) as base_url:
        slices = collect_http_hls_slices(
            base_url,
            "/live/index.m3u8",
            "session-http-mixed-absolute-relative",
        )

    assert_slice_identity(
        slices,
        source_names=["relative_060.ts", "segment_061.ts"],
        window_indexes=[60, 61],
    )
    cleanup_http_hls_session("session-http-mixed-absolute-relative")


def test_http_hls_loader_accepts_uppercase_playlist_and_segment_suffixes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Uppercase playlist paths and segment suffixes should still load cleanly."""
    configure_http_hls_loader_test(monkeypatch, tmp_path)

    playlist_text = media_playlist(210, "SEGMENT_210.TS")
    routes = {
        "/LIVE/INDEX.M3U8": (200, playlist_text, _HLS_CONTENT_TYPE),
        "/LIVE/SEGMENT_210.TS": (200, b"210", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/LIVE/INDEX.M3U8")
        loader = HttpHlsApiStreamLoader("session-http-uppercase-suffixes")
        slices = collect_api_stream_slices(loader, source)

    assert_slice_identity(
        slices,
        source_names=["SEGMENT_210.TS"],
        window_indexes=[210],
    )
    cleanup_http_hls_session("session-http-uppercase-suffixes")


def test_http_hls_loader_fetches_query_string_segments_while_normalizing_source_names(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Segment fetches may require query strings even though emitted source names stay stable."""
    configure_http_hls_loader_test(monkeypatch, tmp_path)

    routes = {
        "/live/index.m3u8": (
            200,
            media_playlist(
                70,
                "segment_070.ts?token=alpha",
                "segment_071.ts?token=beta",
            ),
            _HLS_CONTENT_TYPE,
        ),
        "/live/segment_070.ts?token=alpha": (200, b"070", _TS_CONTENT_TYPE),
        "/live/segment_071.ts?token=beta": (200, b"071", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        slices = collect_http_hls_slices(
            base_url,
            "/live/index.m3u8",
            "session-http-query-segments",
        )

    assert_slice_identity(
        slices,
        source_names=["segment_070.ts", "segment_071.ts"],
        window_indexes=[70, 71],
    )
    cleanup_http_hls_session("session-http-query-segments")


def test_http_hls_loader_retries_playlist_fetch_before_succeeding(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Retryable playlist failures should be retried inside the loader seam."""
    configure_http_hls_loader_test(monkeypatch, tmp_path, sleep=no_sleep)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)

    playlist_text = media_playlist(0, "segment_000.ts")
    routes = {
        "/live/index.m3u8": [
            (503, "upstream busy", "text/plain"),
            (200, playlist_text, _HLS_CONTENT_TYPE),
        ],
        "/live/segment_000.ts": (200, b"ok", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-retry")
        slices = collect_api_stream_slices(loader, source)

    assert_slice_identity(slices, source_names=["segment_000.ts"])
    cleanup_http_hls_session("session-http-retry")


def test_http_hls_loader_retries_playlist_fetch_after_http_429(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """HTTP 429 responses should be treated like retryable provider throttling."""
    configure_http_hls_loader_test(monkeypatch, tmp_path, sleep=no_sleep)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)

    routes = {
        "/live/index.m3u8": [
            (429, "slow down", "text/plain"),
            (200, media_playlist(0, "segment_000.ts"), _HLS_CONTENT_TYPE),
        ],
        "/live/segment_000.ts": (200, b"ok", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-retry-429")
        slices = collect_api_stream_slices(loader, source)

    assert_slice_identity(slices, source_names=["segment_000.ts"])
    assert loader.telemetry_snapshot().reconnect_attempt_count == 1
    cleanup_http_hls_session("session-http-retry-429")


def test_http_hls_loader_surfaces_http_403_as_explicit_terminal_provider_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """HTTP 403 stays terminal today and should surface a clear provider-facing reason."""
    configure_http_hls_loader_test(monkeypatch, tmp_path)

    routes = {
        "/live/index.m3u8": [(403, "forbidden", "text/plain")],
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-403")
        with pytest.raises(ValueError, match="HTTP 403"):
            collect_api_stream_slices(loader, source)

    assert loader.telemetry_snapshot().terminal_failure_reason == "api_stream upstream returned HTTP 403"
    cleanup_http_hls_session("session-http-403")


def test_http_hls_loader_follows_playlist_redirects(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Provider-style playlist redirects should resolve before normal polling begins."""
    configure_http_hls_loader_test(monkeypatch, tmp_path)

    routes = {
        "/entry.m3u8": (302, "", "text/plain", {"Location": "/live/index.m3u8"}),
        "/live/index.m3u8": (
            200,
            media_playlist(10, "segment_010.ts"),
            _HLS_CONTENT_TYPE,
        ),
        "/live/segment_010.ts": (200, b"010", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/entry.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-redirect")
        slices = collect_api_stream_slices(loader, source)

    assert_slice_identity(slices, window_indexes=[10])
    cleanup_http_hls_session("session-http-redirect")


def test_http_hls_loader_tolerates_playlist_with_odd_content_type(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Some providers serve playlists with generic content types; parsing should stay text-based."""
    configure_http_hls_loader_test(monkeypatch, tmp_path)

    routes = {
        "/live/index.m3u8": (
            200,
            media_playlist(12, "segment_012.ts"),
            "text/plain",
        ),
        "/live/segment_012.ts": (200, b"012", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-odd-content-type")
        slices = collect_api_stream_slices(loader, source)

    assert_slice_identity(slices, window_indexes=[12])
    cleanup_http_hls_session("session-http-odd-content-type")
