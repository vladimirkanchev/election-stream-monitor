"""Tests for HTTP/HLS limits, temp cleanup, and longer-running stability.

These cases isolate budget exhaustion, cleanup guarantees, and soak/restart
coverage from the loader shell's ordinary fetch and reconnect paths so
failures can be attributed to one concern more quickly. Direct helper coverage
for temp-file writes and byte accounting lives in the dedicated helper test
files.
"""

from dataclasses import replace
from pathlib import Path

import pytest

import config
import stream_loader_http_hls
from analyzer_contract import AnalysisSlice
from session_io import (
    append_api_stream_seen_chunk_key,
    read_api_stream_seen_chunk_keys,
    request_session_cancel,
)
from stream_loader import (
    HttpHlsApiStreamLoader,
    build_api_stream_source_contract,
    build_api_stream_temp_session_dir,
    cleanup_api_stream_temp_session_dir,
    collect_api_stream_slices,
    iter_api_stream_slices,
)
from tests.local_hls_test_support import _serve_local_hls

_HLS_CONTENT_TYPE = "application/vnd.apple.mpegurl"
_TS_CONTENT_TYPE = "video/mp2t"


def _configure_http_hls_limits_test(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    poll_interval_sec: float = 0.0,
    max_idle_playlist_polls: int | None = None,
    max_playlist_refreshes: int | None = None,
    max_session_runtime_sec: float | None = None,
    max_reconnect_attempts: int | None = None,
    reconnect_backoff_sec: float | None = None,
    temp_max_bytes: int | None = None,
    max_fetch_bytes: int | None = None,
    sleep=None,
    monotonic=None,
) -> None:
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", poll_interval_sec)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    if max_idle_playlist_polls is not None:
        monkeypatch.setattr(
            config,
            "API_STREAM_MAX_IDLE_PLAYLIST_POLLS",
            max_idle_playlist_polls,
        )
    if max_playlist_refreshes is not None:
        monkeypatch.setattr(
            config,
            "API_STREAM_MAX_PLAYLIST_REFRESHES",
            max_playlist_refreshes,
        )
    if max_session_runtime_sec is not None:
        monkeypatch.setattr(
            config,
            "API_STREAM_MAX_SESSION_RUNTIME_SEC",
            max_session_runtime_sec,
        )
    if max_reconnect_attempts is not None:
        monkeypatch.setattr(
            config,
            "API_STREAM_MAX_RECONNECT_ATTEMPTS",
            max_reconnect_attempts,
        )
    if reconnect_backoff_sec is not None:
        monkeypatch.setattr(
            config,
            "API_STREAM_RECONNECT_BACKOFF_SEC",
            reconnect_backoff_sec,
        )
    if temp_max_bytes is not None:
        monkeypatch.setattr(config, "API_STREAM_TEMP_MAX_BYTES", temp_max_bytes)
    if max_fetch_bytes is not None:
        monkeypatch.setattr(config, "API_STREAM_MAX_FETCH_BYTES", max_fetch_bytes)
    if sleep is not None:
        monkeypatch.setattr(stream_loader_http_hls.time, "sleep", sleep)
    if monotonic is not None:
        monkeypatch.setattr(stream_loader_http_hls.time, "monotonic", monotonic)


def _playlist(*lines: str) -> str:
    return "\n".join(["#EXTM3U", *lines])


def _media_playlist(
    media_sequence: int,
    *segments: str,
    target_duration: int = 1,
    endlist: bool = True,
) -> str:
    lines = [
        f"#EXT-X-TARGETDURATION:{target_duration}",
        f"#EXT-X-MEDIA-SEQUENCE:{media_sequence}",
    ]
    for segment in segments:
        lines.extend(["#EXTINF:1.0,", segment])
    if endlist:
        lines.append("#EXT-X-ENDLIST")
    return _playlist(*lines)


def _segment_routes(
    *indexes: int,
    prefix: str = "/live",
    body_prefix: str = "segment-",
) -> dict[str, tuple[int, bytes, str]]:
    return {
        f"{prefix}/segment_{index:03d}.ts": (
            200,
            f"{body_prefix}{index}".encode("utf-8"),
            _TS_CONTENT_TYPE,
        )
        for index in indexes
    }


def _build_loader_source(
    base_url: str,
    session_id: str,
    *,
    playlist_path: str = "/live/index.m3u8",
) -> tuple[HttpHlsApiStreamLoader, object]:
    loader = HttpHlsApiStreamLoader(session_id)
    source = build_api_stream_source_contract(f"{base_url}{playlist_path}")
    return loader, source


