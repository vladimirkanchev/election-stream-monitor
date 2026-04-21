"""Shared local HTTP HLS server helper for backend test suites.

This module intentionally stays narrow: it only hosts the tiny reusable local
HTTP server used by multiple HLS-oriented test families.
"""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread


@contextmanager
def _serve_local_hls(routes: dict[str, object]):
    route_state = _RouteState(routes)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            status, body, content_type, headers = route_state.next_response(self.path)
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
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


class _RouteState:
    def __init__(self, routes: dict[str, object]) -> None:
        self._routes = {
            path: (list(spec) if isinstance(spec, list) else [spec])
            for path, spec in routes.items()
        }
        self._counts = {path: 0 for path in routes}

    def next_response(
        self, path: str
    ) -> tuple[int, str | bytes, str, dict[str, str]]:
        sequence = self._routes.get(path)
        if not sequence:
            return (404, "not found", "text/plain", {})
        index = min(self._counts[path], len(sequence) - 1)
        self._counts[path] += 1
        response = sequence[index]
        assert isinstance(response, tuple)
        if len(response) == 3:
            status, body, content_type = response
            return status, body, content_type, {}
        status, body, content_type, headers = response
        return status, body, content_type, headers
