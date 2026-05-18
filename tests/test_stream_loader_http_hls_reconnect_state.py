"""Tests for HTTP/HLS reconnect budget, replay state, and recovery logging behavior."""

import pytest

import stream_loader_http_hls
from session_io import read_api_stream_seen_chunk_keys
from stream_loader import (
    HttpHlsApiStreamLoader,
    build_api_stream_source_contract,
    cleanup_api_stream_temp_session_dir,
    collect_api_stream_slices,
)
from tests.http_hls_reconnect_test_support import configure_http_hls_reconnect_test
from tests.local_hls_test_support import _serve_local_hls


def test_http_hls_loader_fails_when_reconnect_budget_is_exhausted(
    monkeypatch,
    tmp_path,
) -> None:
    """Repeated retryable playlist failures should become terminal after the configured budget."""
    configure_http_hls_reconnect_test(monkeypatch, tmp_path, reconnect_backoff_sec=0.0, sleep=lambda seconds: None)

    routes = {
        "/live/index.m3u8": [
            (503, "busy", "text/plain"),
            (503, "busy", "text/plain"),
            (503, "busy", "text/plain"),
            (503, "busy", "text/plain"),
            (503, "busy", "text/plain"),
        ],
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-budget")
        with pytest.raises(ValueError, match="reconnect budget exhausted"):
            collect_api_stream_slices(loader, source)

    cleanup_api_stream_temp_session_dir("session-http-budget")


def test_http_hls_loader_persists_identity_keys_and_skips_replayed_segments(
    monkeypatch,
    tmp_path,
) -> None:
    """Persisted de-dup keys should prevent replay after reconnect or repeated loader startup."""
    configure_http_hls_reconnect_test(monkeypatch, tmp_path)

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:5",
            "#EXTINF:1.0,",
            "segment_005.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_005.ts": (200, b"005", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        first_loader = HttpHlsApiStreamLoader("session-http-dedup")
        first_slices = collect_api_stream_slices(first_loader, source)
        second_loader = HttpHlsApiStreamLoader("session-http-dedup")
        second_slices = collect_api_stream_slices(second_loader, source)

    assert [slice_.window_index for slice_ in first_slices] == [5]
    assert second_slices == []
    assert read_api_stream_seen_chunk_keys("session-http-dedup") == {
        (source.input_path, 5, "segment_005.ts")
    }
    cleanup_api_stream_temp_session_dir("session-http-dedup")


def test_http_hls_loader_skips_duplicate_segment_replay_during_playlist_refresh(
    monkeypatch,
    tmp_path,
) -> None:
    """Playlist replay should not duplicate already accepted live segments in one run."""
    configure_http_hls_reconnect_test(monkeypatch, tmp_path, sleep=lambda seconds: None)

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:7",
            "#EXTINF:1.0,",
            "segment_007.ts",
        ]
    )
    replayed_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:7",
            "#EXTINF:1.0,",
            "segment_007.ts",
            "#EXTINF:1.0,",
            "segment_008.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, replayed_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_007.ts": (200, b"007", "video/mp2t"),
        "/live/segment_008.ts": (200, b"008", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-replay")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [7, 8]
    assert [slice_.source_name for slice_ in slices] == ["segment_007.ts", "segment_008.ts"]
    cleanup_api_stream_temp_session_dir("session-http-replay")


def test_http_hls_loader_logs_selected_variant_refresh_stats_and_replay_skips(
    monkeypatch,
    tmp_path,
) -> None:
    """Loader logs should expose variant choice, refresh counts, new segments, and replay skips."""
    configure_http_hls_reconnect_test(monkeypatch, tmp_path, sleep=lambda seconds: None)

    info_logs: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        stream_loader_http_hls.logger,
        "info",
        lambda message, *args: info_logs.append((message, args)),
    )

    master_text = "\n".join(
        [
            "#EXTM3U",
            '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360',
            "low/index.m3u8",
            '#EXT-X-STREAM-INF:BANDWIDTH=1200000,RESOLUTION=1280x720',
            "high/index.m3u8",
        ]
    )
    first_media = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:50",
            "#EXTINF:1.0,",
            "segment_050.ts",
        ]
    )
    second_media = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:50",
            "#EXTINF:1.0,",
            "segment_050.ts",
            "#EXTINF:1.0,",
            "segment_051.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/master.m3u8": (200, master_text, "application/vnd.apple.mpegurl"),
        "/low/index.m3u8": [
            (200, first_media, "application/vnd.apple.mpegurl"),
            (200, second_media, "application/vnd.apple.mpegurl"),
        ],
        "/high/index.m3u8": (200, second_media, "application/vnd.apple.mpegurl"),
        "/low/segment_050.ts": (200, b"050", "video/mp2t"),
        "/low/segment_051.ts": (200, b"051", "video/mp2t"),
        "/high/segment_050.ts": (200, b"050", "video/mp2t"),
        "/high/segment_051.ts": (200, b"051", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/master.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-logs")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [50, 51]
    assert any(message == "Selected api_stream variant [%s]" for message, _ in info_logs)
    refresh_logs = [args[0] for message, args in info_logs if message == "Refreshed api_stream playlist [%s]"]
    assert refresh_logs
    assert any("session_id='session-http-logs'" in str(entry) for entry in refresh_logs)
    assert any("playlist_refresh_count=1" in str(entry) and "new_segment_count=1" in str(entry) for entry in refresh_logs)
    assert any("playlist_refresh_count=2" in str(entry) and "new_segment_count=1" in str(entry) and "skipped_replay_count=1" in str(entry) for entry in refresh_logs)
    cleanup_api_stream_temp_session_dir("session-http-logs")
