"""Tests for seam-based `api_stream` session-runner behavior.

These cases focus on the runner's live-session orchestration in
`src/session_runner.py` while avoiding real HTTP/HLS transport. They cover the
same lifecycle surface with deterministic seam loaders, leaving transport-heavy
coverage to `tests/test_session_runner_api_stream_http_hls.py`.
"""

from pathlib import Path

import pytest
import session_runner
from analyzer_contract import AnalysisSlice, AnalyzerRegistration
from session_io import read_session_snapshot
from session_runner import run_local_session
from stream_loader import (
    FakeApiStreamLoader,
    StaticApiStreamLoader,
    build_api_stream_source_contract,
)
from tests.session_runner_api_stream_test_support import (
    _build_blur_analyzer,
    _configure_api_stream_runner_test,
    _fake_chunk_event,
    _fake_malformed_chunk_event,
    _fake_temporary_failure_event,
    _fake_terminal_failure_event,
    _install_api_stream_loader,
    _make_live_slices,
    _patch_processor_with_analyzer,
    _patch_processor_with_analyzers,
)


def test_run_local_session_keeps_snapshot_contract_when_fake_loader_skips_bad_live_events(
    monkeypatch, tmp_path: Path
) -> None:
    """Live ingestion changes should not change the persisted session snapshot model."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)

    stream_source = build_api_stream_source_contract(
        "https://example.com/live/playlist.m3u8"
    )
    fake_loader = FakeApiStreamLoader(
        [
            _fake_chunk_event(
                tmp_path,
                chunk_index=0,
                current_item="live-window-000.ts",
            ),
            _fake_temporary_failure_event(
                chunk_index=1,
                current_item="live-window-001.ts",
                message="temporary fetch timeout",
            ),
            _fake_chunk_event(
                tmp_path,
                chunk_index=1,
                current_item="live-window-001.ts",
            ),
            _fake_chunk_event(
                tmp_path,
                chunk_index=1,
                current_item="live-window-001.ts",
            ),
            _fake_malformed_chunk_event(
                tmp_path,
                chunk_index=3,
                current_item="bad-window.ts",
                file_name="live-window-002.ts",
            ),
            _fake_chunk_event(
                tmp_path,
                chunk_index=2,
                current_item="live-window-002.ts",
            ),
        ]
    )
    _install_api_stream_loader(monkeypatch, fake_loader)

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer(
            {
                "live-window-000.ts": 0.2,
                "live-window-001.ts": 0.25,
                "live-window-002.ts": 0.3,
            }
        ),
        supported_modes=("api_stream",),
    )

    metadata = run_local_session(
        mode="api_stream",
        input_path=stream_source.input_path,
        selected_detectors=["video_blur"],
        session_id="session-api-fake-loader",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["session"]["mode"] == "api_stream"
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == 3
    assert snapshot["progress"]["current_item"] == "live-window-002.ts"
    assert len(snapshot["results"]) == 3
    assert snapshot["alerts"] == []


def test_run_local_session_persists_failed_api_stream_when_loader_hits_terminal_error(
    monkeypatch, tmp_path: Path
) -> None:
    """A terminal loader failure should create a failed live-session snapshot."""
    fake_loader = FakeApiStreamLoader(
        [
            _fake_terminal_failure_event(message="playlist permanently unavailable")
        ]
    )
    _configure_api_stream_runner_test(monkeypatch, tmp_path, loader=fake_loader)

    with pytest.raises(ValueError, match="playlist permanently unavailable"):
        run_local_session(
            mode="api_stream",
            input_path="https://example.com/live/playlist.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-loader-terminal",
        )

    snapshot = read_session_snapshot("session-api-loader-terminal")

    assert snapshot["session"]["status"] == "failed"
    assert snapshot["progress"]["status"] == "failed"
    assert snapshot["progress"]["processed_count"] == 0
    assert snapshot["progress"]["total_count"] == 0
    assert snapshot["results"] == []
    assert snapshot["alerts"] == []


def test_run_local_session_logs_api_stream_completion_summary(
    monkeypatch, tmp_path: Path
) -> None:
    """Completed api_stream runs should log one transport/session summary for operators."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)
    info_logs: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        session_runner.logger,
        "info",
        lambda message, *args: info_logs.append((message, args)),
    )

    fake_loader = FakeApiStreamLoader(
        [
            _fake_chunk_event(
                tmp_path,
                chunk_index=0,
                current_item="live-window-000.ts",
                payload=b"000",
            ),
            _fake_chunk_event(
                tmp_path,
                chunk_index=1,
                current_item="live-window-001.ts",
                payload=b"001",
            ),
        ]
    )
    _install_api_stream_loader(monkeypatch, fake_loader)

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer(
            {
                "live-window-000.ts": 0.2,
                "live-window-001.ts": 0.25,
            }
        ),
        supported_modes=("api_stream",),
    )

    run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-log-complete",
    )

    completion_logs = [
        args[1] for message, args in info_logs if message == "Completed session %s [%s]"
    ]
    assert completion_logs
    assert any("session_end_reason='completed'" in str(entry) for entry in completion_logs)
    assert any("source_url_class='hls_playlist_url'" in str(entry) for entry in completion_logs)
    assert any("processed_chunk_count=2" in str(entry) for entry in completion_logs)
    assert any("temp_cleanup_success_count=2" in str(entry) for entry in completion_logs)
    assert any("temp_cleanup_failure_count=0" in str(entry) for entry in completion_logs)


