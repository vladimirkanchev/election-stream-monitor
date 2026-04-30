"""Shared support helpers for HTTP/HLS-oriented backend tests.

These helpers keep the larger loader suites focused on scenario intent:
- configure one local loader test environment
- build minimal playlists and segment routes
- collect slices through the public loader seam
- host a tiny dynamic local HTTP server when routes depend on the base URL

This module is intentionally small and procedural. It exists to remove setup
noise from the test files, not to hide test meaning behind a framework.
"""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

import config
import stream_loader_http_hls
from stream_loader import (
    HttpHlsApiStreamLoader,
    build_api_stream_source_contract,
    cleanup_api_stream_temp_session_dir,
    collect_api_stream_slices,
)

_HLS_CONTENT_TYPE = "application/vnd.apple.mpegurl"
_TS_CONTENT_TYPE = "video/mp2t"


def no_sleep(_: float) -> None:
    """Stand-in sleep used by refresh-oriented tests that should not block."""
    return None


def configure_http_hls_loader_test(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    poll_interval_sec: float = 0.0,
    max_idle_playlist_polls: int | None = None,
    sleep=None,
) -> None:
    """Redirect one loader test into isolated temp/session state."""
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


def playlist(*lines: str) -> str:
    """Build a minimal playlist body with the standard HLS header."""
    return "\n".join(["#EXTM3U", *lines])


def media_playlist(
    media_sequence: int,
    *segments: str,
    target_duration: int = 1,
    endlist: bool = True,
) -> str:
    """Build a simple media playlist used by loader behavior tests."""
    lines = [
        f"#EXT-X-TARGETDURATION:{target_duration}",
        f"#EXT-X-MEDIA-SEQUENCE:{media_sequence}",
    ]
    for segment in segments:
        lines.extend(["#EXTINF:1.0,", segment])
    if endlist:
        lines.append("#EXT-X-ENDLIST")
    return playlist(*lines)


def build_http_hls_source(base_url: str, playlist_path: str):
    """Build one validated source contract from a served local playlist path."""
    return build_api_stream_source_contract(f"{base_url}{playlist_path}")


def collect_http_hls_slices(base_url: str, playlist_path: str, session_id: str):
    """Collect all slices for one source URL through the public loader seam."""
    source = build_http_hls_source(base_url, playlist_path)
    loader = HttpHlsApiStreamLoader(session_id)
    return collect_api_stream_slices(loader, source)


def cleanup_http_hls_session(session_id: str) -> None:
    """Remove the temp state owned by one test session id."""
    cleanup_api_stream_temp_session_dir(session_id)


def assert_slice_identity(
    slices,
    *,
    source_names: list[str] | None = None,
    window_indexes: list[int] | None = None,
) -> None:
    """Assert emitted slice identity fields without repeating list comprehensions."""
    if source_names is not None:
        assert [slice_.source_name for slice_ in slices] == source_names
    if window_indexes is not None:
        assert [slice_.window_index for slice_ in slices] == window_indexes


@contextmanager
def serve_dynamic_local_hls(build_routes):
    """Serve dynamic HLS routes when the response bodies depend on the base URL."""
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
