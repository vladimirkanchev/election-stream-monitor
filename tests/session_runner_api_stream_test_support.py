"""Shared helpers for session-runner-oriented backend tests.

This module started with the `api_stream` runner suites, but it now also hosts
small reusable helpers for local-runner and ground-truth tests. Keep it
practical, not framework-like: the goal is to remove repeated patching and
fixture setup, not to build a mini test framework.

Reading guide:
- use the loader helpers when a test needs fake or static live slices
- use the analyzer builders when a scenario only varies by detector behavior
- use the bundle helpers when the runner test wants to bypass processor logic
- keep scenario assertions in the test files, not here
"""

from dataclasses import dataclass, field
from pathlib import Path

import config
import processor
import session_runner
import stream_loader_http_hls
from analyzer_contract import AnalysisSlice, AnalyzerRegistration
from session_io import request_session_cancel
from stream_loader import FakeApiStreamEvent, HttpHlsApiStreamLoader, StaticApiStreamLoader
from tests.local_hls_test_support import _serve_local_hls


@dataclass(slots=True)
class DummyStore:
    """Minimal in-memory store used by session-runner integration tests."""

    rows: list[dict] = field(default_factory=list)

    def add_row(self, row: dict) -> None:
        """Record one persisted row for later assertions."""
        self.rows.append(row)


