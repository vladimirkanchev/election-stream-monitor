"""Tests for HTTP HLS retry, reconnect, and replay de-duplication behavior.

This file keeps transport recovery and playlist-window movement cases isolated
from ordinary core-loader semantics and hard-limit scenarios.
"""

from pathlib import Path

import pytest

import config
import stream_loader
from session_io import read_api_stream_seen_chunk_keys, request_session_cancel
from stream_loader import (
    HttpHlsApiStreamLoader,
    build_api_stream_source_contract,
    cleanup_api_stream_temp_session_dir,
    collect_api_stream_slices,
)
from tests.stream_loader_http_hls_test_support import _serve_local_hls


def test_http_hls_loader_resumes_after_outage_when_playlist_window_moves(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A reconnect should resume from the next visible segment when older ones disappeared."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    info_logs: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        stream_loader.logger,
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


def test_http_hls_loader_stops_cleanly_when_cancel_is_requested_just_after_reconnect(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A cancel request during reconnect backoff should stop the live loop cleanly."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 1.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    def maybe_cancel_on_sleep(seconds: float) -> None:
        if seconds == 1.0:
            request_session_cancel("session-http-cancel-reconnect")

    monkeypatch.setattr(stream_loader.time, "sleep", maybe_cancel_on_sleep)

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
    tmp_path: Path,
) -> None:
    """A replayed segment after reconnect should be skipped while the new segment still runs."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

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
    tmp_path: Path,
) -> None:
    """A temporary segment outage should be skipped while later segments still progress."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

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


def test_http_hls_loader_fails_when_reconnect_budget_is_exhausted(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Repeated retryable playlist failures should become terminal after the configured budget."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

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


def test_http_hls_loader_recovers_after_multiple_retryable_playlist_failures(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Multiple retryable playlist failures should still recover while budget remains."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

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


def test_http_hls_loader_persists_identity_keys_and_skips_replayed_segments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Persisted de-dup keys should prevent replay after reconnect or repeated loader startup."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

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
    tmp_path: Path,
) -> None:
    """Playlist replay should not duplicate already accepted live segments in one run."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

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
    tmp_path: Path,
) -> None:
    """Loader logs should expose variant choice, refresh counts, new segments, and replay skips."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    info_logs: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        stream_loader.logger,
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
