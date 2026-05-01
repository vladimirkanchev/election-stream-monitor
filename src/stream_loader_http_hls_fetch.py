"""Transport helpers for the concrete HTTP/HLS api_stream loader.

Keep this module focused on stateless fetch mechanics:

- outbound request normalization
- bounded response-body reads
- low-level transport exception classification

Loader-owned retry loops and reconnect state updates stay in
`stream_loader_http_hls.py`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request

from stream_loader_contracts import (
    ApiStreamFailure,
    ApiStreamFailureKind,
    _api_stream_loader_error,
    _build_api_stream_failure,
)


_API_STREAM_FETCH_READ_CHUNK_BYTES = 64 * 1024
_API_STREAM_USER_AGENT = "election-stream-monitor/1.0"


class _ReadableResponse(Protocol):
    def read(self, n: int = -1) -> bytes: ...

    def geturl(self) -> str: ...


def _build_api_stream_request(url: str) -> Request:
    """Return the normalized outbound request for one upstream fetch."""
    return Request(url, headers={"User-Agent": _API_STREAM_USER_AGENT})


def _read_api_stream_response_bytes(
    response: _ReadableResponse,
    *,
    max_fetch_bytes: int,
    on_chunk_read: Callable[[], None],
) -> bytes:
    """Read one upstream response body while enforcing byte and cancel budgets."""
    chunks: list[bytes] = []
    total_bytes = 0
    while True:
        on_chunk_read()
        chunk = response.read(_API_STREAM_FETCH_READ_CHUNK_BYTES)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_fetch_bytes:
            raise _api_stream_loader_error(
                "terminal_failure",
                "api_stream fetch exceeded max byte budget",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _classify_api_stream_fetch_exception(
    error: TimeoutError | HTTPError | URLError,
) -> ApiStreamFailure:
    """Map low-level transport exceptions into loader-facing failure semantics."""
    if isinstance(error, TimeoutError):
        return _build_api_stream_failure(
            "retryable_failure",
            "api_stream fetch timed out",
        )
    if isinstance(error, HTTPError):
        failure_kind: ApiStreamFailureKind = (
            "retryable_failure" if error.code in {408, 429, 500, 502, 503, 504}
            else "terminal_failure"
        )
        return _build_api_stream_failure(
            failure_kind,
            f"api_stream upstream returned HTTP {error.code}",
        )
    return _build_api_stream_failure(
        "retryable_failure",
        f"api_stream upstream connection failed: {error.reason}",
    )