def test_run_local_session_deletes_processed_api_stream_temp_files(
    monkeypatch, tmp_path: Path
) -> None:
    """Processed live temp media should be deleted by the runner after each slice."""
    live_file = tmp_path / "live-window-000.ts"
    live_file.write_bytes(b"ts")

    fake_loader = FakeApiStreamLoader(
        [
            _fake_chunk_event(
                tmp_path,
                chunk_index=0,
                current_item="live-window-000.ts",
            )
        ]
    )
    _configure_api_stream_runner_test(monkeypatch, tmp_path, loader=fake_loader)

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer({"live-window-000.ts": 0.2}),
        supported_modes=("api_stream",),
    )

    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-temp-cleanup",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["progress"]["processed_count"] == 1
    assert not live_file.exists()


def test_run_local_session_preserves_partial_progress_before_fake_loader_terminal_failure(
    monkeypatch, tmp_path: Path
) -> None:
    """Accepted live chunks should remain persisted if a later fake-loader failure becomes terminal."""
    fake_loader = FakeApiStreamLoader(
        [
            _fake_chunk_event(
                tmp_path,
                chunk_index=0,
                current_item="live-window-000.ts",
            ),
            _fake_chunk_event(
                tmp_path,
                chunk_index=1,
                current_item="live-window-001.ts",
            ),
            _fake_terminal_failure_event(
                message="seam loader disconnected after partial progress"
            ),
        ]
    )
    _configure_api_stream_runner_test(monkeypatch, tmp_path, loader=fake_loader)

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer(
            {
                "live-window-000.ts": 0.2,
                "live-window-001.ts": 0.25,
            }
        ),
        supported_modes=("api_stream",),
    )

    with pytest.raises(
        ValueError, match="seam loader disconnected after partial progress"
    ):
        run_local_session(
            mode="api_stream",
            input_path="https://example.com/live/playlist.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-partial-then-terminal",
        )

    snapshot = read_session_snapshot("session-api-partial-then-terminal")

    assert snapshot["session"]["status"] == "failed"
    assert snapshot["progress"]["status"] == "failed"
    assert snapshot["progress"]["processed_count"] == 2
    assert snapshot["progress"]["current_item"] == "live-window-001.ts"
    assert snapshot["progress"]["status_reason"] == "source_unreachable"
    assert (
        snapshot["progress"]["status_detail"]
        == "seam loader disconnected after partial progress"
    )
    assert len(snapshot["results"]) == 2
    assert snapshot["alerts"] == []


