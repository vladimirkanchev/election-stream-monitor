"""Focused HTTP/HLS loader soak, restart, and dedup-resume behavior tests."""

from pathlib import Path

import pytest

import stream_loader_http_hls
from session_io import read_api_stream_seen_chunk_keys
from stream_loader import (
    HttpHlsApiStreamLoader,
    build_api_stream_temp_session_dir,
    cleanup_api_stream_temp_session_dir,
    iter_api_stream_slices,
)
from tests.http_hls_limits_test_support import (
    configure_http_hls_limits_test,
    seen_segment_keys,
    segment_routes,
)
from tests.http_hls_test_support import (
    _HLS_CONTENT_TYPE,
    _TS_CONTENT_TYPE,
    build_http_hls_source,
    media_playlist,
    no_sleep,
)
from tests.local_hls_test_support import _serve_local_hls


def test_http_hls_loader_semi_soak_run_keeps_temp_cleanup_and_dedup_stable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A longer local HLS run should stay bounded in temp files, dedup state, and idle shutdown."""
    sleep_calls: list[float] = []
    configure_http_hls_limits_test(
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
            media_playlist(first_index, f"segment_{first_index}.ts", f"segment_{second_index}.ts", endlist=False),
            _HLS_CONTENT_TYPE,
        )
        for first_index, second_index in playlist_specs
    ]

    routes: dict[str, object] = {
        "/live/index.m3u8": playlist_responses,
        **segment_routes(*range(600, 612)),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-semi-soak")
        temp_dir = build_api_stream_temp_session_dir("session-http-semi-soak")
        collected_indexes: list[int] = []

        for slice_ in iter_api_stream_slices(loader, source):
            assert slice_.window_index is not None
            collected_indexes.append(slice_.window_index)
            slice_.file_path.unlink()

        assert collected_indexes == list(range(600, 612))
        assert len(collected_indexes) == len(set(collected_indexes))
        assert read_api_stream_seen_chunk_keys("session-http-semi-soak") == seen_segment_keys(
            source.input_path,
            *range(600, 612),
        )
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
    configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_idle_playlist_polls=1,
        sleep=no_sleep,
    )

    routes = {
        "/live/index.m3u8": [
            (
                200,
                media_playlist(700, "segment_700.ts", "segment_701.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                media_playlist(701, "segment_701.ts", "segment_702.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                media_playlist(702, "segment_702.ts", "segment_703.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                media_playlist(703, "segment_703.ts", "segment_704.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                media_playlist(703, "segment_703.ts", "segment_704.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
        ],
        **segment_routes(*range(700, 705)),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
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
        assert read_api_stream_seen_chunk_keys("session-http-semi-soak-restart") == seen_segment_keys(
            source.input_path,
            *range(700, 703),
        )

        second_loader = HttpHlsApiStreamLoader("session-http-semi-soak-restart")
        second_indexes: list[int] = []
        for slice_ in iter_api_stream_slices(second_loader, source):
            assert slice_.window_index is not None
            second_indexes.append(slice_.window_index)
            slice_.file_path.unlink()
        second_loader.close()

        assert second_indexes == [703, 704]
        assert not any(temp_dir.iterdir())
        assert read_api_stream_seen_chunk_keys("session-http-semi-soak-restart") == seen_segment_keys(
            source.input_path,
            *range(700, 705),
        )

    cleanup_api_stream_temp_session_dir("session-http-semi-soak-restart")


def test_http_hls_loader_restart_after_idle_budget_completion_preserves_persisted_dedup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A restart after idle-budget completion should resume from persisted dedup state."""
    session_id = "session-http-idle-restart-dedup"
    configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_idle_playlist_polls=1,
        sleep=no_sleep,
    )

    routes = {
        "/live/index.m3u8": [
            (
                200,
                media_playlist(900, "segment_900.ts", "segment_901.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                media_playlist(901, "segment_901.ts", "segment_902.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                media_playlist(902, "segment_902.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                media_playlist(902, "segment_902.ts", "segment_903.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                media_playlist(903, "segment_903.ts", "segment_904.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                media_playlist(904, "segment_904.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
        ],
        **segment_routes(*range(900, 905)),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")

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
    assert read_api_stream_seen_chunk_keys(session_id) == seen_segment_keys(
        source.input_path,
        *range(900, 905),
    )
    cleanup_api_stream_temp_session_dir(session_id)


def test_http_hls_loader_restart_after_partial_progress_terminal_failure_preserves_dedup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A restart after partial progress and a later terminal failure should resume cleanly."""
    session_id = "session-http-restart-after-terminal-failure"
    configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_idle_playlist_polls=1,
        sleep=no_sleep,
    )

    routes = {
        "/live/index.m3u8": [
            (
                200,
                media_playlist(1000, "segment_1000.ts", "segment_1001.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                media_playlist(1001, "segment_1001.ts", "segment_1002.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                media_playlist(1002, "segment_1002.ts", "segment_1003.ts"),
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
        source = build_http_hls_source(base_url, "/live/index.m3u8")
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
    assert read_api_stream_seen_chunk_keys(session_id) == seen_segment_keys(
        source.input_path,
        *range(1000, 1004),
    )
    cleanup_api_stream_temp_session_dir(session_id)


def test_http_hls_loader_restart_after_runtime_limit_preserves_persisted_dedup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A restart after runtime exhaustion should resume from persisted dedup instead of replaying chunks."""
    session_id = "session-http-runtime-restart-dedup"
    first_ticks = iter([0.0, 0.5, 1.0, 6.1])
    configure_http_hls_limits_test(
        monkeypatch,
        tmp_path,
        max_idle_playlist_polls=10,
        max_session_runtime_sec=5.0,
        sleep=no_sleep,
        monotonic=lambda: next(first_ticks),
    )

    routes = {
        "/live/index.m3u8": [
            (
                200,
                media_playlist(1200, "segment_1200.ts", "segment_1201.ts", endlist=False),
                _HLS_CONTENT_TYPE,
            ),
            (
                200,
                media_playlist(1201, "segment_1201.ts", "segment_1202.ts", "segment_1203.ts"),
                _HLS_CONTENT_TYPE,
            ),
        ],
        **segment_routes(1200, 1201, 1202, 1203),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")

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
    assert read_api_stream_seen_chunk_keys(session_id) == seen_segment_keys(
        source.input_path,
        *range(1200, 1204),
    )
    cleanup_api_stream_temp_session_dir(session_id)
