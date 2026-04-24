"""Tests for core HTTP/HLS behavior in `stream_loader_http_hls`.

These cases cover the concrete loader's ordinary fetch, variant-selection, and
playlist progression semantics without mixing in reconnect-budget or limit
behavior. They complement:

- `test_stream_loader_contracts.py` for facade/contract-level checks
- `test_stream_loader_http_hls_reconnect.py` for recovery behavior
- `test_stream_loader_http_hls_limits.py` for hard-limit and cleanup behavior
"""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

import config
import stream_loader
import stream_loader_http_hls
from session_io import request_session_cancel
from stream_loader import (
    HttpHlsApiStreamLoader,
    build_api_stream_source_contract,
    cleanup_api_stream_temp_session_dir,
    collect_api_stream_slices,
    iter_api_stream_slices,
)
from tests.stream_loader_http_hls_test_support import _serve_local_hls


def _configure_http_hls_loader_test(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    poll_interval_sec: float = 0.0,
    max_idle_playlist_polls: int | None = None,
    sleep=None,
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
    if sleep is not None:
        monkeypatch.setattr(stream_loader_http_hls.time, "sleep", sleep)


def _playlist(*lines: str) -> str:
    return "\n".join(["#EXTM3U", *lines])


def _media_playlist(
    media_sequence: int,
    *segments: str,
    target_duration: int = 1,
    endlist: bool = True,
) -> str:
    lines = [
        "#EXT-X-TARGETDURATION:{target_duration}".format(
            target_duration=target_duration
        ),
        f"#EXT-X-MEDIA-SEQUENCE:{media_sequence}",
    ]
    for segment in segments:
        lines.extend(["#EXTINF:1.0,", segment])
    if endlist:
        lines.append("#EXT-X-ENDLIST")
    return _playlist(*lines)


def _collect_http_hls_slices(base_url: str, playlist_path: str, session_id: str):
    source = build_api_stream_source_contract(f"{base_url}{playlist_path}")
    loader = HttpHlsApiStreamLoader(session_id)
    return collect_api_stream_slices(loader, source)


@contextmanager
def _serve_dynamic_local_hls(build_routes):
    route_counts: dict[str, int] = {}
    routes: dict[str, list[object]] = {}

    def next_response(path: str) -> tuple[int, str | bytes, str, dict[str, str]]:
        sequence = routes.get(path)
        if not sequence:
            return (404, "not found", "text/plain", {})
        index = min(route_counts[path], len(sequence) - 1)
        route_counts[path] += 1
        response = sequence[index]
        assert isinstance(response, tuple)
        if len(response) == 3:
            status, body, content_type = response
            return status, body, content_type, {}
        status, body, content_type, headers = response
        return status, body, content_type, headers

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            status, body, content_type, headers = next_response(self.path)
            payload = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            for header_name, header_value in headers.items():
                self.send_header(header_name, header_value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    base_url = f"http://127.0.0.1:{server.server_port}"
    built_routes = build_routes(base_url)
    routes.update(
        {
            path: (list(spec) if isinstance(spec, list) else [spec])
            for path, spec in built_routes.items()
        }
    )
    route_counts.update({path: 0 for path in built_routes})
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield base_url
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


# Playlist semantics

def test_http_hls_loader_collects_media_playlist_segments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The concrete loader should fetch a media playlist and materialize segment slices."""
    _configure_http_hls_loader_test(monkeypatch, tmp_path)

    playlist_text = _media_playlist(0, "segment_000.ts", "segment_001.ts")
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_000.ts": (200, b"ts-000", "video/mp2t"),
        "/live/segment_001.ts": (200, b"ts-001", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        slices = _collect_http_hls_slices(base_url, "/live/index.m3u8", "session-http-media")

    assert [slice_.source_name for slice_ in slices] == ["segment_000.ts", "segment_001.ts"]
    assert [slice_.window_index for slice_ in slices] == [0, 1]
    assert all(slice_.file_path.exists() for slice_ in slices)
    cleanup_api_stream_temp_session_dir("session-http-media")


def test_http_hls_loader_selects_first_master_playlist_variant(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The first real loader should apply the explicit first-variant master-playlist policy."""
    _configure_http_hls_loader_test(monkeypatch, tmp_path)

    master_text = _playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360',
        "low/index.m3u8",
        '#EXT-X-STREAM-INF:BANDWIDTH=1200000,RESOLUTION=1280x720',
        "high/index.m3u8",
    )
    media_text = _media_playlist(10, "segment_low_010.ts")
    routes = {
        "/master.m3u8": (200, master_text, "application/vnd.apple.mpegurl"),
        "/low/index.m3u8": (200, media_text, "application/vnd.apple.mpegurl"),
        "/high/index.m3u8": (
            200,
            media_text.replace("segment_low_010.ts", "segment_high_010.ts"),
            "application/vnd.apple.mpegurl",
        ),
        "/low/segment_low_010.ts": (200, b"low", "video/mp2t"),
        "/high/segment_high_010.ts": (200, b"high", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        slices = _collect_http_hls_slices(base_url, "/master.m3u8", "session-http-master")

    assert [slice_.source_name for slice_ in slices] == ["segment_low_010.ts"]
    assert [slice_.window_index for slice_ in slices] == [10]
    cleanup_api_stream_temp_session_dir("session-http-master")


def test_http_hls_loader_uses_first_master_variant_even_when_it_is_weak_but_playable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """First-variant selection should remain predictable even for a low-quality playable stream."""
    _configure_http_hls_loader_test(monkeypatch, tmp_path)

    master_text = _playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=180000,RESOLUTION=320x180',
        "weak/index.m3u8",
        '#EXT-X-STREAM-INF:BANDWIDTH=2400000,RESOLUTION=1920x1080',
        "strong/index.m3u8",
    )
    weak_media = _playlist(
        "#EXT-X-TARGETDURATION:2",
        "#EXT-X-MEDIA-SEQUENCE:20",
        "#EXTINF:2.0,",
        "segment_weak_020.ts",
        "#EXT-X-ENDLIST",
    )
    strong_media = weak_media.replace("segment_weak_020.ts", "segment_strong_020.ts")
    routes = {
        "/master.m3u8": (200, master_text, "application/vnd.apple.mpegurl"),
        "/weak/index.m3u8": (200, weak_media, "application/vnd.apple.mpegurl"),
        "/strong/index.m3u8": (200, strong_media, "application/vnd.apple.mpegurl"),
        "/weak/segment_weak_020.ts": (200, b"weak", "video/mp2t"),
        "/strong/segment_strong_020.ts": (200, b"strong", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        slices = _collect_http_hls_slices(
            base_url,
            "/master.m3u8",
            "session-http-master-weak-first",
        )

    assert [slice_.source_name for slice_ in slices] == ["segment_weak_020.ts"]
    cleanup_api_stream_temp_session_dir("session-http-master-weak-first")


def test_http_hls_loader_resolves_nested_master_playlist_variants(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Nested master playlists should still resolve to a reachable media playlist."""
    _configure_http_hls_loader_test(monkeypatch, tmp_path)

    outer_master = _playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360',
        "variant/master.m3u8",
    )
    inner_master = _playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=750000,RESOLUTION=960x540',
        "media/index.m3u8",
    )
    media_playlist = _media_playlist(12, "segment_012.ts")
    routes = {
        "/master.m3u8": (200, outer_master, "application/vnd.apple.mpegurl"),
        "/variant/master.m3u8": (200, inner_master, "application/vnd.apple.mpegurl"),
        "/variant/media/index.m3u8": (200, media_playlist, "application/vnd.apple.mpegurl"),
        "/variant/media/segment_012.ts": (200, b"012", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        slices = _collect_http_hls_slices(
            base_url,
            "/master.m3u8",
            "session-http-nested-master",
        )

    assert [slice_.window_index for slice_ in slices] == [12]
    cleanup_api_stream_temp_session_dir("session-http-nested-master")


def test_http_hls_loader_ignores_malformed_master_variant_entries_and_uses_first_valid_one(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A malformed master entry without a URI should not prevent using the next valid variant."""
    _configure_http_hls_loader_test(monkeypatch, tmp_path)

    master_text = _playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=300000,RESOLUTION=426x240',
        "# malformed first variant entry has no URI",
        '#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=960x540',
        "valid/index.m3u8",
    )
    media_text = _media_playlist(15, "segment_valid_015.ts")
    routes = {
        "/master.m3u8": (200, master_text, "application/vnd.apple.mpegurl"),
        "/valid/index.m3u8": (200, media_text, "application/vnd.apple.mpegurl"),
        "/valid/segment_valid_015.ts": (200, b"015", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        slices = _collect_http_hls_slices(
            base_url,
            "/master.m3u8",
            "session-http-master-malformed-entry",
        )

    assert [slice_.window_index for slice_ in slices] == [15]
    assert [slice_.source_name for slice_ in slices] == ["segment_valid_015.ts"]
    cleanup_api_stream_temp_session_dir("session-http-master-malformed-entry")


def test_http_hls_loader_resolves_parent_relative_segment_paths_from_nested_media_playlist(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Segment URIs with .. should resolve relative to the nested media playlist location."""
    _configure_http_hls_loader_test(monkeypatch, tmp_path)

    media_text = _media_playlist(
        50,
        "../segments/segment_050.ts",
        "../segments/segment_051.ts",
    )
    routes = {
        "/nested/live/index.m3u8": (200, media_text, "application/vnd.apple.mpegurl"),
        "/nested/segments/segment_050.ts": (200, b"050", "video/mp2t"),
        "/nested/segments/segment_051.ts": (200, b"051", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        slices = _collect_http_hls_slices(
            base_url,
            "/nested/live/index.m3u8",
            "session-http-parent-relative-segments",
        )

    assert [slice_.source_name for slice_ in slices] == [
        "segment_050.ts",
        "segment_051.ts",
    ]
    assert [slice_.window_index for slice_ in slices] == [50, 51]
    cleanup_api_stream_temp_session_dir("session-http-parent-relative-segments")


def test_http_hls_loader_rejects_master_playlist_without_any_usable_variant_uri(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A master playlist with only malformed variant entries should fail clearly."""
    _configure_http_hls_loader_test(monkeypatch, tmp_path)

    master_text = _playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=300000,RESOLUTION=426x240',
        "# no usable variant URI here",
        '#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=960x540',
        "   ",
    )
    routes = {
        "/master.m3u8": (200, master_text, "application/vnd.apple.mpegurl"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/master.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-master-no-usable-variant")
        with pytest.raises(
            ValueError,
            match="api_stream master playlist requires at least one variant URL",
        ):
            collect_api_stream_slices(loader, source)

    cleanup_api_stream_temp_session_dir("session-http-master-no-usable-variant")


def test_http_hls_loader_follows_variant_redirect_before_resolving_media_playlist(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A master-playlist variant may redirect before it reaches the final media playlist."""
    _configure_http_hls_loader_test(monkeypatch, tmp_path)

    master_text = _playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360',
        "variant/index.m3u8",
    )
    routes = {
        "/master.m3u8": (200, master_text, "application/vnd.apple.mpegurl"),
        "/variant/index.m3u8": (
            302,
            "",
            "text/plain",
            {"Location": "/media/index.m3u8"},
        ),
        "/media/index.m3u8": (
            200,
            _media_playlist(61, "segment_061.ts"),
            "application/vnd.apple.mpegurl",
        ),
        "/media/segment_061.ts": (200, b"061", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        slices = _collect_http_hls_slices(
            base_url,
            "/master.m3u8",
            "session-http-master-variant-redirect",
        )

    assert [slice_.window_index for slice_ in slices] == [61]
    assert [slice_.source_name for slice_ in slices] == ["segment_061.ts"]
    cleanup_api_stream_temp_session_dir("session-http-master-variant-redirect")


# Progression and live-window behavior

def test_http_hls_loader_polls_playlist_and_emits_only_new_segments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Playlist refresh should discover only new segments on later polls."""
    _configure_http_hls_loader_test(
        monkeypatch,
        tmp_path,
        sleep=lambda seconds: None,
    )

    first_playlist = _media_playlist(3, "segment_003.ts", endlist=False)
    second_playlist = _media_playlist(3, "segment_003.ts", "segment_004.ts")
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, second_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_003.ts": (200, b"003", "video/mp2t"),
        "/live/segment_004.ts": (200, b"004", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        slices = _collect_http_hls_slices(base_url, "/live/index.m3u8", "session-http-refresh")

    assert [slice_.window_index for slice_ in slices] == [3, 4]
    assert [slice_.source_name for slice_ in slices] == ["segment_003.ts", "segment_004.ts"]
    cleanup_api_stream_temp_session_dir("session-http-refresh")


def test_http_hls_loader_handles_sliding_window_playlist_histories(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Sliding HLS windows should allow old segments to disappear without duplicating survivors."""
    _configure_http_hls_loader_test(
        monkeypatch,
        tmp_path,
        sleep=lambda seconds: None,
    )

    first_playlist = _media_playlist(
        10,
        "segment_010.ts",
        "segment_011.ts",
        "segment_012.ts",
        endlist=False,
    )
    second_playlist = _media_playlist(12, "segment_012.ts", "segment_013.ts")
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, second_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_010.ts": (200, b"010", "video/mp2t"),
        "/live/segment_011.ts": (200, b"011", "video/mp2t"),
        "/live/segment_012.ts": (200, b"012", "video/mp2t"),
        "/live/segment_013.ts": (200, b"013", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        slices = _collect_http_hls_slices(base_url, "/live/index.m3u8", "session-http-sliding")

    assert [slice_.window_index for slice_ in slices] == [10, 11, 12, 13]
    assert [slice_.source_name for slice_ in slices] == [
        "segment_010.ts",
        "segment_011.ts",
        "segment_012.ts",
        "segment_013.ts",
    ]
    cleanup_api_stream_temp_session_dir("session-http-sliding")


def test_http_hls_loader_handles_longer_sliding_runs_without_replay_cache_growth(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Longer HLS runs should keep replay tracking bounded to the visible window."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader_http_hls.time, "sleep", lambda seconds: None)

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
            (200, playlist_text, "application/vnd.apple.mpegurl")
            for playlist_text in playlists
        ],
    }
    for index in range(300, 308):
        routes[f"/live/segment_{index}.ts"] = (
            200,
            f"{index}".encode("utf-8"),
            "video/mp2t",
        )

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
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

    cleanup_api_stream_temp_session_dir("session-http-long-run")


def test_http_hls_loader_resumes_after_window_advance_when_missed_segments_are_gone(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """When the live window advances past missed segments, the loader should resume from the next visible segment."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader_http_hls.time, "sleep", lambda seconds: None)

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:40",
            "#EXTINF:1.0,",
            "segment_040.ts",
        ]
    )
    second_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:43",
            "#EXTINF:1.0,",
            "segment_043.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, second_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_040.ts": (200, b"040", "video/mp2t"),
        "/live/segment_043.ts": (200, b"043", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-window-advance")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [40, 43]
    assert [slice_.source_name for slice_ in slices] == ["segment_040.ts", "segment_043.ts"]
    cleanup_api_stream_temp_session_dir("session-http-window-advance")


def test_http_hls_loader_tolerates_incomplete_refresh_and_keeps_progressing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A dangling EXTINF without a URI should be ignored as an incomplete live refresh."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(stream_loader_http_hls.time, "sleep", lambda seconds: None)

    first_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:60",
            "#EXTINF:1.0,",
            "segment_060.ts",
        ]
    )
    incomplete_refresh = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:60",
            "#EXTINF:1.0,",
        ]
    )
    final_playlist = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:60",
            "#EXTINF:1.0,",
            "segment_060.ts",
            "#EXTINF:1.0,",
            "segment_061.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, incomplete_refresh, "application/vnd.apple.mpegurl"),
            (200, final_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_060.ts": (200, b"060", "video/mp2t"),
        "/live/segment_061.ts": (200, b"061", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-incomplete-refresh")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [60, 61]
    cleanup_api_stream_temp_session_dir("session-http-incomplete-refresh")


def test_http_hls_loader_tolerates_media_playlist_missing_target_duration_tag(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A media playlist missing TARGETDURATION should still progress when EXTINF entries are present."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

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
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_062.ts": (200, b"062", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-missing-target-duration")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [62]
    cleanup_api_stream_temp_session_dir("session-http-missing-target-duration")


def test_http_hls_loader_stops_after_repeated_no_new_live_refreshes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Non-endlist live playlists should stop cleanly after a bounded idle poll budget."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_MAX_IDLE_PLAYLIST_POLLS", 2)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    sleep_calls: list[float] = []
    monkeypatch.setattr(stream_loader_http_hls.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:21",
            "#EXTINF:1.0,",
            "segment_021.ts",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, playlist_text, "application/vnd.apple.mpegurl"),
            (200, playlist_text, "application/vnd.apple.mpegurl"),
            (200, playlist_text, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_021.ts": (200, b"021", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-idle")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [21]
    assert len(sleep_calls) == 2
    cleanup_api_stream_temp_session_dir("session-http-idle")


def test_http_hls_loader_stops_immediately_after_endlist_segments_are_exhausted(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """ENDLIST should stop the live loop without falling back to idle polling."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    sleep_calls: list[float] = []
    monkeypatch.setattr(stream_loader_http_hls.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:80",
            "#EXTINF:1.0,",
            "segment_080.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_080.ts": (200, b"080", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-endlist-stop")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [80]
    assert sleep_calls == []
    cleanup_api_stream_temp_session_dir("session-http-endlist-stop")


def test_http_hls_loader_stops_cleanly_when_cancel_is_requested_during_idle_polling(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A cancel request during idle polling should stop the live loop without hanging."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    sleep_calls: list[float] = []

    def cancel_on_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        request_session_cancel("session-http-cancel-idle")

    monkeypatch.setattr(stream_loader_http_hls.time, "sleep", cancel_on_sleep)

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:81",
            "#EXTINF:1.0,",
            "segment_081.ts",
        ]
    )
    routes = {
        "/live/index.m3u8": [
            (200, playlist_text, "application/vnd.apple.mpegurl"),
            (200, playlist_text, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_081.ts": (200, b"081", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-cancel-idle")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [81]
    assert len(sleep_calls) == 1
    cleanup_api_stream_temp_session_dir("session-http-cancel-idle")


def test_http_hls_loader_prunes_replay_cache_when_playlist_window_slides(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Older replay keys should not grow forever once the visible playlist window advances."""
    _configure_http_hls_loader_test(
        monkeypatch,
        tmp_path,
        sleep=lambda seconds: None,
    )

    first_playlist = _media_playlist(10, "segment_010.ts", "segment_011.ts", endlist=False)
    second_playlist = _media_playlist(12, "segment_012.ts")
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, second_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_010.ts": (200, b"010", "video/mp2t"),
        "/live/segment_011.ts": (200, b"011", "video/mp2t"),
        "/live/segment_012.ts": (200, b"012", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
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

    cleanup_api_stream_temp_session_dir("session-http-cache-prune")


def test_http_hls_loader_adapts_polling_to_target_duration_drift(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Target-duration drift should change the next live refresh wait without breaking loading."""
    sleep_calls: list[float] = []
    _configure_http_hls_loader_test(
        monkeypatch,
        tmp_path,
        poll_interval_sec=2.0,
        max_idle_playlist_polls=3,
        sleep=lambda seconds: sleep_calls.append(seconds),
    )

    first_playlist = _playlist(
        "#EXT-X-TARGETDURATION:4",
        "#EXT-X-MEDIA-SEQUENCE:30",
        "#EXTINF:4.0,",
        "segment_030.ts",
    )
    second_playlist = _playlist(
        "#EXT-X-TARGETDURATION:1",
        "#EXT-X-MEDIA-SEQUENCE:30",
        "#EXTINF:4.0,",
        "segment_030.ts",
    )
    third_playlist = _playlist(
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
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, second_playlist, "application/vnd.apple.mpegurl"),
            (200, third_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_030.ts": (200, b"030", "video/mp2t"),
        "/live/segment_031.ts": (200, b"031", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-drift")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [30, 31]
    assert sleep_calls == [2.0, 1.0]
    cleanup_api_stream_temp_session_dir("session-http-drift")


# Malformed playlist and partial-refresh behavior

def test_http_hls_loader_treats_temporarily_malformed_refresh_as_retryable_noise(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A malformed 200 OK refresh should be skipped so later valid media can still continue."""
    _configure_http_hls_loader_test(
        monkeypatch,
        tmp_path,
        sleep=lambda seconds: None,
    )
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    warning_logs: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        stream_loader.logger,
        "warning",
        lambda message, *args: warning_logs.append((message, args)),
    )

    first_playlist = _media_playlist(90, "segment_090.ts", endlist=False)
    final_playlist = _media_playlist(90, "segment_090.ts", "segment_091.ts")
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, "temporary html error", "text/plain"),
            (200, final_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_090.ts": (200, b"090", "video/mp2t"),
        "/live/segment_091.ts": (200, b"091", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-malformed-refresh")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [90, 91]
    assert any(message == "Retryable api_stream failure [%s]" for message, _ in warning_logs)
    assert any(
        "session_id='session-http-malformed-refresh'" in str(args[0])
        and "reconnect_attempt=1" in str(args[0])
        for message, args in warning_logs
        if message == "Retryable api_stream failure [%s]"
    )
    cleanup_api_stream_temp_session_dir("session-http-malformed-refresh")


def test_http_hls_loader_surfaces_late_terminal_refresh_failure_after_emitting_early_segments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Already accepted segments should still be emitted before a later fatal refresh stops loading."""
    _configure_http_hls_loader_test(
        monkeypatch,
        tmp_path,
        sleep=lambda seconds: None,
    )

    first_playlist = _media_playlist(96, "segment_096.ts", endlist=False)
    fatal_refresh = _playlist(
        '#EXT-X-STREAM-INF:BANDWIDTH=300000,RESOLUTION=426x240',
        "   ",
    )
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, fatal_refresh, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_096.ts": (200, b"096", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
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

    cleanup_api_stream_temp_session_dir("session-http-late-terminal-refresh")


def test_http_hls_loader_treats_invalid_target_duration_tag_as_retryable_refresh_noise(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A refresh with a malformed TARGETDURATION tag should be skipped until a valid playlist appears."""
    _configure_http_hls_loader_test(
        monkeypatch,
        tmp_path,
        sleep=lambda seconds: None,
    )
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)

    first_playlist = _media_playlist(92, "segment_092.ts", endlist=False)
    malformed_refresh = _playlist(
        "#EXT-X-TARGETDURATION:not-a-number",
        "#EXT-X-MEDIA-SEQUENCE:92",
        "#EXTINF:1.0,",
        "segment_092.ts",
    )
    final_playlist = _media_playlist(92, "segment_092.ts", "segment_093.ts")
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, malformed_refresh, "application/vnd.apple.mpegurl"),
            (200, final_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_092.ts": (200, b"092", "video/mp2t"),
        "/live/segment_093.ts": (200, b"093", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-malformed-target-duration")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [92, 93]
    cleanup_api_stream_temp_session_dir("session-http-malformed-target-duration")


def test_http_hls_loader_recovers_from_partial_refresh_missing_segment_uri(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A partial refresh with a dangling EXTINF should recover once the next valid playlist arrives."""
    _configure_http_hls_loader_test(
        monkeypatch,
        tmp_path,
        sleep=lambda seconds: None,
    )

    first_playlist = _media_playlist(94, "segment_094.ts", endlist=False)
    partial_refresh = _playlist(
        "#EXT-X-TARGETDURATION:1",
        "#EXT-X-MEDIA-SEQUENCE:94",
        "#EXTINF:1.0,",
        "segment_094.ts",
        "#EXTINF:1.0,",
    )
    final_playlist = _media_playlist(94, "segment_094.ts", "segment_095.ts")
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, partial_refresh, "application/vnd.apple.mpegurl"),
            (200, final_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_094.ts": (200, b"094", "video/mp2t"),
        "/live/segment_095.ts": (200, b"095", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-partial-refresh-recovery")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [94, 95]
    cleanup_api_stream_temp_session_dir("session-http-partial-refresh-recovery")


def test_http_hls_loader_continues_when_missing_segment_disappears_from_later_window(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A missing segment that falls out of the live window should not block later visible segments."""
    _configure_http_hls_loader_test(
        monkeypatch,
        tmp_path,
        sleep=lambda seconds: None,
    )

    first_playlist = _media_playlist(400, "segment_400.ts", "segment_401.ts", endlist=False)
    advanced_playlist = _media_playlist(402, "segment_402.ts")
    routes = {
        "/live/index.m3u8": [
            (200, first_playlist, "application/vnd.apple.mpegurl"),
            (200, advanced_playlist, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_400.ts": (200, b"400", "video/mp2t"),
        "/live/segment_401.ts": (503, "busy", "text/plain"),
        "/live/segment_402.ts": (200, b"402", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-disappearing-segment")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [400, 402]
    cleanup_api_stream_temp_session_dir("session-http-disappearing-segment")


def test_http_hls_loader_handles_mixed_relative_and_absolute_segment_uris(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A media playlist may mix relative paths with absolute segment URLs."""
    _configure_http_hls_loader_test(monkeypatch, tmp_path)

    def build_routes(base_url: str) -> dict[str, object]:
        playlist_text = _playlist(
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:60",
            "#EXTINF:1.0,",
            "relative_060.ts",
            "#EXTINF:1.0,",
            f"{base_url}/cdn/segment_061.ts",
            "#EXT-X-ENDLIST",
        )
        return {
            "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
            "/live/relative_060.ts": (200, b"060", "video/mp2t"),
            "/cdn/segment_061.ts": (200, b"061", "video/mp2t"),
        }

    with _serve_dynamic_local_hls(build_routes) as base_url:
        slices = _collect_http_hls_slices(
            base_url,
            "/live/index.m3u8",
            "session-http-mixed-absolute-relative",
        )

    assert [slice_.source_name for slice_ in slices] == ["relative_060.ts", "segment_061.ts"]
    assert [slice_.window_index for slice_ in slices] == [60, 61]
    cleanup_api_stream_temp_session_dir("session-http-mixed-absolute-relative")


# Provider and transport edge behavior

def test_http_hls_loader_accepts_uppercase_playlist_and_segment_suffixes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Uppercase playlist paths and segment suffixes should still load cleanly."""
    _configure_http_hls_loader_test(monkeypatch, tmp_path)

    playlist_text = _media_playlist(210, "SEGMENT_210.TS")
    routes = {
        "/LIVE/INDEX.M3U8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/LIVE/SEGMENT_210.TS": (200, b"210", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/LIVE/INDEX.M3U8")
        loader = HttpHlsApiStreamLoader("session-http-uppercase-suffixes")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.source_name for slice_ in slices] == ["SEGMENT_210.TS"]
    assert [slice_.window_index for slice_ in slices] == [210]
    cleanup_api_stream_temp_session_dir("session-http-uppercase-suffixes")


def test_http_hls_loader_fetches_query_string_segments_while_normalizing_source_names(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Segment fetches may require query strings even though emitted source names stay stable."""
    _configure_http_hls_loader_test(monkeypatch, tmp_path)

    routes = {
        "/live/index.m3u8": (
            200,
            _media_playlist(
                70,
                "segment_070.ts?token=alpha",
                "segment_071.ts?token=beta",
            ),
            "application/vnd.apple.mpegurl",
        ),
        "/live/segment_070.ts?token=alpha": (200, b"070", "video/mp2t"),
        "/live/segment_071.ts?token=beta": (200, b"071", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        slices = _collect_http_hls_slices(
            base_url,
            "/live/index.m3u8",
            "session-http-query-segments",
        )

    assert [slice_.source_name for slice_ in slices] == ["segment_070.ts", "segment_071.ts"]
    assert [slice_.window_index for slice_ in slices] == [70, 71]
    cleanup_api_stream_temp_session_dir("session-http-query-segments")


def test_http_hls_loader_retries_playlist_fetch_before_succeeding(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Retryable playlist failures should be retried inside the loader seam."""
    _configure_http_hls_loader_test(
        monkeypatch,
        tmp_path,
        sleep=lambda seconds: None,
    )
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)

    playlist_text = _media_playlist(0, "segment_000.ts")
    routes = {
        "/live/index.m3u8": [
            (503, "upstream busy", "text/plain"),
            (200, playlist_text, "application/vnd.apple.mpegurl"),
        ],
        "/live/segment_000.ts": (200, b"ok", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-retry")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.source_name for slice_ in slices] == ["segment_000.ts"]
    cleanup_api_stream_temp_session_dir("session-http-retry")


def test_http_hls_loader_retries_playlist_fetch_after_http_429(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """HTTP 429 responses should be treated like retryable provider throttling."""
    _configure_http_hls_loader_test(
        monkeypatch,
        tmp_path,
        sleep=lambda seconds: None,
    )
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)

    routes = {
        "/live/index.m3u8": [
            (429, "slow down", "text/plain"),
            (
                200,
                _media_playlist(0, "segment_000.ts"),
                "application/vnd.apple.mpegurl",
            ),
        ],
        "/live/segment_000.ts": (200, b"ok", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-retry-429")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.source_name for slice_ in slices] == ["segment_000.ts"]
    assert loader.telemetry_snapshot().reconnect_attempt_count == 1
    cleanup_api_stream_temp_session_dir("session-http-retry-429")


def test_http_hls_loader_surfaces_http_403_as_explicit_terminal_provider_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """HTTP 403 stays terminal today and should surface a clear provider-facing reason."""
    _configure_http_hls_loader_test(monkeypatch, tmp_path)

    routes = {
        "/live/index.m3u8": [
            (403, "forbidden", "text/plain"),
        ],
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-403")
        with pytest.raises(ValueError, match="HTTP 403"):
            collect_api_stream_slices(loader, source)

    assert loader.telemetry_snapshot().terminal_failure_reason == "api_stream upstream returned HTTP 403"
    cleanup_api_stream_temp_session_dir("session-http-403")


def test_http_hls_loader_follows_playlist_redirects(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Provider-style playlist redirects should resolve before normal polling begins."""
    _configure_http_hls_loader_test(monkeypatch, tmp_path)

    routes = {
        "/entry.m3u8": (302, "", "text/plain", {"Location": "/live/index.m3u8"}),
        "/live/index.m3u8": (
            200,
            _media_playlist(10, "segment_010.ts"),
            "application/vnd.apple.mpegurl",
        ),
        "/live/segment_010.ts": (200, b"010", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/entry.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-redirect")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [10]
    cleanup_api_stream_temp_session_dir("session-http-redirect")


def test_http_hls_loader_tolerates_playlist_with_odd_content_type(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Some providers serve playlists with generic content types; parsing should stay text-based."""
    _configure_http_hls_loader_test(monkeypatch, tmp_path)

    routes = {
        "/live/index.m3u8": (
            200,
            _media_playlist(12, "segment_012.ts"),
            "text/plain",
        ),
        "/live/segment_012.ts": (200, b"012", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        source = build_api_stream_source_contract(f"{base_url}/live/index.m3u8")
        loader = HttpHlsApiStreamLoader("session-http-odd-content-type")
        slices = collect_api_stream_slices(loader, source)

    assert [slice_.window_index for slice_ in slices] == [12]
    cleanup_api_stream_temp_session_dir("session-http-odd-content-type")