def test_run_local_session_deletes_current_api_stream_temp_file_on_cancel(
    monkeypatch, tmp_path: Path
) -> None:
    """A yielded live chunk should be deleted immediately when cancel stops the session."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)
    live_file = tmp_path / "live-window-000.ts"
    live_file.write_bytes(b"ts")

    slice_ = AnalysisSlice(
        file_path=live_file,
        source_group="https://example.com/live/playlist.m3u8",
        source_name="live-window-000.ts",
        window_index=0,
        window_start_sec=0.0,
        window_duration_sec=1.0,
    )
    _install_api_stream_loader(monkeypatch, StaticApiStreamLoader([slice_]))

    from session_io import request_session_cancel

    request_session_cancel("session-api-cancel-before-processing")
    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-cancel-before-processing",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "cancelled"
    assert snapshot["progress"]["status"] == "cancelled"
    assert snapshot["progress"]["processed_count"] == 0
    assert not live_file.exists()


def test_run_local_session_cancels_after_temporary_loader_noise_before_next_accepted_chunk(
    monkeypatch, tmp_path: Path
) -> None:
    """A cancel request should still settle cleanly if a temporary loader failure happens first."""
    fake_loader = FakeApiStreamLoader(
        [
            _fake_chunk_event(
                tmp_path,
                chunk_index=0,
                current_item="live-window-001.ts",
            ),
            _fake_temporary_failure_event(
                chunk_index=1,
                current_item="live-window-002.ts",
                message="temporary upstream stall",
            ),
            _fake_chunk_event(
                tmp_path,
                chunk_index=1,
                current_item="live-window-002.ts",
            ),
        ]
    )
    _configure_api_stream_runner_test(monkeypatch, tmp_path, loader=fake_loader)

    cancel_requested = {"done": False}

    def cancelling_blur_analyzer(
        file_path: Path,
        prefix: str | None = None,
        source_group: str | None = None,
        source_name: str | None = None,
        window_index: int | None = None,
        window_start_sec: float | None = None,
        window_duration_sec: float | None = None,
    ) -> dict:
        _ = (file_path, prefix, source_group, window_start_sec, window_duration_sec)
        if not cancel_requested["done"]:
            cancel_requested["done"] = True
            from session_io import request_session_cancel

            request_session_cancel("session-api-cancel-after-noise")
        return {
            "analyzer": "video_blur",
            "source_type": "video",
            "source_name": str(source_name),
            "source_group": str(source_group),
            "timestamp_utc": f"2026-04-04 10:00:{int(window_index or 0):02d}",
            "processing_sec": 0.01,
            "blur_detected": False,
            "blur_score": 0.2,
            "threshold_used": 0.72,
            "window_index": window_index,
            "window_start_sec": window_start_sec,
            "window_duration_sec": window_duration_sec,
        }

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=cancelling_blur_analyzer,
        supported_modes=("api_stream",),
    )

    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-cancel-after-noise",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "cancelled"
    assert snapshot["progress"]["status"] == "cancelled"
    assert snapshot["progress"]["processed_count"] == 1
    assert snapshot["progress"]["current_item"] == "live-window-001.ts"
    assert snapshot["progress"]["status_reason"] == "cancel_requested"
    assert (
        snapshot["progress"]["status_detail"]
        == "Cancellation requested during slice processing"
    )
    assert len(snapshot["results"]) == 1


def test_run_local_session_completes_remote_api_stream_like_session(
    monkeypatch, tmp_path: Path
) -> None:
    """Remote api-stream inputs should progress through live-like slices and complete."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)
    remote_url = "https://example.com/live/playlist.m3u8"

    slices = _make_live_slices(
        tmp_path,
        source_group="stream-a",
        names=["live-window-001.ts", "live-window-002.ts", "live-window-003.ts"],
    )
    _install_api_stream_loader(monkeypatch, StaticApiStreamLoader(slices))

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer(
            {
                "live-window-001.ts": 0.20,
                "live-window-002.ts": 0.25,
                "live-window-003.ts": 0.30,
            }
        ),
        supported_modes=("api_stream",),
    )

    metadata = run_local_session(
        mode="api_stream",
        input_path=remote_url,
        selected_detectors=["video_blur"],
        session_id="session-api-remote",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert metadata.mode == "api_stream"
    assert metadata.input_path == remote_url
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == 3
    assert snapshot["progress"]["current_item"] == "live-window-003.ts"
    assert len(snapshot["results"]) == 3
    assert snapshot["alerts"] == []


def test_run_local_session_cancels_incremental_api_stream_cleanly(
    monkeypatch, tmp_path: Path
) -> None:
    """An explicit cancel request should stop the live loop after the current chunk."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)

    names = ["live-window-001.ts", "live-window-002.ts", "live-window-003.ts"]
    slices = _make_live_slices(tmp_path, source_group="stream-a", names=names)
    _install_api_stream_loader(monkeypatch, StaticApiStreamLoader(slices))

    cancel_requested = {"done": False}

    def cancelling_blur_analyzer(
        file_path: Path,
        prefix: str | None = None,
        source_group: str | None = None,
        source_name: str | None = None,
        window_index: int | None = None,
        window_start_sec: float | None = None,
        window_duration_sec: float | None = None,
    ) -> dict:
        _ = (file_path, prefix, source_group, window_start_sec, window_duration_sec)
        if not cancel_requested["done"]:
            cancel_requested["done"] = True
            from session_io import request_session_cancel

            request_session_cancel("session-api-cancelled")
        return {
            "analyzer": "video_blur",
            "source_type": "video",
            "source_name": str(source_name),
            "source_group": str(source_group),
            "timestamp_utc": f"2026-04-04 10:00:{int(window_index or 0):02d}",
            "processing_sec": 0.01,
            "blur_detected": False,
            "blur_score": 0.2,
            "threshold_used": 0.72,
            "window_index": window_index,
            "window_start_sec": window_start_sec,
            "window_duration_sec": window_duration_sec,
        }

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=cancelling_blur_analyzer,
        supported_modes=("api_stream",),
    )

    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-cancelled",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "cancelled"
    assert snapshot["progress"]["status"] == "cancelled"
    assert snapshot["progress"]["processed_count"] == 1
    assert snapshot["progress"]["current_item"] == "live-window-001.ts"
    assert len(snapshot["results"]) == 1


def test_run_local_session_continues_after_temporary_live_chunk_detector_failure(
    monkeypatch, tmp_path: Path
) -> None:
    """One bad live chunk should not fail the whole api-stream session."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)

    slices = _make_live_slices(
        tmp_path,
        source_group="stream-a",
        names=["live-window-001.ts", "live-window-002.ts", "live-window-003.ts"],
    )
    _install_api_stream_loader(monkeypatch, StaticApiStreamLoader(slices))

    def flaky_blur_analyzer(
        file_path: Path,
        prefix: str | None = None,
        source_group: str | None = None,
        source_name: str | None = None,
        window_index: int | None = None,
        window_start_sec: float | None = None,
        window_duration_sec: float | None = None,
    ) -> dict:
        _ = (prefix, source_group)
        if window_index == 1:
            raise ValueError("temporary chunk decode failure")
        return {
            "analyzer": "video_blur",
            "source_type": "video",
            "source_name": str(source_name),
            "source_group": str(source_group),
            "timestamp_utc": f"2026-04-04 10:00:0{window_index}",
            "processing_sec": 0.01,
            "blur_detected": False,
            "blur_score": 0.2,
            "threshold_used": 0.72,
            "window_index": window_index,
            "window_start_sec": window_start_sec,
            "window_duration_sec": window_duration_sec,
        }

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=flaky_blur_analyzer,
        supported_modes=("api_stream",),
    )

    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-flaky",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == 3
    assert len(snapshot["results"]) == 2
    assert snapshot["progress"]["current_item"] == "live-window-003.ts"


