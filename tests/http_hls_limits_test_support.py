"""Shared helpers for the split HTTP/HLS loader limits test suites."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import config
import stream_loader_http_hls
from stream_loader import HttpHlsApiStreamLoader
from stream_loader_contracts import ApiStreamSourceContract
from tests.http_hls_test_support import (
    _TS_CONTENT_TYPE,
    build_http_hls_source,
    configure_http_hls_loader_test,
)


def _set_optional_limit(monkeypatch: pytest.MonkeyPatch, setting_name: str, value: Any) -> None:
    """Patch one loader limit setting only when a test provided an override."""
    if value is not None:
        monkeypatch.setattr(config, setting_name, value)


def configure_http_hls_limits_test(
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
    """Install the common HTTP/HLS test harness plus optional limit overrides."""
    configure_http_hls_loader_test(
        monkeypatch,
        tmp_path,
        poll_interval_sec=poll_interval_sec,
        max_idle_playlist_polls=max_idle_playlist_polls,
        sleep=sleep,
    )
    _set_optional_limit(monkeypatch, "API_STREAM_MAX_PLAYLIST_REFRESHES", max_playlist_refreshes)
    _set_optional_limit(monkeypatch, "API_STREAM_MAX_SESSION_RUNTIME_SEC", max_session_runtime_sec)
    _set_optional_limit(monkeypatch, "API_STREAM_MAX_RECONNECT_ATTEMPTS", max_reconnect_attempts)
    _set_optional_limit(monkeypatch, "API_STREAM_RECONNECT_BACKOFF_SEC", reconnect_backoff_sec)
    _set_optional_limit(monkeypatch, "API_STREAM_TEMP_MAX_BYTES", temp_max_bytes)
    _set_optional_limit(monkeypatch, "API_STREAM_MAX_FETCH_BYTES", max_fetch_bytes)
    if sleep is not None:
        monkeypatch.setattr(stream_loader_http_hls.time, "sleep", sleep)
    if monotonic is not None:
        monkeypatch.setattr(stream_loader_http_hls.time, "monotonic", monotonic)


def segment_routes(
    *indexes: int,
    prefix: str = "/live",
    body_prefix: str = "segment-",
) -> dict[str, tuple[int, bytes, str]]:
    """Build deterministic TS segment routes for a local HLS fixture server."""
    return {
        f"{prefix}/segment_{index:03d}.ts": (
            200,
            f"{body_prefix}{index}".encode(),
            _TS_CONTENT_TYPE,
        )
        for index in indexes
    }


def build_loader_source(
    base_url: str,
    session_id: str,
    *,
    playlist_path: str = "/live/index.m3u8",
) -> tuple[HttpHlsApiStreamLoader, ApiStreamSourceContract]:
    """Create a real loader plus a matching source contract for one test session."""
    loader = HttpHlsApiStreamLoader(session_id)
    source = build_http_hls_source(base_url, playlist_path)
    return loader, source


def seen_segment_keys(source_path: str, *indexes: int) -> set[tuple[str, int, str]]:
    """Build the persisted dedup keys expected for the given segment indexes."""
    return {
        (source_path, index, f"segment_{index}.ts")
        for index in indexes
    }


def request_url(request) -> str:
    """Read the normalized URL from either urllib request shape used in tests."""
    return request.full_url if hasattr(request, "full_url") else request.get_full_url()


__all__ = [
    "build_loader_source",
    "configure_http_hls_limits_test",
    "replace",
    "request_url",
    "seen_segment_keys",
    "segment_routes",
]
