"""Tests for HTTP/HLS reconnect recovery and continued progression behavior."""

import stream_loader_http_hls
from session_io import request_session_cancel
from stream_loader import (
    HttpHlsApiStreamLoader,
    build_api_stream_source_contract,
    cleanup_api_stream_temp_session_dir,
    collect_api_stream_slices,
)
from tests.http_hls_reconnect_test_support import configure_http_hls_reconnect_test
from tests.local_hls_test_support import _serve_local_hls


def test_http_hls_loader_resumes_after_outage_when_playlist_window_moves(
    monkeypatch,
    tmp_path,
) -> None:
    """A reconnect should resume from the next visible segment when older ones disappeared."""
    configure_http_hls_reconnect_test(monkeypatch, tmp_path, reconnect_backoff_sec=0.0, sleep=lambda seconds: None)

    info_logs: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        stream_loader_http_hls.logger,
        "info",
        lambda message, *args: info_logs.append((message, args)),
    )

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:100",
            "#EXTINF:1.0,",
            "segment_100.ts",
        ]
    )
    resumed_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:102",
            "#EXTINF:1.0,",
            "segment_102.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (503, "busy", "text/plain"),
            (200, resumed_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_100.ts": (200, b"100", "video/mp2t"),
        "/live/segment_102.ts": (200, b"102", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-resume-gap")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [100, 102]
    assert any(message == "api_stream playlist window advanced [%s]" for message, _ in info_logs)
    cleanup_api_stream_temp_session_dir("session-http-resume-gap")


def test_http_hls_loader_resumes_after_larger_playlist_window_jump_and_prunes_replays(
    monkeypatch,
    tmp_path,
) -> None:
    """A larger window jump should still prune replayed segments and keep newer work flowing."""
    configure_http_hls_reconnect_test(monkeypatch, tmp_path, reconnect_backoff_sec=0.0, sleep=lambda seconds: None)

    info_logs: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        stream_loader_http_hls.logger,
        "info",
        lambda message, *args: info_logs.append((message, args)),
    )

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:100",
            "#EXTINF:1.0,",
            "segment_100.ts",
            "#EXTINF:1.0,",
            "segment_101.ts",
        ]
    )
    advanced_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:104",
            "#EXTINF:1.0,",
            "segment_104.ts",
            "#EXTINF:1.0,",
            "segment_105.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (503, "busy", "text/plain"),
            (200, advanced_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_100.ts": (200, b"100", "video/mp2t"),
        "/live/segment_101.ts": (200, b"101", "video/mp2t"),
        "/live/segment_104.ts": (200, b"104", "video/mp2t"),
        "/live/segment_105.ts": (200, b"105", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-large-gap")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [100, 101, 104, 105]
    assert any(
        "missed_segment_count=2" in str(args[0])
        for message, args in info_logs
        if message == "api_stream playlist window advanced [%s]"
    )
    cleanup_api_stream_temp_session_dir("session-http-large-gap")


def test_http_hls_loader_stops_cleanly_when_cancel_is_requested_just_after_reconnect(
    monkeypatch,
    tmp_path,
) -> None:
    """A cancel request during reconnect backoff should stop the live loop cleanly."""
    configure_http_hls_reconnect_test(
        monkeypatch,
        tmp_path,
        reconnect_backoff_sec=1.0,
        sleep=None,
    )

    def maybe_cancel_on_sleep(seconds: float) -> None:
        if seconds == 1.0:
            request_session_cancel("session-http-cancel-reconnect")

    monkeypatch.setattr(stream_loader_http_hls.time, "sleep", maybe_cancel_on_sleep)

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:150",
            "#EXTINF:1.0,",
            "segment_150.ts",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (503, "busy", "text/plain"),
        ],
        "/live/segment_150.ts": (200, b"150", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-cancel-reconnect")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [150]
    cleanup_api_stream_temp_session_dir("session-http-cancel-reconnect")


def test_http_hls_loader_skips_replayed_segment_after_reconnect_and_keeps_new_work(
    monkeypatch,
    tmp_path,
) -> None:
    """A replayed segment after reconnect should be skipped while the new segment still runs."""
    configure_http_hls_reconnect_test(monkeypatch, tmp_path, reconnect_backoff_sec=0.0, sleep=lambda seconds: None)

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:200",
            "#EXTINF:1.0,",
            "segment_200.ts",
        ]
    )
    replayed_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:200",
            "#EXTINF:1.0,",
            "segment_200.ts",
            "#EXTINF:1.0,",
            "segment_201.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (503, "busy", "text/plain"),
            (200, replayed_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_200.ts": (200, b"200", "video/mp2t"),
        "/live/segment_201.ts": (200, b"201", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-resume-replay")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [200, 201]
    cleanup_api_stream_temp_session_dir("session-http-resume-replay")


def test_http_hls_loader_skips_temporarily_unavailable_segment_and_continues(
    monkeypatch,
    tmp_path,
) -> None:
    """A temporary segment outage should be skipped while later segments still progress."""
    configure_http_hls_reconnect_test(monkeypatch, tmp_path, sleep=lambda seconds: None)

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXTINF:1.0,",
            "segment_000.ts",
            "#EXTINF:1.0,",
            "segment_001.ts",
            "#EXTINF:1.0,",
            "segment_002.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_000.ts": (200, b"ok-000", "video/mp2t"),
        "/live/segment_001.ts": (503, "temporarily busy", "text/plain"),
        "/live/segment_002.ts": (200, b"ok-002", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-temp-outage")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.source_name for slice_ in slices] == ["segment_000.ts", "segment_002.ts"]
    assert [slice_.window_index for slice_ in slices] == [0, 2]
    cleanup_api_stream_temp_session_dir("session-http-temp-outage")


def test_http_hls_loader_recovers_after_multiple_retryable_playlist_failures(
    monkeypatch,
    tmp_path,
) -> None:
    """Multiple retryable playlist failures should still recover while budget remains."""
    configure_http_hls_reconnect_test(monkeypatch, tmp_path, reconnect_backoff_sec=0.0, sleep=lambda seconds: None)

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:10",
            "#EXTINF:1.0,",
            "segment_010.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (503, "busy", "text/plain"),
            (503, "busy", "text/plain"),
            (200, playlist_text, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_010.ts": (200, b"010", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-multi-recover")
        slices = collect_api_stream_slices(loader, source)
        telemetry = loader.telemetry_snapshot()

    assert [slice_.window_index for slice_ in slices] == [10]
    assert telemetry.reconnect_attempt_count == 2
    assert telemetry.reconnect_budget_exhaustion_count == 0
    assert telemetry.terminal_failure_reason is None
    cleanup_api_stream_temp_session_dir("session-http-multi-recover")
