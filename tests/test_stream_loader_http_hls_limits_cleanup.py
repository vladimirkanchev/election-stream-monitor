"""Focused HTTP/HLS loader temp-state, cleanup, and storage-budget tests."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import stream_loader_http_hls
from analyzer_contract import AnalysisSlice
from session_io import append_api_stream_seen_chunk_key, request_session_cancel
from stream_loader import (
    HttpHlsApiStreamLoader,
    build_api_stream_temp_session_dir,
    cleanup_api_stream_temp_session_dir,
    collect_api_stream_slices,
    iter_api_stream_slices,
)
from tests.http_hls_limits_test_support import (
    build_loader_source,
    configure_http_hls_limits_test,
    replace,
    request_url,
    segment_routes,
)
from tests.http_hls_test_support import (
    _HLS_CONTENT_TYPE,
    _TS_CONTENT_TYPE,
    build_http_hls_source,
    media_playlist,
)
from tests.local_hls_test_support import _serve_local_hls


def test_http_hls_loader_keeps_session_temp_dirs_isolated_under_concurrent_runs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Concurrent live runs should keep temp materialization isolated per session."""
    configure_http_hls_limits_test(monkeypatch, tmp_path)

    routes = {
        "/live/index.m3u8": (
            200,
            media_playlist(0, "segment_000.ts"),
            _HLS_CONTENT_TYPE,
        ),
        **segment_routes(0),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")

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
    configure_http_hls_limits_test(monkeypatch, tmp_path)

    routes = {
        "/live/index.m3u8": (
            200,
            media_playlist(82, "segment_082.ts"),
            _HLS_CONTENT_TYPE,
        ),
        **segment_routes(82),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = build_loader_source(
            base_url,
            "session-http-cancel-download",
        )
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


def test_http_hls_loader_recovers_from_interrupted_run_by_clearing_stale_temp_media(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A restarted loader should drop orphaned temp media while preserving persisted dedup state."""
    configure_http_hls_limits_test(monkeypatch, tmp_path)

    routes = {
        "/live/index.m3u8": (
            200,
            media_playlist(0, "segment_000.ts", "segment_001.ts"),
            _HLS_CONTENT_TYPE,
        ),
        **segment_routes(0, 1),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        session_id = "session-http-interrupted-recovery"
        temp_dir = build_api_stream_temp_session_dir(session_id)
        temp_dir.mkdir(parents=True, exist_ok=True)
        (temp_dir / "orphan-segment.ts").write_bytes(b"stale")
        append_api_stream_seen_chunk_key(
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
    configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        temp_max_bytes=3,
    )

    routes = {
        "/live/index.m3u8": (
            200,
            media_playlist(0, "segment_000.ts"),
            _HLS_CONTENT_TYPE,
        ),
        "/live/segment_000.ts": (200, b"toolarge", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = build_loader_source(
            base_url,
            "session-http-temp-budget",
        )
        with pytest.raises(ValueError, match="temp storage exceeded max byte budget"):
            collect_api_stream_slices(loader, source)

    cleanup_api_stream_temp_session_dir("session-http-temp-budget")


def test_http_hls_loader_enforces_max_fetch_byte_budget_on_large_segments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Oversized segment downloads should fail before they can run away in real-data tests."""
    configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_fetch_bytes=3,
    )

    routes = {
        "/live/index.m3u8": (
            200,
            media_playlist(0, "segment_000.ts"),
            _HLS_CONTENT_TYPE,
        ),
        "/live/segment_000.ts": (200, b"toolarge", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = build_loader_source(
            base_url,
            "session-http-fetch-budget",
        )
        with pytest.raises(ValueError, match="fetch exceeded max byte budget"):
            collect_api_stream_slices(loader, source)

    cleanup_api_stream_temp_session_dir("session-http-fetch-budget")


def test_http_hls_loader_enforces_temp_storage_budget_after_earlier_accepted_segments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Temp byte limits should still fire cleanly after earlier accepted progress."""
    configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        temp_max_bytes=6,
    )

    routes = {
        "/live/index.m3u8": (
            200,
            media_playlist(0, "segment_000.ts", "segment_001.ts"),
            _HLS_CONTENT_TYPE,
        ),
        "/live/segment_000.ts": (200, b"abc", _TS_CONTENT_TYPE),
        "/live/segment_001.ts": (200, b"wxyz", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = build_loader_source(
            base_url,
            "session-http-temp-budget-after-progress",
        )
        iterator = iter_api_stream_slices(loader, source)
        first_slice = next(iterator)

        with pytest.raises(ValueError, match="temp storage exceeded max byte budget"):
            next(iterator)

    assert first_slice.window_index == 0
    assert first_slice.file_path.exists()
    first_slice.file_path.unlink()
    cleanup_api_stream_temp_session_dir("session-http-temp-budget-after-progress")


def test_http_hls_loader_enforces_fetch_byte_budget_after_one_accepted_segment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Fetch byte limits should still fail clearly after one accepted segment has persisted."""
    configure_http_hls_limits_test(monkeypatch, tmp_path)

    routes = {
        "/live/index.m3u8": (
            200,
            media_playlist(0, "segment_000.ts", "segment_001.ts"),
            _HLS_CONTENT_TYPE,
        ),
        "/live/segment_000.ts": (200, b"abc", _TS_CONTENT_TYPE),
        "/live/segment_001.ts": (200, b"toolarge", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = build_loader_source(
            base_url,
            "session-http-fetch-budget-after-progress",
        )
        iterator = iter_api_stream_slices(loader, source)
        first_slice = next(iterator)
        loader._runtime_policy = replace(loader._runtime_policy, max_fetch_bytes=3)

        with pytest.raises(ValueError, match="fetch exceeded max byte budget"):
            next(iterator)

    assert first_slice.window_index == 0
    assert first_slice.file_path.exists()
    first_slice.file_path.unlink()
    cleanup_api_stream_temp_session_dir("session-http-fetch-budget-after-progress")


def test_http_hls_loader_cleans_temp_state_after_reconnect_budget_exhaustion(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Reconnect-budget exhaustion after earlier progress should leave the session temp dir clean."""
    session_id = "session-http-reconnect-budget-cleanup"
    sleep_calls: list[float] = []
    configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_reconnect_attempts=1,
        reconnect_backoff_sec=0.0,
        sleep=lambda seconds: sleep_calls.append(seconds),
    )

    routes = {
        "/live/index.m3u8": (
            200,
            media_playlist(0, "segment_000.ts", endlist=False),
            _HLS_CONTENT_TYPE,
        ),
        **segment_routes(0),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = build_loader_source(base_url, session_id)
        temp_dir = build_api_stream_temp_session_dir(session_id)
        original_urlopen = stream_loader_http_hls.urlopen
        playlist_fetch_count = 0

        def flaky_urlopen(request, timeout=None):
            nonlocal playlist_fetch_count
            current_url = request_url(request)
            if current_url.endswith("/live/index.m3u8"):
                playlist_fetch_count += 1
                if playlist_fetch_count >= 2:
                    raise TimeoutError()
            return original_urlopen(request, timeout=timeout)

        monkeypatch.setattr(stream_loader_http_hls, "urlopen", flaky_urlopen)
        iterator = iter_api_stream_slices(loader, source)
        first_slice = next(iterator)
        first_slice.file_path.unlink()

        with pytest.raises(
            ValueError,
            match="reconnect budget exhausted: api_stream fetch timed out",
        ):
            next(iterator)

    assert temp_dir.exists()
    assert not any(temp_dir.iterdir())
    assert 0.0 in sleep_calls
    assert loader.telemetry_snapshot().terminal_failure_reason == (
        "reconnect_budget_exhausted:api_stream fetch timed out"
    )
    cleanup_api_stream_temp_session_dir(session_id)
