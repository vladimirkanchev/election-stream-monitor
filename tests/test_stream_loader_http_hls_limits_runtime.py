"""Focused HTTP/HLS loader runtime-limit and shutdown behavior tests."""

from pathlib import Path

import pytest

import stream_loader_http_hls
from session_io import read_api_stream_seen_chunk_keys, request_session_cancel
from stream_loader import (
    HttpHlsApiStreamLoader,
    build_api_stream_source_contract,
    build_api_stream_temp_session_dir,
    cleanup_api_stream_temp_session_dir,
    collect_api_stream_slices,
    iter_api_stream_slices,
)
from tests.http_hls_limits_test_support import (
    build_loader_source,
    configure_http_hls_limits_test,
    request_url,
    seen_segment_keys,
    segment_routes,
)
from tests.http_hls_test_support import _HLS_CONTENT_TYPE, _TS_CONTENT_TYPE, media_playlist, no_sleep
from tests.local_hls_test_support import _serve_local_hls


def test_http_hls_loader_enforces_playlist_refresh_limit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A bounded refresh budget should stop unbounded provider churn explicitly."""
    configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_playlist_refreshes=1,
        max_idle_playlist_polls=10,
        sleep=no_sleep,
    )

    routes = {
        "/live/index.m3u8": [
            (200, media_playlist(0, "segment_000.ts", endlist=False), _HLS_CONTENT_TYPE),
            (200, media_playlist(0, "segment_000.ts", endlist=False), _HLS_CONTENT_TYPE),
        ],
        **segment_routes(0),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = build_loader_source(
            base_url,
            "session-http-refresh-limit",
        )
        with pytest.raises(ValueError, match="playlist refresh limit exceeded"):
            collect_api_stream_slices(loader, source)

    assert (
        loader.telemetry_snapshot().terminal_failure_reason
        == "api_stream playlist refresh limit exceeded"
    )
    cleanup_api_stream_temp_session_dir("session-http-refresh-limit")


def test_http_hls_loader_closes_once_after_endlist_terminal_completion(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The terminal loader path should close exactly once and leave cleanup to session ownership."""
    configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_idle_playlist_polls=10,
        sleep=no_sleep,
    )

    routes = {
        "/live/index.m3u8": (
            200,
            media_playlist(0, "segment_000.ts"),
            _HLS_CONTENT_TYPE,
        ),
        "/live/segment_000.ts": (200, b"000", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = build_loader_source(base_url, "session-http-close-on-endlist")
        close_calls: list[int] = []
        original_close = loader.close

        def counting_close() -> None:
            close_calls.append(1)
            original_close()

        monkeypatch.setattr(loader, "close", counting_close)
        slices = collect_api_stream_slices(loader, source)
        temp_dir = build_api_stream_temp_session_dir("session-http-close-on-endlist")

    assert [slice_.window_index for slice_ in slices] == [0]
    assert close_calls == [1]
    assert temp_dir.exists()
    cleanup_api_stream_temp_session_dir("session-http-close-on-endlist")


def test_http_hls_loader_enforces_session_runtime_limit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A bounded runtime should fail explicitly instead of polling forever."""
    ticks = iter([0.0, 6.0, 6.0, 6.0])
    configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_idle_playlist_polls=10,
        max_session_runtime_sec=5.0,
        monotonic=lambda: next(ticks),
    )

    routes = {
        "/live/index.m3u8": (
            200,
            media_playlist(0, "segment_000.ts"),
            _HLS_CONTENT_TYPE,
        ),
        **segment_routes(0),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = build_loader_source(
            base_url,
            "session-http-runtime-limit",
        )
        with pytest.raises(ValueError, match="session runtime exceeded max duration"):
            collect_api_stream_slices(loader, source)

    assert (
        loader.telemetry_snapshot().terminal_failure_reason
        == "api_stream session runtime exceeded max duration"
    )
    cleanup_api_stream_temp_session_dir("session-http-runtime-limit")


def test_http_hls_loader_enforces_fetch_timeout_budget_cleanly(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Repeated playlist fetch timeouts should exhaust the reconnect budget predictably."""
    configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_reconnect_attempts=1,
        reconnect_backoff_sec=0.0,
        sleep=no_sleep,
    )

    monkeypatch.setattr(
        stream_loader_http_hls,
        "urlopen",
        lambda request, timeout=None: (_ for _ in ()).throw(TimeoutError()),
    )

    loader = HttpHlsApiStreamLoader("session-http-timeout-budget")
    source = build_api_stream_source_contract("https://example.com/live/index.m3u8")

    with pytest.raises(
        ValueError,
        match="reconnect budget exhausted: api_stream fetch timed out",
    ):
        collect_api_stream_slices(loader, source)

    cleanup_api_stream_temp_session_dir("session-http-timeout-budget")


def test_http_hls_loader_enforces_runtime_limit_after_several_successful_refreshes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Runtime enforcement should still trigger after several successful live refreshes."""
    ticks = iter([0.0, 0.5, 1.0, 2.0, 2.5, 6.1])
    configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_idle_playlist_polls=10,
        max_session_runtime_sec=5.0,
        sleep=no_sleep,
        monotonic=lambda: next(ticks),
    )

    routes = {
        "/live/index.m3u8": [
            (
                200,
                media_playlist(800, "segment_800.ts", "segment_801.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                media_playlist(801, "segment_801.ts", "segment_802.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
        ],
        **segment_routes(800, 801, 802),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = build_loader_source(
            base_url,
            "session-http-runtime-late-limit",
        )
        iterator = iter_api_stream_slices(loader, source)
        collected_indexes: list[int] = []

        with pytest.raises(ValueError, match="session runtime exceeded max duration"):
            while True:
                slice_ = next(iterator)
                assert slice_.window_index is not None
                collected_indexes.append(slice_.window_index)
                slice_.file_path.unlink()

    assert collected_indexes == [800, 801, 802]
    assert read_api_stream_seen_chunk_keys("session-http-runtime-late-limit") == seen_segment_keys(
        source.input_path,
        *range(800, 803),
    )
    cleanup_api_stream_temp_session_dir("session-http-runtime-late-limit")


def test_http_hls_loader_stops_cleanly_when_cancel_is_requested_during_reconnect_backoff(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A cancel request during reconnect backoff should stop the run without promoting failure."""
    session_id = "session-http-cancel-reconnect-backoff"
    sleep_calls: list[float] = []

    def record_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if seconds == 0.5:
            request_session_cancel(session_id)

    configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_reconnect_attempts=3,
        reconnect_backoff_sec=0.5,
        sleep=record_sleep,
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
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [0]
    assert loader.telemetry_snapshot().terminal_failure_reason is None
    assert 0.5 in sleep_calls
    for slice_ in slices:
        slice_.file_path.unlink(missing_ok=True)
    cleanup_api_stream_temp_session_dir(session_id)


def test_http_hls_loader_enforces_playlist_refresh_limit_after_earlier_progress(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Refresh limits should still fail clearly after the loader has already accepted chunks."""
    session_id = "session-http-refresh-limit-after-progress"
    configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_playlist_refreshes=1,
        max_idle_playlist_polls=10,
        sleep=no_sleep,
    )

    routes = {
        "/live/index.m3u8": (
            200,
            media_playlist(1100, "segment_1100.ts", "segment_1101.ts", endlist=False),
            _HLS_CONTENT_TYPE,
        ),
        **segment_routes(1100, 1101),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = build_loader_source(base_url, session_id)
        iterator = iter_api_stream_slices(loader, source)
        collected_indexes: list[int | None] = []

        first_slice = next(iterator)
        second_slice = next(iterator)
        collected_indexes.extend([first_slice.window_index, second_slice.window_index])
        first_slice.file_path.unlink()
        second_slice.file_path.unlink()

        with pytest.raises(ValueError, match="playlist refresh limit exceeded"):
            next(iterator)

    assert collected_indexes == [1100, 1101]
    assert read_api_stream_seen_chunk_keys(session_id) == seen_segment_keys(
        source.input_path,
        *range(1100, 1102),
    )
    cleanup_api_stream_temp_session_dir(session_id)