def test_run_local_session_fails_processing_after_earlier_skipped_temporary_chunk(
    monkeypatch, tmp_path: Path
) -> None:
    """A later analyzer failure should still persist a failed run even after earlier temporary loader noise."""
    fake_loader = FakeApiStreamLoader(
        [
            _fake_chunk_event(
                tmp_path,
                chunk_index=0,
                current_item="live-window-000.ts",
            ),
            _fake_temporary_failure_event(
                chunk_index=1,
                current_item="live-window-001.ts",
                message="temporary fetch timeout",
            ),
            _fake_chunk_event(
                tmp_path,
                chunk_index=1,
                current_item="live-window-001.ts",
            ),
        ]
    )
    _configure_api_stream_runner_test(monkeypatch, tmp_path, loader=fake_loader)

    call_count = {"value": 0}

    def failing_bundle(
        file_path: Path,
        prefix: str,
        mode: str,
        session_id: str,
        selected_analyzers: set[str] | None = None,
        persist_to_store: bool = True,
        analysis_slice: AnalysisSlice | None = None,
    ) -> dict[str, list[dict[str, object]]]:
        _ = (file_path, prefix, mode, selected_analyzers, persist_to_store)
        call_count["value"] += 1
        if call_count["value"] == 2:
            raise ValueError("processing failed after temporary chunk")
        return {
            "results": [
                {
                    "session_id": session_id,
                    "detector_id": "video_blur",
                    "payload": {
                        "source_name": analysis_slice.source_name if analysis_slice else None
                    },
                }
            ],
            "alerts": [],
        }

    monkeypatch.setattr("session_runner.run_enabled_analyzers_bundle", failing_bundle)
    monkeypatch.setattr("session_runner.black_frame_store.flush", lambda: None)
    monkeypatch.setattr("session_runner.blur_metrics_store.flush", lambda: None)

    with pytest.raises(ValueError, match="processing failed after temporary chunk"):
        run_local_session(
            mode="api_stream",
            input_path="https://example.com/live/playlist.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-fail-after-noise",
        )

    snapshot = read_session_snapshot("session-api-fail-after-noise")

    assert snapshot["session"]["status"] == "failed"
    assert snapshot["progress"]["status"] == "failed"
    assert snapshot["progress"]["processed_count"] == 1
    assert snapshot["progress"]["status_reason"] == "source_unreachable"
    assert "processing failed after temporary chunk" in str(
        snapshot["progress"]["status_detail"]
    )
    assert len(snapshot["results"]) == 1


