"""Tests for HTTP HLS limits, temp cleanup, and longer-running stability behavior.

These cases isolate budget exhaustion, cleanup guarantees, and soak/restart
coverage from the loader's ordinary fetch and reconnect paths.
"""

from pathlib import Path

import pytest

import config
import stream_loader
from analyzer_contract import AnalysisSlice
from session_io import read_api_stream_seen_chunk_keys, request_session_cancel
from stream_loader import (
    HttpHlsApiStreamLoader,
    build_api_stream_source_contract,
    build_api_stream_temp_session_dir,
    cleanup_api_stream_temp_session_dir,
    collect_api_stream_slices,
    iter_api_stream_slices,
)
from tests.stream_loader_http_hls_test_support import _serve_local_hls


def test_http_hls_loader_enforces_playlist_refresh_limit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A bounded refresh budget should stop unbounded provider churn explicitly."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_MAX_PLAYLIST_REFRESHES", 1)
    monkeypatch.setattr(config, "API_STREAM_MAX_IDLE_PLAYLIST_POLLS", 10)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    routes = {
        "/live/index.m3u8": [
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:0",
                        "#EXTINF:1.0,",
                        "segment_000.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:0",
                        "#EXTINF:1.0,",
                        "segment_000.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
        ],
        "/live/segment_000.ts": (200, b"000", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-refresh-limit")
        with pytest.raises(ValueError, match="playlist refresh limit exceeded"):
            collect_api_stream_slices(loader, source)

    assert loader.telemetry_snapshot().terminal_failure_reason == "api_stream playlist refresh limit exceeded"
    cleanup_api_stream_temp_session_dir("session-http-refresh-limit")


def test_http_hls_loader_enforces_session_runtime_limit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A bounded runtime should fail explicitly instead of polling forever."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_MAX_IDLE_PLAYLIST_POLLS", 10)
    monkeypatch.setattr(config, "API_STREAM_MAX_SESSION_RUNTIME_SEC", 5.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    ticks = iter([0.0, 6.0, 6.0, 6.0])
    monkeypatch.setattr(stream_loader.time, "monotonic", lambda: next(ticks))

    routes = {
        "/live/index.m3u8": (
            200,
            "\n".join(
                [
                    "#EXTM3U",
                    "#EXT-X-TARGETDURATION:1",
                    "#EXT-X-MEDIA-SEQUENCE:0",
                    "#EXTINF:1.0,",
                    "segment_000.ts",
                ]
            ),
            "application/vnd.apple.mpegurl",
        ),
        "/live/segment_000.ts": (200, b"000", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-runtime-limit")
        with pytest.raises(ValueError, match="session runtime exceeded max duration"):
            collect_api_stream_slices(loader, source)

    assert loader.telemetry_snapshot().terminal_failure_reason == "api_stream session runtime exceeded max duration"
    cleanup_api_stream_temp_session_dir("session-http-runtime-limit")


def test_http_hls_loader_keeps_session_temp_dirs_isolated_under_concurrent_runs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Concurrent live runs should keep temp materialization isolated per session."""
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXTINF:1.0,",
            "segment_000.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_000.ts": (200, b"000", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")

        def run_loader(session_id: str) -> tuple[list[AnalysisSlice], Path]:
            loader = HttpHlsApiStreamLoader(session_id)
            slices = collect_api_stream_slices(loader, source)
            return slices, build_api_stream_temp_session_dir(session_id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first_slices, first_dir = pool.submit(run_loader, "session-http-concurrent-a").result()
            second_slices, second_dir = pool.submit(run_loader, "session-http-concurrent-b").result()

    assert first_dir != second_dir
    assert all(first_dir in slice_.file_path.parents for slice_ in first_slices)
    assert all(second_dir in slice_.file_path.parents for slice_ in second_slices)
    cleanup_api_stream_temp_session_dir("session-http-concurrent-a")
    cleanup_api_stream_temp_session_dir("session-http-concurrent-b")


def test_http_hls_loader_stops_cleanly_when_cancel_is_requested_during_segment_download(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A cancel request during segment download should stop before temp media is written."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:82",
            "#EXTINF:1.0,",
            "segment_082.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_082.ts": (200, b"082", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-cancel-download")

        original_fetch = loader._fetch_segment_bytes

        def cancelling_fetch(url: str, segment_name: str) -> bytes:
            request_session_cancel("session-http-cancel-download")
            return original_fetch(url, segment_name)

        monkeypatch.setattr(loader, "_fetch_segment_bytes", cancelling_fetch)
        slices = collect_api_stream_slices(loader, source)

        temp_dir = build_api_stream_temp_session_dir("session-http-cancel-download")

    assert slices == []
    assert not any(temp_dir.iterdir())
    cleanup_api_stream_temp_session_dir("session-http-cancel-download")

def test_http_hls_loader_semi_soak_run_keeps_temp_cleanup_and_dedup_stable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A longer local HLS run should stay bounded in temp files, dedup state, and idle shutdown."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_MAX_IDLE_PLAYLIST_POLLS", 2)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    sleep_calls: list[float] = []
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    playlist_specs = [
        (600, 601, False),
        (601, 602, False),
        (602, 603, False),
        (603, 604, False),
        (604, 605, False),
        (605, 606, False),
        (606, 607, False),
        (607, 608, False),
        (608, 609, False),
        (609, 610, False),
        (610, 611, False),
        (610, 611, False),
        (610, 611, False),
    ]
    playlist_responses = []
    for first_index, second_index, is_endlist in playlist_specs:
        lines = [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            f"#EXT-X-MEDIA-SEQUENCE:{first_index}",
            "#EXTINF:1.0,",
            f"segment_{first_index}.ts",
            "#EXTINF:1.0,",
            f"segment_{second_index}.ts",
        ]
        if is_endlist:
            lines.append("#EXT-X-ENDLIST")
        playlist_responses.append(
            (200, "\n".join(lines), "application/vnd.apple.mpegurl")
        )

    routes: dict[str, object] = {
        "/live/index.m3u8": playlist_responses,
    }
    for index in range(600, 612):
        routes[f"/live/segment_{index}.ts"] = (
            200,
            f"segment-{index}".encode("utf-8"),
            "video/mp2t",
        )

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-semi-soak")
        temp_dir = build_api_stream_temp_session_dir("session-http-semi-soak")
        collected_indexes: list[int] = []

        for slice_ in iter_api_stream_slices(loader, source):
            assert slice_.window_index is not None
            collected_indexes.append(slice_.window_index)
            slice_.file_path.unlink()

        assert collected_indexes == list(range(600, 612))
        assert len(collected_indexes) == len(set(collected_indexes))
        assert read_api_stream_seen_chunk_keys("session-http-semi-soak") == {
            (source.input_path, index, f"segment_{index}.ts")
            for index in range(600, 612)
        }
        assert temp_dir.exists()
        assert not any(temp_dir.iterdir())

    assert len(sleep_calls) >= 2
    assert sleep_calls[-2:] == [0.0, 0.0]
    cleanup_api_stream_temp_session_dir("session-http-semi-soak")


def test_http_hls_loader_semi_soak_restart_keeps_persisted_dedup_and_temp_state_stable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A longer run across loader restarts should not replay persisted chunks or leak temp files."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_MAX_IDLE_PLAYLIST_POLLS", 1)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    routes = {
        "/live/index.m3u8": [
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:700",
                        "#EXTINF:1.0,",
                        "segment_700.ts",
                        "#EXTINF:1.0,",
                        "segment_701.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:701",
                        "#EXTINF:1.0,",
                        "segment_701.ts",
                        "#EXTINF:1.0,",
                        "segment_702.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:702",
                        "#EXTINF:1.0,",
                        "segment_702.ts",
                        "#EXTINF:1.0,",
                        "segment_703.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:703",
                        "#EXTINF:1.0,",
                        "segment_703.ts",
                        "#EXTINF:1.0,",
                        "segment_704.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:703",
                        "#EXTINF:1.0,",
                        "segment_703.ts",
                        "#EXTINF:1.0,",
                        "segment_704.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
        ],
    }
    for index in range(700, 705):
        routes[f"/live/segment_{index}.ts"] = (
            200,
            f"segment-{index}".encode("utf-8"),
            "video/mp2t",
        )

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        temp_dir = build_api_stream_temp_session_dir("session-http-semi-soak-restart")

        first_loader = HttpHlsApiStreamLoader("session-http-semi-soak-restart")
        first_indexes: list[int] = []
        for slice_ in iter_api_stream_slices(first_loader, source):
            assert slice_.window_index is not None
            first_indexes.append(slice_.window_index)
            slice_.file_path.unlink()
            if slice_.window_index == 702:
                break
        first_loader.close()

        assert first_indexes == [700, 701, 702]
        assert temp_dir.exists()
        assert not any(temp_dir.iterdir())
        assert read_api_stream_seen_chunk_keys("session-http-semi-soak-restart") == {
            (source.input_path, index, f"segment_{index}.ts")
            for index in range(700, 703)
        }

        second_loader = HttpHlsApiStreamLoader("session-http-semi-soak-restart")
        second_indexes: list[int] = []
        for slice_ in iter_api_stream_slices(second_loader, source):
            assert slice_.window_index is not None
            second_indexes.append(slice_.window_index)
            slice_.file_path.unlink()
        second_loader.close()

        assert second_indexes == [703, 704]
        assert not any(temp_dir.iterdir())
        assert read_api_stream_seen_chunk_keys("session-http-semi-soak-restart") == {
            (source.input_path, index, f"segment_{index}.ts")
            for index in range(700, 705)
        }

    cleanup_api_stream_temp_session_dir("session-http-semi-soak-restart")


def test_http_hls_loader_recovers_from_interrupted_run_by_clearing_stale_temp_media(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A restarted loader should drop orphaned temp media while preserving persisted dedup state."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXTINF:1.0,",
            "segment_000.ts",
            "#EXTINF:1.0,",
            "segment_001.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_000.ts": (200, b"000", "video/mp2t"),
        "/live/segment_001.ts": (200, b"001", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        session_id = "session-http-interrupted-recovery"
        temp_dir = build_api_stream_temp_session_dir(session_id)
        temp_dir.mkdir(parents=True, exist_ok=True)
        (temp_dir / "orphan-segment.ts").write_bytes(b"stale")
        stream_loader.append_api_stream_seen_chunk_key(
            session_id,
            (source.input_path, 0, "segment_000.ts"),
        )

        loader = HttpHlsApiStreamLoader(session_id)
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [1]
    assert [slice_.source_name for slice_ in slices] == ["segment_001.ts"]
    assert not (temp_dir / "orphan-segment.ts").exists()
    cleanup_api_stream_temp_session_dir("session-http-interrupted-recovery")


def test_http_hls_loader_enforces_temp_storage_budget(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Temp media materialization should stop when the configured disk budget is exceeded."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_TEMP_MAX_BYTES", 3)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXTINF:1.0,",
            "segment_000.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_000.ts": (200, b"toolarge", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-temp-budget")
        with pytest.raises(ValueError, match="temp storage exceeded max byte budget"):
            collect_api_stream_slices(loader, source)

    cleanup_api_stream_temp_session_dir("session-http-temp-budget")


def test_http_hls_loader_enforces_fetch_timeout_budget_cleanly(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Repeated playlist fetch timeouts should exhaust the reconnect budget predictably."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_MAX_RECONNECT_ATTEMPTS", 1)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader.time, "sleep", lambda seconds: None)

    monkeypatch.setattr(
        stream_loader,
        "urlopen",
        lambda request, timeout=None: (_ for _ in ()).throw(TimeoutError()),
    )

    loader = HttpHlsApiStreamLoader("session-http-timeout-budget")
    source = build_api_stream_source_contract("https://example.com/live/index.m3u8")

    with pytest.raises(ValueError, match="reconnect budget exhausted: api_stream fetch timed out"):
        collect_api_stream_slices(loader, source)

    cleanup_api_stream_temp_session_dir("session-http-timeout-budget")


def test_http_hls_loader_enforces_max_fetch_byte_budget_on_large_segments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Oversized segment downloads should fail before they can run away in real-data tests."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_MAX_FETCH_BYTES", 3)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXTINF:1.0,",
            "segment_000.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_000.ts": (200, b"toolarge", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-fetch-budget")
        with pytest.raises(ValueError, match="fetch exceeded max byte budget"):
            collect_api_stream_slices(loader, source)

    cleanup_api_stream_temp_session_dir("session-http-fetch-budget")
