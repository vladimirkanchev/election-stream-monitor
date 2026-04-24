"""Shared helpers for the `api_stream` session-runner test family.

This support module centralizes the seam setup used by:

- `tests/test_session_runner_api_stream_basic.py`
- `tests/test_session_runner_api_stream_http_hls.py`

It keeps analyzer registration helpers, fake chunk builders, and local HLS
fixture wiring in one place so the session-runner tests can stay focused on the
behavior they are asserting.
"""

from pathlib import Path

import config
import processor
import session_runner
import stream_loader_http_hls
from analyzer_contract import AnalysisSlice, AnalyzerRegistration
from stream_loader import FakeApiStreamEvent
from stream_loader import HttpHlsApiStreamLoader
from tests.local_hls_test_support import _serve_local_hls


class DummyStore:
    """Minimal in-memory store used by session-runner integration tests."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add_row(self, row: dict) -> None:
        self.rows.append(row)


def _configure_api_stream_runner_test(
    monkeypatch,
    tmp_path: Path,
    *,
    loader=None,
) -> None:
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    if loader is not None:
        _install_api_stream_loader(monkeypatch, loader)


def _configure_http_hls_runner_test(
    monkeypatch,
    tmp_path: Path,
    *,
    session_id: str,
    poll_interval_sec: float = 0.0,
    reconnect_backoff_sec: float = 0.0,
    sleep=None,
    config_overrides: dict[str, object] | None = None,
) -> None:
    default_session_id = session_id
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", poll_interval_sec)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", reconnect_backoff_sec)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    if config_overrides:
        for name, value in config_overrides.items():
            monkeypatch.setattr(config, name, value)
    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: HttpHlsApiStreamLoader(
            session_id or default_session_id
        ),
    )
    monkeypatch.setattr(
        stream_loader_http_hls.time,
        "sleep",
        sleep or (lambda seconds: None),
    )


def _install_api_stream_loader(monkeypatch, loader) -> None:
    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: loader,
    )


def _make_live_slices(
    tmp_path: Path,
    *,
    source_group: str,
    names: list[str],
) -> list[AnalysisSlice]:
    slices: list[AnalysisSlice] = []
    live_dir = tmp_path / source_group
    live_dir.mkdir(exist_ok=True)
    for index, name in enumerate(names):
        file_path = live_dir / name
        file_path.write_bytes(b"chunk")
        slices.append(
            AnalysisSlice(
                file_path=file_path,
                source_group=source_group,
                source_name=name,
                window_index=index,
                window_start_sec=float(index),
                window_duration_sec=1.0,
            )
        )
    return slices


def _playlist(*lines: str) -> str:
    return "\n".join(["#EXTM3U", *lines])


def _media_playlist(
    media_sequence: int,
    *segments: str,
    target_duration: int = 1,
    endlist: bool = True,
) -> str:
    lines = [
        f"#EXT-X-TARGETDURATION:{target_duration}",
        f"#EXT-X-MEDIA-SEQUENCE:{media_sequence}",
    ]
    for segment in segments:
        lines.extend(["#EXTINF:1.0,", segment])
    if endlist:
        lines.append("#EXT-X-ENDLIST")
    return _playlist(*lines)


def _segment_routes(
    *segment_names: str,
    prefix: str = "/live",
    body_prefix: str = "segment-",
) -> dict[str, tuple[int, bytes, str]]:
    routes: dict[str, tuple[int, bytes, str]] = {}
    for segment_name in segment_names:
        routes[f"{prefix}/{segment_name}"] = (
            200,
            f"{body_prefix}{segment_name}".encode("utf-8"),
            "video/mp2t",
        )
    return routes


def _fake_chunk_event(
    tmp_path: Path,
    *,
    chunk_index: int,
    current_item: str,
    file_name: str | None = None,
    payload: bytes = b"ts",
) -> FakeApiStreamEvent:
    file_path = tmp_path / (file_name or current_item)
    file_path.write_bytes(payload)
    return FakeApiStreamEvent(
        kind="chunk",
        chunk_index=chunk_index,
        current_item=current_item,
        file_path=file_path,
    )


def _fake_temporary_failure_event(
    *,
    chunk_index: int,
    current_item: str,
    message: str,
) -> FakeApiStreamEvent:
    return FakeApiStreamEvent(
        kind="temporary_failure",
        chunk_index=chunk_index,
        current_item=current_item,
        message=message,
    )


def _fake_terminal_failure_event(*, message: str) -> FakeApiStreamEvent:
    return FakeApiStreamEvent(
        kind="terminal_failure",
        message=message,
    )


def _fake_malformed_chunk_event(
    tmp_path: Path,
    *,
    chunk_index: int,
    current_item: str,
    file_name: str,
    payload: bytes = b"ts",
) -> FakeApiStreamEvent:
    file_path = tmp_path / file_name
    file_path.write_bytes(payload)
    return FakeApiStreamEvent(
        kind="malformed_chunk",
        chunk_index=chunk_index,
        current_item=current_item,
        file_path=file_path,
    )


def _build_blur_analyzer(score_by_name: dict[str, float]):
    def analyzer(
        file_path: Path,
        prefix: str | None = None,
        source_group: str | None = None,
        source_name: str | None = None,
        window_index: int | None = None,
        window_start_sec: float | None = None,
        window_duration_sec: float | None = None,
    ) -> dict:
        _ = (file_path, prefix)
        return {
            "analyzer": "video_blur",
            "source_type": "video",
            "source_name": str(source_name),
            "source_group": str(source_group),
            "timestamp_utc": f"2026-04-04 10:00:{int(window_index or 0):02d}",
            "processing_sec": 0.01,
            "blur_detected": True,
            "blur_score": score_by_name[str(source_name)],
            "threshold_used": 0.72,
            "window_index": window_index,
            "window_start_sec": window_start_sec,
            "window_duration_sec": window_duration_sec,
        }

    return analyzer


def _patch_processor_with_analyzer(
    monkeypatch,
    *,
    analyzer_name: str,
    store_name: str,
    analyzer,
    supported_modes: tuple[str, ...],
) -> None:
    monkeypatch.setattr(
        processor,
        "get_enabled_analyzers",
        lambda mode: [
            AnalyzerRegistration(
                name=analyzer_name,
                analyzer=analyzer,
                store_name=store_name,
                supported_modes=supported_modes,
                supported_suffixes=(".ts",),
                display_name="Test Analyzer",
                description="Live-like session test detector",
                produces_alerts=True,
            )
        ],
    )
    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {
            "video_metrics": DummyStore(),
            "blur_metrics": DummyStore(),
        },
    )
    monkeypatch.setattr("session_runner.black_frame_store.flush", lambda: None)
    monkeypatch.setattr("session_runner.blur_metrics_store.flush", lambda: None)


def _patch_processor_with_analyzers(
    monkeypatch,
    *,
    registrations: list[AnalyzerRegistration],
) -> None:
    monkeypatch.setattr(
        processor,
        "get_enabled_analyzers",
        lambda mode: list(registrations),
    )
    store_names = {registration.store_name for registration in registrations}
    monkeypatch.setattr(
        processor,
        "STORE_REGISTRY",
        {store_name: DummyStore() for store_name in store_names},
    )
    monkeypatch.setattr("session_runner.black_frame_store.flush", lambda: None)
    monkeypatch.setattr("session_runner.blur_metrics_store.flush", lambda: None)