def test_run_local_session_tolerates_repeated_temporary_live_chunk_failures(
    monkeypatch, tmp_path: Path
) -> None:
    """Repeated live-chunk detector failures should still allow the session to complete."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)

    names = [f"live-window-{index:03d}.ts" for index in range(1, 9)]
    slices = _make_live_slices(tmp_path, source_group="stream-a", names=names)
    _install_api_stream_loader(monkeypatch, StaticApiStreamLoader(slices))

    failing_windows = {1, 3, 5}

    def flaky_blur_analyzer(
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
            raise ValueError(f"temporary failure for window {window_index}")
        return {
            "analyzer": "video_blur",
            "source_type": "video",
            "source_name": str(source_name),
            "source_group": str(source_group),
            "timestamp_utc": f"2026-04-04 10:00:{int(window_index or 0):02d}",
            "processing_sec": 0.01,
            "blur_detected": False,
            "blur_score": 0.2,
            "threshold_used": 0.72,
            "window_index": window_index,
            "window_start_sec": window_start_sec,
            "window_duration_sec": window_duration_sec,
        }

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=flaky_blur_analyzer,
        supported_modes=("api_stream",),
    )

    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-repeated-flaky",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == 8
    assert len(snapshot["results"]) == 5
    assert snapshot["progress"]["current_item"] == "live-window-008.ts"


def test_run_local_session_completes_with_zero_progress_when_fake_loader_only_emits_temporary_failures(
    monkeypatch, tmp_path: Path
) -> None:
    """A fake live run with only temporary failures should settle cleanly without persisted results."""
    fake_loader = FakeApiStreamLoader(
        [
            _fake_temporary_failure_event(
                chunk_index=0,
                current_item="live-window-000.ts",
                message="temporary fetch timeout",
            ),
            _fake_temporary_failure_event(
                chunk_index=1,
                current_item="live-window-001.ts",
                message="temporary upstream stall",
            ),
        ]
    )
    _configure_api_stream_runner_test(monkeypatch, tmp_path, loader=fake_loader)

    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-zero-progress",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["session"]["status"] == "completed"
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == 0
    assert snapshot["progress"]["current_item"] is None
    assert snapshot["progress"]["status_reason"] == "completed"
    assert snapshot["progress"]["status_detail"] is None
    assert snapshot["results"] == []
    assert snapshot["alerts"] == []


def test_run_local_session_live_like_blur_progression_tracks_alert_reentry(
    monkeypatch, tmp_path: Path
) -> None:
    """Live-like slice sequences should persist progress and timed blur alerts."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)

    names = [
        "live-window-001.ts",
        "live-window-002.ts",
        "live-window-003.ts",
        "live-window-004.ts",
        "live-window-005.ts",
        "live-window-006.ts",
        "live-window-007.ts",
        "live-window-008.ts",
    ]
    scores = {
        "live-window-001.ts": 0.82,
        "live-window-002.ts": 0.79,
        "live-window-003.ts": 0.60,
        "live-window-004.ts": 0.40,
        "live-window-005.ts": 0.42,
        "live-window-006.ts": 0.45,
        "live-window-007.ts": 0.81,
        "live-window-008.ts": 0.77,
    }
    slices = _make_live_slices(tmp_path, source_group="stream-a", names=names)
    _install_api_stream_loader(monkeypatch, StaticApiStreamLoader(slices))

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer(scores),
        supported_modes=("api_stream",),
    )

    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_blur"],
        session_id="session-api-blur",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["progress"]["processed_count"] == 8
    assert snapshot["progress"]["alert_count"] == 2
    assert [alert["window_index"] for alert in snapshot["alerts"]] == [2, 7]
    assert [alert["source_name"] for alert in snapshot["alerts"]] == [
        "live-window-003.ts",
        "live-window-008.ts",
    ]