def test_http_hls_loader_enforces_playlist_refresh_limit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A bounded refresh budget should stop unbounded provider churn explicitly."""
    _configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_playlist_refreshes=1,
        max_idle_playlist_polls=10,
        sleep=lambda seconds: None,
    )

    routes = {
        "/live/index.m3u8": [
            (200, _media_playlist(0, "segment_000.ts", endlist=False), _HLS_CONTENT_TYPE),
            (200, _media_playlist(0, "segment_000.ts", endlist=False), _HLS_CONTENT_TYPE),
        ],
        **_segment_routes(0),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = _build_loader_source(
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
    _configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_idle_playlist_polls=10,
        sleep=lambda seconds: None,
    )

    routes = {
        "/live/index.m3u8": (
            200,
            _media_playlist(0, "segment_000.ts"),
            _HLS_CONTENT_TYPE,
        ),
        "/live/segment_000.ts": (200, b"000", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = _build_loader_source(base_url, "session-http-close-on-endlist")
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
    _configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_idle_playlist_polls=10,
        max_session_runtime_sec=5.0,
        monotonic=lambda: next(ticks),
    )

    routes = {
        "/live/index.m3u8": (
            200,
            _media_playlist(0, "segment_000.ts"),
            _HLS_CONTENT_TYPE,
        ),
        **_segment_routes(0),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = _build_loader_source(
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


def test_http_hls_loader_keeps_session_temp_dirs_isolated_under_concurrent_runs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Concurrent live runs should keep temp materialization isolated per session."""
    from concurrent.futures import ThreadPoolExecutor

    _configure_http_hls_limits_test(monkeypatch, tmp_path)

    routes = {
        "/live/index.m3u8": (
            200,
            _media_playlist(0, "segment_000.ts"),
            _HLS_CONTENT_TYPE,
        ),
        **_segment_routes(0),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")

        def run_loader(session_id: str) -> tuple[list[AnalysisSlice], Path]:
            loader = HttpHlsApiStreamLoader(session_id)
            slices = collect_api_stream_slices(loader, source)
            return slices, build_api_stream_temp_session_dir(session_id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first_slices, first_dir = pool.submit(
                run_loader,
                "session-http-concurrent-a",
            ).result()
            second_slices, second_dir = pool.submit(
                run_loader,
                "session-http-concurrent-b",
            ).result()

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
    _configure_http_hls_limits_test(monkeypatch, tmp_path)

    routes = {
        "/live/index.m3u8": (
            200,
            _media_playlist(82, "segment_082.ts"),
            _HLS_CONTENT_TYPE,
        ),
        **_segment_routes(82),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = _build_loader_source(
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


def test_http_hls_loader_semi_soak_run_keeps_temp_cleanup_and_dedup_stable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A longer local HLS run should stay bounded in temp files, dedup state, and idle shutdown."""
    sleep_calls: list[float] = []
    _configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_idle_playlist_polls=2,
        sleep=lambda seconds: sleep_calls.append(seconds),
    )

    playlist_specs = [
        (600, 601),
        (601, 602),
        (602, 603),
        (603, 604),
        (604, 605),
        (605, 606),
        (606, 607),
        (607, 608),
        (608, 609),
        (609, 610),
        (610, 611),
        (610, 611),
        (610, 611),
    ]
    playlist_responses = [
        (
            200,
            _media_playlist(first_index, f"segment_{first_index}.ts", f"segment_{second_index}.ts", endlist=False),
            _HLS_CONTENT_TYPE,
        )
        for first_index, second_index in playlist_specs
    ]

    routes: dict[str, object] = {
        "/live/index.m3u8": playlist_responses,
        **_segment_routes(*range(600, 612)),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = _build_loader_source(base_url, "session-http-semi-soak")
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
    _configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_idle_playlist_polls=1,
        sleep=lambda seconds: None,
    )

    routes = {
        "/live/index.m3u8": [
            (
                200,
                _media_playlist(700, "segment_700.ts", "segment_701.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                _media_playlist(701, "segment_701.ts", "segment_702.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                _media_playlist(702, "segment_702.ts", "segment_703.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                _media_playlist(703, "segment_703.ts", "segment_704.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                _media_playlist(703, "segment_703.ts", "segment_704.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
        ],
        **_segment_routes(*range(700, 705)),
    }

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
    _configure_http_hls_limits_test(monkeypatch, tmp_path)

    routes = {
        "/live/index.m3u8": (
            200,
            _media_playlist(0, "segment_000.ts", "segment_001.ts"),
            _HLS_CONTENT_TYPE,
        ),
        **_segment_routes(0, 1),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
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
    _configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        temp_max_bytes=3,
    )

    routes = {
        "/live/index.m3u8": (
            200,
            _media_playlist(0, "segment_000.ts"),
            _HLS_CONTENT_TYPE,
        ),
        "/live/segment_000.ts": (200, b"toolarge", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = _build_loader_source(
            base_url,
            "session-http-temp-budget",
        )
        with pytest.raises(ValueError, match="temp storage exceeded max byte budget"):
            collect_api_stream_slices(loader, source)

    cleanup_api_stream_temp_session_dir("session-http-temp-budget")


def test_http_hls_loader_enforces_fetch_timeout_budget_cleanly(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Repeated playlist fetch timeouts should exhaust the reconnect budget predictably."""
    _configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_reconnect_attempts=1,
        reconnect_backoff_sec=0.0,
        sleep=lambda seconds: None,
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


def test_http_hls_loader_enforces_max_fetch_byte_budget_on_large_segments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Oversized segment downloads should fail before they can run away in real-data tests."""
    _configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_fetch_bytes=3,
    )

    routes = {
        "/live/index.m3u8": (
            200,
            _media_playlist(0, "segment_000.ts"),
            _HLS_CONTENT_TYPE,
        ),
        "/live/segment_000.ts": (200, b"toolarge", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = _build_loader_source(
            base_url,
            "session-http-fetch-budget",
        )
        with pytest.raises(ValueError, match="fetch exceeded max byte budget"):
            collect_api_stream_slices(loader, source)

    cleanup_api_stream_temp_session_dir("session-http-fetch-budget")


def test_http_hls_loader_enforces_runtime_limit_after_several_successful_refreshes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Runtime enforcement should still trigger after several successful live refreshes."""
    ticks = iter([0.0, 0.5, 1.0, 2.0, 2.5, 6.1])
    _configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_idle_playlist_polls=10,
        max_session_runtime_sec=5.0,
        sleep=lambda seconds: None,
        monotonic=lambda: next(ticks),
    )

    routes = {
        "/live/index.m3u8": [
            (
                200,
                _media_playlist(800, "segment_800.ts", "segment_801.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                _media_playlist(801, "segment_801.ts", "segment_802.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
        ],
        **_segment_routes(800, 801, 802),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = _build_loader_source(
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
    assert read_api_stream_seen_chunk_keys("session-http-runtime-late-limit") == {
        (source.input_path, index, f"segment_{index}.ts")
        for index in range(800, 803)
    }
    cleanup_api_stream_temp_session_dir("session-http-runtime-late-limit")


def test_http_hls_loader_enforces_temp_storage_budget_after_earlier_accepted_segments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Temp byte limits should still fire cleanly after earlier accepted progress."""
    _configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        temp_max_bytes=6,
    )

    routes = {
        "/live/index.m3u8": (
            200,
            _media_playlist(0, "segment_000.ts", "segment_001.ts"),
            _HLS_CONTENT_TYPE,
        ),
        "/live/segment_000.ts": (200, b"abc", _TS_CONTENT_TYPE),
        "/live/segment_001.ts": (200, b"wxyz", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = _build_loader_source(
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
    _configure_http_hls_limits_test(monkeypatch, tmp_path)

    routes = {
        "/live/index.m3u8": (
            200,
            _media_playlist(0, "segment_000.ts", "segment_001.ts"),
            _HLS_CONTENT_TYPE,
        ),
        "/live/segment_000.ts": (200, b"abc", _TS_CONTENT_TYPE),
        "/live/segment_001.ts": (200, b"toolarge", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = _build_loader_source(
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

    _configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_reconnect_attempts=3,
        reconnect_backoff_sec=0.5,
        sleep=record_sleep,
    )

    routes = {
        "/live/index.m3u8": (
            200,
            _media_playlist(0, "segment_000.ts", endlist=False),
            _HLS_CONTENT_TYPE,
        ),
        **_segment_routes(0),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = _build_loader_source(base_url, session_id)
        original_urlopen = stream_loader_http_hls.urlopen
        playlist_fetch_count = 0

        def flaky_urlopen(request, timeout=None):
            nonlocal playlist_fetch_count
            request_url = request.full_url if hasattr(request, "full_url") else request.get_full_url()
            if request_url.endswith("/live/index.m3u8"):
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


def test_http_hls_loader_restart_after_idle_budget_completion_preserves_persisted_dedup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A restart after idle-budget completion should resume from persisted dedup state."""
    session_id = "session-http-idle-restart-dedup"
    _configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_idle_playlist_polls=1,
        sleep=lambda seconds: None,
    )

    routes = {
        "/live/index.m3u8": [
            (
                200,
                _media_playlist(900, "segment_900.ts", "segment_901.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                _media_playlist(901, "segment_901.ts", "segment_902.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                _media_playlist(902, "segment_902.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                _media_playlist(902, "segment_902.ts", "segment_903.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                _media_playlist(903, "segment_903.ts", "segment_904.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                _media_playlist(904, "segment_904.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
        ],
        **_segment_routes(*range(900, 905)),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")

        first_loader = HttpHlsApiStreamLoader(session_id)
        first_indexes: list[int] = []
        for slice_ in iter_api_stream_slices(first_loader, source):
            assert slice_.window_index is not None
            first_indexes.append(slice_.window_index)
            slice_.file_path.unlink()
        first_loader.close()

        second_loader = HttpHlsApiStreamLoader(session_id)
        second_indexes: list[int] = []
        for slice_ in iter_api_stream_slices(second_loader, source):
            assert slice_.window_index is not None
            second_indexes.append(slice_.window_index)
            slice_.file_path.unlink()
        second_loader.close()

    assert first_indexes == [900, 901, 902]
    assert second_indexes == [903, 904]
    assert read_api_stream_seen_chunk_keys(session_id) == {
        (source.input_path, index, f"segment_{index}.ts")
        for index in range(900, 905)
    }
    cleanup_api_stream_temp_session_dir(session_id)


def test_http_hls_loader_restart_after_partial_progress_terminal_failure_preserves_dedup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A restart after partial progress and a later terminal failure should resume cleanly."""
    session_id = "session-http-restart-after-terminal-failure"
    _configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_idle_playlist_polls=1,
        sleep=lambda seconds: None,
    )

    routes = {
        "/live/index.m3u8": [
            (
                200,
                _media_playlist(1000, "segment_1000.ts", "segment_1001.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                _media_playlist(1001, "segment_1001.ts", "segment_1002.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                _media_playlist(1002, "segment_1002.ts", "segment_1003.ts"),
                _HLS_CONTENT_TYPE,
            ),
        ],
        "/live/segment_1000.ts": (200, b"1000", _TS_CONTENT_TYPE),
        "/live/segment_1001.ts": (200, b"1001", _TS_CONTENT_TYPE),
        "/live/segment_1002.ts": [
            (403, b"forbidden", "text/plain"),
            (200, b"1002", _TS_CONTENT_TYPE),
        ],
        "/live/segment_1003.ts": (200, b"1003", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        temp_dir = build_api_stream_temp_session_dir(session_id)

        first_loader = HttpHlsApiStreamLoader(session_id)
        first_iterator = iter_api_stream_slices(first_loader, source)
        first_indexes: list[int] = []
        with pytest.raises(ValueError, match="upstream returned HTTP 403"):
            while True:
                slice_ = next(first_iterator)
                assert slice_.window_index is not None
                first_indexes.append(slice_.window_index)
                slice_.file_path.unlink()
        assert first_indexes == [1000, 1001]
        assert not any(temp_dir.iterdir())

        second_loader = HttpHlsApiStreamLoader(session_id)
        second_indexes: list[int] = []
        for slice_ in iter_api_stream_slices(second_loader, source):
            assert slice_.window_index is not None
            second_indexes.append(slice_.window_index)
            slice_.file_path.unlink()
        second_loader.close()

    assert second_indexes == [1002, 1003]
    assert read_api_stream_seen_chunk_keys(session_id) == {
        (source.input_path, index, f"segment_{index}.ts")
        for index in range(1000, 1004)
    }
    cleanup_api_stream_temp_session_dir(session_id)


def test_http_hls_loader_cleans_temp_state_after_reconnect_budget_exhaustion(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Reconnect-budget exhaustion after earlier progress should leave the session temp dir clean."""
    session_id = "session-http-reconnect-budget-cleanup"
    sleep_calls: list[float] = []
    _configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_reconnect_attempts=1,
        reconnect_backoff_sec=0.0,
        sleep=lambda seconds: sleep_calls.append(seconds),
    )

    routes = {
        "/live/index.m3u8": (
            200,
            _media_playlist(0, "segment_000.ts", endlist=False),
            _HLS_CONTENT_TYPE,
        ),
        **_segment_routes(0),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = _build_loader_source(base_url, session_id)
        temp_dir = build_api_stream_temp_session_dir(session_id)
        original_urlopen = stream_loader_http_hls.urlopen
        playlist_fetch_count = 0

        def flaky_urlopen(request, timeout=None):
            nonlocal playlist_fetch_count
            request_url = request.full_url if hasattr(request, "full_url") else request.get_full_url()
            if request_url.endswith("/live/index.m3u8"):
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


def test_http_hls_loader_enforces_playlist_refresh_limit_after_earlier_progress(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Refresh limits should still fail clearly after the loader has already accepted chunks."""
    session_id = "session-http-refresh-limit-after-progress"
    _configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_playlist_refreshes=1,
        max_idle_playlist_polls=10,
        sleep=lambda seconds: None,
    )

    routes = {
        "/live/index.m3u8": (
            200,
            _media_playlist(1100, "segment_1100.ts", "segment_1101.ts", endlist=False),
            _HLS_CONTENT_TYPE,
        ),
        **_segment_routes(1100, 1101),
    }

    with _serve_local_hls(routes) as base_url:
        loader, source = _build_loader_source(base_url, session_id)
        iterator = iter_api_stream_slices(loader, source)
        collected_indexes: list[int] = []

        first_slice = next(iterator)
        second_slice = next(iterator)
        collected_indexes.extend(
            [
                first_slice.window_index,
                second_slice.window_index,
            ]
        )
        first_slice.file_path.unlink()
        second_slice.file_path.unlink()

        with pytest.raises(ValueError, match="playlist refresh limit exceeded"):
            next(iterator)

    assert collected_indexes == [1100, 1101]
    assert read_api_stream_seen_chunk_keys(session_id) == {
        (source.input_path, index, f"segment_{index}.ts")
        for index in range(1100, 1102)
    }
    cleanup_api_stream_temp_session_dir(session_id)


def test_http_hls_loader_restart_after_runtime_limit_preserves_persisted_dedup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A restart after runtime exhaustion should resume from persisted dedup instead of replaying chunks."""
    session_id = "session-http-runtime-restart-dedup"
    first_ticks = iter([0.0, 0.5, 1.0, 6.1])
    _configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_idle_playlist_polls=10,
        max_session_runtime_sec=5.0,
        sleep=lambda seconds: None,
        monotonic=lambda: next(first_ticks),
    )

    routes = {
        "/live/index.m3u8": [
            (
                200,
                _media_playlist(1200, "segment_1200.ts", "segment_1201.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                _media_playlist(1201, "segment_1201.ts", "segment_1202.ts", "segment_1203.ts"),
                _HLS_CONTENT_TYPE,
            ),
        ],
        **_segment_routes(1200, 1201, 1202, 1203),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")

        first_loader = HttpHlsApiStreamLoader(session_id)
        first_iterator = iter_api_stream_slices(first_loader, source)
        first_indexes: list[int] = []

        with pytest.raises(ValueError, match="session runtime exceeded max duration"):
            while True:
                slice_ = next(first_iterator)
                assert slice_.window_index is not None
                first_indexes.append(slice_.window_index)
                slice_.file_path.unlink()

        second_ticks = iter([0.0, 0.5, 1.0, 1.5])
        monkeypatch.setattr(stream_loader_http_hls.time, "monotonic", lambda: next(second_ticks))

        second_loader = HttpHlsApiStreamLoader(session_id)
        second_indexes: list[int] = []
        for slice_ in iter_api_stream_slices(second_loader, source):
            assert slice_.window_index is not None
            second_indexes.append(slice_.window_index)
            slice_.file_path.unlink()
        second_loader.close()

    assert first_indexes == [1200, 1201]
    assert second_indexes == [1202, 1203]
    assert read_api_stream_seen_chunk_keys(session_id) == {
        (source.input_path, index, f"segment_{index}.ts")
        for index in range(1200, 1204)
    }
    cleanup_api_stream_temp_session_dir(session_id)
