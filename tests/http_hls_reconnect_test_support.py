"""Shared setup helpers for the split HTTP/HLS reconnect-focused test suites."""

from pathlib import Path

import pytest

import config
from tests.http_hls_test_support import configure_http_hls_loader_test


def configure_http_hls_reconnect_test(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    poll_interval_sec: float = 0.0,
    reconnect_backoff_sec: float = 0.0,
    sleep=None,
) -> None:
    """Install the common reconnect harness with a configurable retry backoff."""
    configure_http_hls_loader_test(
        monkeypatch,
        tmp_path,
        poll_interval_sec=poll_interval_sec,
        sleep=sleep,
    )
    monkeypatch.setattr(
        config,
        "API_STREAM_RECONNECT_BACKOFF_SEC",
        reconnect_backoff_sec,
    )