def test_run_local_session_persists_two_detector_progress_for_api_stream(
    monkeypatch, tmp_path: Path
) -> None:
    """A fake live run with two detectors should keep multi-detector progress fields coherent."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)

    slices = _make_live_slices(
        tmp_path,
        source_group="stream-a",
        names=["live-window-001.ts", "live-window-002.ts"],
    )
    _install_api_stream_loader(monkeypatch, StaticApiStreamLoader(slices))

    def metrics_analyzer(
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
            "black_ratio": 0.1,
            "longest_black_sec": 0.0,
            "window_index": window_index,
            "window_start_sec": window_start_sec,
            "window_duration_sec": window_duration_sec,
        }

    registrations = [
        AnalyzerRegistration(
            name="video_metrics",
            analyzer=metrics_analyzer,
            store_name="video_metrics",
            supported_modes=("api_stream",),
            supported_suffixes=(".ts",),
            display_name="Metrics Analyzer",
            description="Live metrics test detector",
            produces_alerts=True,
        ),
        AnalyzerRegistration(
            name="video_blur",
            analyzer=_build_blur_analyzer(
                {
                    "live-window-001.ts": 0.2,
                    "live-window-002.ts": 0.25,
                }
            ),
            store_name="blur_metrics",
            supported_modes=("api_stream",),
            supported_suffixes=(".ts",),
            display_name="Blur Analyzer",
            description="Live blur test detector",
            produces_alerts=True,
        ),
    ]
    _patch_processor_with_analyzers(
        monkeypatch,
        registrations=registrations,
    )

    metadata = run_local_session(
        mode="api_stream",
        input_path="https://example.com/live/playlist.m3u8",
        selected_detectors=["video_metrics", "video_blur"],
        session_id="session-api-two-detectors",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["progress"]["processed_count"] == 2
    assert snapshot["progress"]["latest_result_detectors"] == [
        "video_metrics",
        "video_blur",
    ]
    assert snapshot["progress"]["latest_result_detector"] == "video_blur"
    assert len(snapshot["results"]) == 4
    assert snapshot["latest_result"]["detector_id"] == "video_blur"


def test_run_local_session_marks_remote_api_stream_failed_when_processing_raises(
    monkeypatch, tmp_path: Path
) -> None:
    """Unrecoverable live processing errors should persist failed session state."""
    _configure_api_stream_runner_test(monkeypatch, tmp_path)
    logged: list[tuple[str, tuple[object, ...]]] = []

    slices = _make_live_slices(
        tmp_path,
        source_group="stream-a",
        names=["live-window-001.ts", "live-window-002.ts", "live-window-003.ts"],
    )
    _install_api_stream_loader(monkeypatch, StaticApiStreamLoader(slices))

    call_count = {"value": 0}

    def failing_bundle(
        file_path: Path,
        prefix: str,
        mode: str,
        session_id: str,
        selected_analyzers: set[str] | None = None,
        persist_to_store: bool = True,
        analysis_slice: AnalysisSlice | None = None,
    ) -> dict[str, list[dict[str, object]]]:
        _ = (file_path, prefix, mode, selected_analyzers, persist_to_store)
        call_count["value"] += 1
        if call_count["value"] == 2:
            raise ValueError("stream reader disconnected")
        return {
            "results": [
                {
                    "session_id": session_id,
                    "detector_id": "video_blur",
                    "payload": {
                        "source_name": analysis_slice.source_name if analysis_slice else None
                    },
                }
            ],
            "alerts": [],
        }

    monkeypatch.setattr("session_runner.run_enabled_analyzers_bundle", failing_bundle)
    monkeypatch.setattr("session_runner.black_frame_store.flush", lambda: None)
    monkeypatch.setattr("session_runner.blur_metrics_store.flush", lambda: None)
    monkeypatch.setattr(
        session_runner.logger,
        "error",
        lambda message, *args: logged.append((message, args)),
    )

    try:
        run_local_session(
            mode="api_stream",
            input_path="https://example.com/live/playlist.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-failed",
        )
    except ValueError:
        snapshot = read_session_snapshot("session-api-failed")
        assert snapshot["session"]["status"] == "failed"
        assert snapshot["progress"]["status"] == "failed"
        assert snapshot["progress"]["processed_count"] == 1
        assert len(snapshot["results"]) == 1
        assert logged
        message, args = logged[0]
        assert message == "Session %s failed: %s [%s]"
        assert args[0] == "session-api-failed"
        assert "stream reader disconnected" in str(args[1])
        assert "session_id='session-api-failed'" in str(args[2])
        assert "source_kind='api_stream'" in str(args[2])
        assert "current_item='live-window-001.ts'" in str(args[2])
        assert "session_end_reason='terminal_failure'" in str(args[2])
        assert "processed_chunk_count=1" in str(args[2])
        assert "temp_cleanup_success_count=2" in str(args[2])
    else:
        raise AssertionError(
            "Expected the session runner to surface the processing failure"
        )
