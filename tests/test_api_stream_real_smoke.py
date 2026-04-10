"""Opt-in smoke tests for real public HLS sources.

These tests are intentionally disabled by default because they depend on public
network sources that can change, rate-limit, or disappear over time. They are
meant for pre-pilot manual verification when we want confidence that:

- source validation still accepts direct public `.m3u8` URLs
- playback resolution still returns the original remote stream URL
- the real HTTP/HLS loader can start against at least one real provider

Enable with:

    API_STREAM_REAL_SMOKE=1 .venv/bin/pytest -p no:cacheprovider tests/test_api_stream_real_smoke.py -q

Optionally override the source list with:

    API_STREAM_REAL_SMOKE_URLS="https://...m3u8 https://...m3u8"
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

import config
from playback_sources import resolve_playback_source
from source_validation import validate_api_stream_url
from stream_loader import (
    ApiStreamLoaderError,
    HttpHlsApiStreamLoader,
    build_api_stream_source_contract,
    cleanup_api_stream_temp_session_dir,
)


pytestmark = pytest.mark.skipif(
    os.getenv("API_STREAM_REAL_SMOKE") != "1",
    reason="Real public-stream smoke tests are opt-in.",
)

DEFAULT_REAL_STREAM_SMOKE_URLS = (
    "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
    "https://devimages-cdn.apple.com/samplecode/avfoundationMedia/AVFoundationQueuePlayer_HLS2/master.m3u8",
)


def _real_stream_smoke_urls() -> tuple[str, ...]:
    configured = tuple(
        candidate.strip()
        for candidate in os.getenv("API_STREAM_REAL_SMOKE_URLS", "").split()
        if candidate.strip()
    )
    return configured or DEFAULT_REAL_STREAM_SMOKE_URLS


def _session_id_for_url(url: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")
    return f"real-smoke-{slug[:40]}"


def test_real_public_stream_smoke_validation_and_playback_resolution() -> None:
    """Each configured public stream should remain a valid direct api_stream input."""
    for url in _real_stream_smoke_urls():
        assert validate_api_stream_url(url) == url
        assert resolve_playback_source("api_stream", url) == url


@pytest.mark.parametrize("url", _real_stream_smoke_urls())
def test_real_public_stream_smoke_loader_starts_cleanly(
    url: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The real loader should either start cleanly or fail with one explicit loader error."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")

    session_id = _session_id_for_url(url)
    loader = HttpHlsApiStreamLoader(session_id)
    source = build_api_stream_source_contract(url)

    try:
        loader.connect(source)
        first_slice = next(loader.iter_slices())
    except StopIteration as error:
        raise AssertionError(f"Expected at least one slice from {url}") from error
    except ApiStreamLoaderError as error:
        raise AssertionError(
            f"Expected {url} to start cleanly, but loader failed: {error.failure.message}"
        ) from error
    finally:
        loader.close()
        cleanup_api_stream_temp_session_dir(session_id)

    assert first_slice.source_group == url
    assert first_slice.file_path.exists()
