"""Direct tests for the stateless HTTP/HLS transport helper module.

These cases keep the orchestration-level loader suites focused on observable
behavior while locking down the request-building, bounded-read, and fetch
failure-classification helpers directly.
"""

from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

from stream_loader_http_hls_fetch import (
    _build_api_stream_request,
    _classify_api_stream_fetch_exception,
    _read_api_stream_response_bytes,
)


def test_build_api_stream_request_sets_user_agent_header() -> None:
    """The transport helper should stamp one stable user-agent header."""
    request = _build_api_stream_request("http://example.test/live/index.m3u8")
    assert request.full_url == "http://example.test/live/index.m3u8"
    assert request.headers["User-agent"] == "election-stream-monitor/1.0"


def test_read_api_stream_response_bytes_enforces_budget_and_cancel_hook() -> None:
    """The bounded-read helper should honor the cancel hook while streaming chunks."""
    chunks = [b"abc", b"def"]
    calls: list[str] = []

    def on_chunk_read() -> None:
        calls.append("tick")

    response = SimpleNamespace(read=lambda size: chunks.pop(0) if chunks else b"")
    payload = _read_api_stream_response_bytes(
        response,
        max_fetch_bytes=10,
        on_chunk_read=on_chunk_read,
    )

    assert payload == b"abcdef"
    assert calls == ["tick", "tick", "tick"]


def test_read_api_stream_response_bytes_rejects_oversized_payload() -> None:
    """The bounded-read helper should fail fast once the byte budget is exceeded."""
    response = SimpleNamespace(read=lambda size: b"abcdefgh")

    with pytest.raises(RuntimeError, match="fetch exceeded max byte budget"):
        _read_api_stream_response_bytes(
            response,
            max_fetch_bytes=4,
            on_chunk_read=lambda: None,
        )


def test_read_api_stream_response_bytes_stops_when_cancel_hook_raises() -> None:
    """The bounded-read helper should propagate cooperative cancellation immediately."""
    chunks = [b"abc", b"def"]
    calls = 0

    def on_chunk_read() -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("cancelled")

    response = SimpleNamespace(read=lambda size: chunks.pop(0) if chunks else b"")

    with pytest.raises(RuntimeError, match="cancelled"):
        _read_api_stream_response_bytes(
            response,
            max_fetch_bytes=10,
            on_chunk_read=on_chunk_read,
        )


@pytest.mark.parametrize(
    ("error", "expected_kind"),
    [
        (TimeoutError(), "retryable_failure"),
        (HTTPError("http://example.test", 429, "too many requests", {}, None), "retryable_failure"),
        (HTTPError("http://example.test", 403, "forbidden", {}, None), "terminal_failure"),
        (URLError("connection reset"), "retryable_failure"),
    ],
)
def test_classify_api_stream_fetch_exception_maps_retryable_and_terminal_cases(
    error: TimeoutError | HTTPError | URLError,
    expected_kind: str,
) -> None:
    """Fetch classification should preserve the retryable-versus-terminal contract."""
    assert _classify_api_stream_fetch_exception(error).kind == expected_kind
