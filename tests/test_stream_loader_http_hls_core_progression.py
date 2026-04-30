"""Tests for core HTTP/HLS live progression and window behavior."""

from pathlib import Path

from session_io import request_session_cancel
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
    no_sleep,
    playlist,
)
from tests.local_hls_test_support import _serve_local_hls


def test_http_hls_loader_polls_playlist_and_emits_only_new_segments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Playlist refresh should discover only new segments on later polls."""
    configure_http_hls_loader_test(monkeypatch, tmp_path, sleep=no_sleep)

    first_playlist = media_playlist(3, "segment_003.ts", endlist=False)
    second_playlist = media_playlist(3, "segment_003.ts", "segment_004.ts")
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, _HLS_CONTENT_TYPE),
            (200, second_playlist, _HLS_CONTENT_TYPE),
        ],
        "/live/segment_003.ts": (200, b"003", _TS_CONTENT_TYPE),
        "/live/segment_004.ts": (200, b"004", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        slices = collect_http_hls_slices(base_url, "/live/index.m3u8", "session-http-refresh")

    assert_slice_identity(
        slices,
        source_names=["segment_003.ts", "segment_004.ts"],
        window_indexes=[3, 4],
    )
    cleanup_http_hls_session("session-http-refresh")


def test_http_hls_loader_handles_sliding_window_playlist_histories(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Sliding HLS windows should allow old segments to disappear without duplicating survivors."""
    configure_http_hls_loader_test(monkeypatch, tmp_path, sleep=no_sleep)

    first_playlist = media_playlist(
        10,
        "segment_010.ts",
        "segment_011.ts",
        "segment_012.ts",
        endlist=False,
    )
    second_playlist = media_playlist(12, "segment_012.ts", "segment_013.ts")
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, _HLS_CONTENT_TYPE),
            (200, second_playlist, _HLS_CONTENT_TYPE),
        ],
        "/live/segment_010.ts": (200, b"010", _TS_CONTENT_TYPE),
        "/live/segment_011.ts": (200, b"011", _TS_CONTENT_TYPE),
        "/live/segment_012.ts": (200, b"012", _TS_CONTENT_TYPE),
        "/live/segment_013.ts": (200, b"013", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        slices = collect_http_hls_slices(base_url, "/live/index.m3u8", "session-http-sliding")

    assert_slice_identity(
        slices,
        source_names=[
            "segment_010.ts",
            "segment_011.ts",
            "segment_012.ts",
            "segment_013.ts",
        ],
        window_indexes=[10, 11, 12, 13],
    )
    cleanup_http_hls_session("session-http-sliding")


def test_http_hls_loader_handles_longer_sliding_runs_without_replay_cache_growth(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Longer HLS runs should keep replay tracking bounded to the visible window."""
    configure_http_hls_loader_test(monkeypatch, tmp_path, sleep=no_sleep)

    playlist_specs = [
        (300, 301, False),
        (301, 302, False),
        (302, 303, False),
        (303, 304, False),
        (304, 305, False),
        (305, 306, False),
        (306, 307, True),
    ]
    playlists = []
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
        playlists.append("\n".join(lines))

    routes: dict[str, object] = {
        "/live/index.m3u8": [
            (200, playlist_text, _HLS_CONTENT_TYPE)
            for playlist_text in playlists
        ],
    }
    for index in range(300, 308):
        routes[f"/live/segment_{index}.ts"] = (
            200,
            f"{index}".encode("utf-8"),
            _TS_CONTENT_TYPE,
        )

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-long-run")
        loader.connect(source)
        try:
            slices = list(loader.iter_slices())
            assert [slice_.window_index for slice_ in slices] == list(range(300, 308))
            assert loader._state.emitted_segment_keys == {
                (306, "segment_306.ts"),
                (307, "segment_307.ts"),
            }
        finally:
            loader.close()

    cleanup_http_hls_session("session-http-long-run")


def test_http_hls_loader_resumes_after_window_advance_when_missed_segments_are_gone(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """When the live window advances past missed segments, the loader should resume from the next visible segment."""
    configure_http_hls_loader_test(monkeypatch, tmp_path, sleep=no_sleep)

    first_playlist = media_playlist(40, "segment_040.ts", endlist=False)
    second_playlist = media_playlist(43, "segment_043.ts")
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, _HLS_CONTENT_TYPE),
            (200, second_playlist, _HLS_CONTENT_TYPE),
        ],
        "/live/segment_040.ts": (200, b"040", _TS_CONTENT_TYPE),
        "/live/segment_043.ts": (200, b"043", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-window-advance")
        slices = collect_api_stream_slices(loader, source)

    assert_slice_identity(
        slices,
        source_names=["segment_040.ts", "segment_043.ts"],
        window_indexes=[40, 43],
    )
    cleanup_http_hls_session("session-http-window-advance")


def test_http_hls_loader_tolerates_incomplete_refresh_and_keeps_progressing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A dangling EXTINF without a URI should be ignored as an incomplete live refresh."""
    configure_http_hls_loader_test(monkeypatch, tmp_path, sleep=no_sleep)

    first_playlist = media_playlist(60, "segment_060.ts", endlist=False)
    incomplete_refresh = playlist(
        "#EXT-X-TARGETDURATION:1",
        "#EXT-X-MEDIA-SEQUENCE:60",
        "#EXTINF:1.0,",
    )
    final_playlist = media_playlist(60, "segment_060.ts", "segment_061.ts")
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, _HLS_CONTENT_TYPE),
            (200, incomplete_refresh, _HLS_CONTENT_TYPE),
            (200, final_playlist, _HLS_CONTENT_TYPE),
        ],
        "/live/segment_060.ts": (200, b"060", _TS_CONTENT_TYPE),
        "/live/segment_061.ts": (200, b"061", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-incomplete-refresh")
        slices = collect_api_stream_slices(loader, source)

    assert_slice_identity(slices, window_indexes=[60, 61])
    cleanup_http_hls_session("session-http-incomplete-refresh")


def test_http_hls_loader_tolerates_media_playlist_missing_target_duration_tag(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A media playlist missing TARGETDURATION should still progress when EXTINF entries are present."""
    configure_http_hls_loader_test(monkeypatch, tmp_path)

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-MEDIA-SEQUENCE:62",
            "#EXTINF:1.0,",
            "segment_062.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, _HLS_CONTENT_TYPE),
        "/live/segment_062.ts": (200, b"062", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-missing-target-duration")
        slices = collect_api_stream_slices(loader, source)

    assert_slice_identity(slices, window_indexes=[62])
    cleanup_http_hls_session("session-http-missing-target-duration")


def test_http_hls_loader_stops_after_repeated_no_new_live_refreshes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Non-endlist live playlists should stop cleanly after a bounded idle poll budget."""
    sleep_calls: list[float] = []
    configure_http_hls_loader_test(
        monkeypatch,
        tmp_path,
        max_idle_playlist_polls=2,
        sleep=lambda seconds: sleep_calls.append(seconds),
    )

    playlist_text = media_playlist(21, "segment_021.ts", endlist=False)
    routes = {
        "/live/index.m3u8": [
            (200, playlist_text, _HLS_CONTENT_TYPE),
            (200, playlist_text, _HLS_CONTENT_TYPE),
            (200, playlist_text, _HLS_CONTENT_TYPE),
        ],
        "/live/segment_021.ts": (200, b"021", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-idle")
        slices = collect_api_stream_slices(loader, source)

    assert_slice_identity(slices, window_indexes=[21])
    assert len(sleep_calls) == 2
    cleanup_http_hls_session("session-http-idle")


def test_http_hls_loader_stops_immediately_after_endlist_segments_are_exhausted(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """ENDLIST should stop the live loop without falling back to idle polling."""
    sleep_calls: list[float] = []
    configure_http_hls_loader_test(
        monkeypatch,
        tmp_path,
        sleep=lambda seconds: sleep_calls.append(seconds),
    )

    playlist_text = media_playlist(80, "segment_080.ts")
    routes = {
        "/live/index.m3u8": (200, playlist_text, _HLS_CONTENT_TYPE),
        "/live/segment_080.ts": (200, b"080", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-endlist-stop")
        slices = collect_api_stream_slices(loader, source)

    assert_slice_identity(slices, window_indexes=[80])
    assert sleep_calls == []
    cleanup_http_hls_session("session-http-endlist-stop")


def test_http_hls_loader_stops_cleanly_when_cancel_is_requested_during_idle_polling(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A cancel request during idle polling should stop the live loop without hanging."""
    sleep_calls: list[float] = []

    def cancel_on_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        request_session_cancel("session-http-cancel-idle")

    configure_http_hls_loader_test(monkeypatch, tmp_path, sleep=cancel_on_sleep)

    playlist_text = media_playlist(81, "segment_081.ts", endlist=False)
    routes = {
        "/live/index.m3u8": [
            (200, playlist_text, _HLS_CONTENT_TYPE),
            (200, playlist_text, _HLS_CONTENT_TYPE),
        ],
        "/live/segment_081.ts": (200, b"081", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-cancel-idle")
        slices = collect_api_stream_slices(loader, source)

    assert_slice_identity(slices, window_indexes=[81])
    assert len(sleep_calls) == 1
    cleanup_http_hls_session("session-http-cancel-idle")


def test_http_hls_loader_prunes_replay_cache_when_playlist_window_slides(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Older replay keys should not grow forever once the visible playlist window advances."""
    configure_http_hls_loader_test(monkeypatch, tmp_path, sleep=no_sleep)

    first_playlist = media_playlist(10, "segment_010.ts", "segment_011.ts", endlist=False)
    second_playlist = media_playlist(12, "segment_012.ts")
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, _HLS_CONTENT_TYPE),
            (200, second_playlist, _HLS_CONTENT_TYPE),
        ],
        "/live/segment_010.ts": (200, b"010", _TS_CONTENT_TYPE),
        "/live/segment_011.ts": (200, b"011", _TS_CONTENT_TYPE),
        "/live/segment_012.ts": (200, b"012", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-cache-prune")
        loader.connect(source)
        iterator = loader.iter_slices()

        first = next(iterator)
        second = next(iterator)
        third = next(iterator)

        assert [first.window_index, second.window_index, third.window_index] == [10, 11, 12]
        assert (10, "segment_010.ts") not in loader._state.emitted_segment_keys
        assert (11, "segment_011.ts") not in loader._state.emitted_segment_keys
        assert (12, "segment_012.ts") in loader._state.emitted_segment_keys
        loader.close()

    cleanup_http_hls_session("session-http-cache-prune")


def test_http_hls_loader_adapts_polling_to_target_duration_drift(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Target-duration drift should change the next live refresh wait without breaking loading."""
    sleep_calls: list[float] = []
    configure_http_hls_loader_test(
        monkeypatch,
        tmp_path,
        poll_interval_sec=2.0,
        max_idle_playlist_polls=3,
        sleep=lambda seconds: sleep_calls.append(seconds),
    )

    first_playlist = playlist(
        "#EXT-X-TARGETDURATION:4",
        "#EXT-X-MEDIA-SEQUENCE:30",
        "#EXTINF:4.0,",
        "segment_030.ts",
    )
    second_playlist = playlist(
        "#EXT-X-TARGETDURATION:1",
        "#EXT-X-MEDIA-SEQUENCE:30",
        "#EXTINF:4.0,",
        "segment_030.ts",
    )
    third_playlist = playlist(
        "#EXT-X-TARGETDURATION:1",
        "#EXT-X-MEDIA-SEQUENCE:30",
        "#EXTINF:4.0,",
        "segment_030.ts",
        "#EXTINF:1.0,",
        "segment_031.ts",
        "#EXT-X-ENDLIST",
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, _HLS_CONTENT_TYPE),
            (200, second_playlist, _HLS_CONTENT_TYPE),
            (200, third_playlist, _HLS_CONTENT_TYPE),
        ],
        "/live/segment_030.ts": (200, b"030", _TS_CONTENT_TYPE),
        "/live/segment_031.ts": (200, b"031", _TS_CONTENT_TYPE),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_http_hls_source(base_url, "/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-drift")
        slices = collect_api_stream_slices(loader, source)

    assert_slice_identity(slices, window_indexes=[30, 31])
    assert sleep_calls == [2.0, 1.0]
    cleanup_http_hls_session("session-http-drift")