def _configure_runner_output_paths(monkeypatch, tmp_path: Path) -> None:
    """Redirect session output into a test-local folder."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")


def _patch_runner_store_flushes(monkeypatch) -> None:
    """Disable real metric-store flush side effects for runner tests."""
    monkeypatch.setattr("session_runner.black_frame_store.flush", lambda: None)
    monkeypatch.setattr("session_runner.blur_metrics_store.flush", lambda: None)


def _patch_runner_bundle(
    monkeypatch,
    bundle_runner,
    *,
    patch_flushes: bool = True,
) -> None:
    """Patch the runner bundle seam and optionally disable store flushes."""
    monkeypatch.setattr("session_runner.run_enabled_analyzers_bundle", bundle_runner)
    if patch_flushes:
        _patch_runner_store_flushes(monkeypatch)


def _configure_api_stream_runner_test(
    monkeypatch,
    tmp_path: Path,
    *,
    loader=None,
) -> None:
    """Prepare session output paths and optionally install one live-loader seam."""
    _configure_runner_output_paths(monkeypatch, tmp_path)
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
    """Prepare config and loader seams for concrete HTTP/HLS runner tests."""
    default_session_id = session_id
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", poll_interval_sec)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", reconnect_backoff_sec)
    _configure_runner_output_paths(monkeypatch, tmp_path)
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
    """Patch the public runner loader seam to return one provided loader instance."""
    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: loader,
    )


def _install_static_api_stream_loader(
    monkeypatch,
    tmp_path: Path,
    *,
    source_group: str,
    names: list[str],
) -> list[AnalysisSlice]:
    """Create live slices and install them behind the static loader seam."""
    slices = _make_live_slices(tmp_path, source_group=source_group, names=names)
    _install_api_stream_loader(monkeypatch, StaticApiStreamLoader(slices))
    return slices


def _make_live_slices(
    tmp_path: Path,
    *,
    source_group: str,
    names: list[str],
) -> list[AnalysisSlice]:
    """Materialize synthetic live slices with one temp media file per source name."""
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


def _make_live_loader_events(slices: list[AnalysisSlice]) -> list[FakeApiStreamEvent]:
    """Translate synthetic live slices into fake-loader chunk events."""
    return [
        FakeApiStreamEvent(
            kind="chunk",
            chunk_index=analysis_slice.window_index,
            current_item=analysis_slice.source_name,
            file_path=analysis_slice.file_path,
            window_start_sec=analysis_slice.window_start_sec,
            window_duration_sec=analysis_slice.window_duration_sec,
        )
        for analysis_slice in slices
    ]


def _playlist(*lines: str) -> str:
    """Build a minimal playlist string with the standard HLS header."""
    return "\n".join(["#EXTM3U", *lines])


def _media_playlist(
    media_sequence: int,
    *segments: str,
    target_duration: int = 1,
    endlist: bool = True,
) -> str:
    """Build a simple media playlist used by local HLS transport tests."""
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
    """Return small HTTP route fixtures for a set of transport-test segments."""
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
    """Create a fake accepted-chunk loader event backed by a temp media file."""
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
    """Create a fake retryable loader event that should not end the session."""
    return FakeApiStreamEvent(
        kind="temporary_failure",
        chunk_index=chunk_index,
        current_item=current_item,
        message=message,
    )


def _fake_terminal_failure_event(*, message: str) -> FakeApiStreamEvent:
    """Create a fake terminal loader event that must fail the session."""
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
    """Create a fake malformed chunk event backed by a temp media file."""
    file_path = tmp_path / file_name
    file_path.write_bytes(payload)
    return FakeApiStreamEvent(
        kind="malformed_chunk",
        chunk_index=chunk_index,
        current_item=current_item,
        file_path=file_path,
    )


def _build_blur_analyzer(score_by_name: dict[str, float]):
    """Build a deterministic blur analyzer keyed by synthetic source name."""
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


def _build_cancelling_blur_analyzer(
    *,
    session_id: str,
    cancel_after_runs: int = 1,
    score: float = 0.2,
    blur_detected: bool = False,
):
    """Build a blur analyzer that requests session cancel after N runs."""
    runs = {"count": 0}

    def analyzer(
        file_path: Path,
        prefix: str | None = None,
        source_group: str | None = None,
        source_name: str | None = None,
        window_index: int | None = None,
        window_start_sec: float | None = None,
        window_duration_sec: float | None = None,
    ) -> dict:
        _ = (file_path, prefix, source_group, window_start_sec, window_duration_sec)
        runs["count"] += 1
        if runs["count"] == cancel_after_runs:
            request_session_cancel(session_id)
        return {
            "analyzer": "video_blur",
            "source_type": "video",
            "source_name": str(source_name),
            "source_group": str(source_group),
            "timestamp_utc": f"2026-04-04 10:00:{int(window_index or 0):02d}",
            "processing_sec": 0.01,
            "blur_detected": blur_detected,
            "blur_score": score,
            "threshold_used": 0.72,
            "window_index": window_index,
            "window_start_sec": window_start_sec,
            "window_duration_sec": window_duration_sec,
        }

    return analyzer


def _build_flaky_blur_analyzer(
    *,
    failing_windows: set[int],
    failure_message_factory=None,
    score: float = 0.2,
):
    """Build a blur analyzer that fails on selected windows and succeeds otherwise."""
    def analyzer(
        file_path: Path,
        prefix: str | None = None,
        source_group: str | None = None,
        source_name: str | None = None,
        window_index: int | None = None,
        window_start_sec: float | None = None,
        window_duration_sec: float | None = None,
    ) -> dict:
        _ = (file_path, prefix, source_group)
        if window_index in failing_windows:
            if failure_message_factory is None:
                raise ValueError(f"temporary failure for window {window_index}")
            raise ValueError(str(failure_message_factory(window_index)))
        return {
            "analyzer": "video_blur",
            "source_type": "video",
            "source_name": str(source_name),
            "source_group": str(source_group),
            "timestamp_utc": f"2026-04-04 10:00:{int(window_index or 0):02d}",
            "processing_sec": 0.01,
            "blur_detected": False,
            "blur_score": score,
            "threshold_used": 0.72,
            "window_index": window_index,
            "window_start_sec": window_start_sec,
            "window_duration_sec": window_duration_sec,
        }

    return analyzer


def _build_video_metrics_analyzer(*, black_ratio: float = 0.1):
    """Build a minimal video-metrics analyzer for multi-detector runner tests."""
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
            "analyzer": "video_metrics",
            "source_type": "video",
            "source_name": str(source_name),
            "source_group": str(source_group),
            "timestamp_utc": f"2026-04-04 10:10:{int(window_index or 0):02d}",
            "processing_sec": 0.02,
            "black_ratio": black_ratio,
            "longest_black_sec": 0.0,
            "window_index": window_index,
            "window_start_sec": window_start_sec,
            "window_duration_sec": window_duration_sec,
        }

    return analyzer


def _build_result_only_bundle(
    *,
    detector_id: str = "video_blur",
    fail_on_call: int | None = None,
    failure_message: str | None = None,
):
    """Build a bundle seam that returns one result row and can fail on call N."""
    calls = {"count": 0}

    def bundle_runner(
        file_path: Path,
        prefix: str,
        mode: str,
        session_id: str,
        selected_analyzers: set[str] | None = None,
        persist_to_store: bool = True,
        analysis_slice: AnalysisSlice | None = None,
    ) -> dict[str, list[dict[str, object]]]:
        _ = (file_path, prefix, mode, selected_analyzers, persist_to_store)
        calls["count"] += 1
        if fail_on_call is not None and calls["count"] == fail_on_call:
            raise ValueError(failure_message or "simulated bundle failure")
        return {
            "results": [
                {
                    "session_id": session_id,
                    "detector_id": detector_id,
                    "payload": {
                        "source_name": analysis_slice.source_name if analysis_slice else None
                    },
                }
            ],
            "alerts": [],
        }

    return bundle_runner


def _assert_basic_completed_snapshot(
    snapshot: dict[str, object],
    *,
    processed_count: int,
    current_item: str | None,
    result_count: int,
) -> None:
    """Assert the common completed-session progress shape for live runner tests."""
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == processed_count
    assert snapshot["progress"]["current_item"] == current_item
    assert len(snapshot["results"]) == result_count


def _assert_basic_cancelled_snapshot(
    snapshot: dict[str, object],
    *,
    processed_count: int,
    current_item: str | None,
    result_count: int,
) -> None:
    """Assert the common cancelled-session progress shape for live runner tests."""
    assert snapshot["progress"]["status"] == "cancelled"
    assert snapshot["progress"]["processed_count"] == processed_count
    assert snapshot["progress"]["current_item"] == current_item
    assert len(snapshot["results"]) == result_count


def _patch_processor_with_analyzer(
    monkeypatch,
    *,
    analyzer_name: str,
    store_name: str,
    analyzer,
    supported_modes: tuple[str, ...],
) -> None:
    """Install one analyzer registration plus in-memory stores for runner tests."""
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
    _patch_runner_store_flushes(monkeypatch)


def _patch_processor_with_analyzers(
    monkeypatch,
    *,
    registrations: list[AnalyzerRegistration],
) -> None:
    """Install multiple analyzer registrations plus matching in-memory stores."""
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
    _patch_runner_store_flushes(monkeypatch)
