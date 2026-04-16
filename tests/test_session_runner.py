"""Tests for session-runner lifecycle, slice discovery, and persistence behavior.

These tests describe the current local-first monitoring contract:

- sessions create metadata, progress, result, and alert artifacts incrementally
- cancellation and failure update persisted state predictably
- local input discovery respects playlist order and slice expansion rules
- malformed or risky inputs degrade safely instead of being treated as work
"""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread

import config
import processor
import pytest
import session_runner
from analyzer_contract import AnalysisSlice, AnalyzerRegistration
from session_io import read_session_snapshot
from session_runner import run_local_session
from stream_loader import (
    FakeApiStreamEvent,
    FakeApiStreamLoader,
    HttpHlsApiStreamLoader,
    StaticApiStreamLoader,
    build_api_stream_source_contract,
)


class DummyStore:
    """Minimal in-memory store used by session-runner integration tests."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add_row(self, row: dict) -> None:
        self.rows.append(row)


def test_run_local_session_writes_incremental_files(
    monkeypatch, tmp_path: Path
) -> None:
    """A normal session should persist metadata, progress, and result events incrementally."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")

    input_dir = tmp_path / "segments"
    input_dir.mkdir()
    (input_dir / "segment_0001.ts").write_bytes(b"aa")
    (input_dir / "segment_0002.ts").write_bytes(b"bb")

    def fake_run_enabled_analyzers_bundle(
        file_path: Path,
        prefix: str,
        mode: str,
        session_id: str,
        selected_analyzers: set[str] | None = None,
        persist_to_store: bool = True,
    ) -> dict[str, list[dict[str, object]]]:
        _ = (prefix, mode, selected_analyzers, persist_to_store)
        return {
            "results": [
                {
                    "session_id": session_id,
                    "detector_id": "video_metrics",
                    "payload": {"source_name": file_path.name},
                }
            ],
            "alerts": [],
        }

    monkeypatch.setattr(
        "session_runner.run_enabled_analyzers_bundle",
        fake_run_enabled_analyzers_bundle,
    )
    monkeypatch.setattr("session_runner.black_frame_store.flush", lambda: None)

    metadata = run_local_session(
        mode="video_segments",
        input_path=input_dir,
        selected_detectors=["video_metrics"],
    )

    session_dir = (tmp_path / "sessions") / metadata.session_id
    progress = json.loads((session_dir / "progress.json").read_text(encoding="utf-8"))
    results_lines = (session_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()

    assert metadata.status == "completed"
    assert progress["processed_count"] == 2
    assert progress["status"] == "completed"
    assert progress["status_reason"] == "completed"
    assert progress["status_detail"] is None
    assert len(results_lines) == 2


def test_run_local_session_stops_when_cancel_is_requested(
    monkeypatch, tmp_path: Path
) -> None:
    """A cancel request observed mid-run should stop the session cleanly."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")

    input_dir = tmp_path / "segments"
    input_dir.mkdir()
    (input_dir / "segment_0001.ts").write_bytes(b"aa")
    (input_dir / "segment_0002.ts").write_bytes(b"bb")

    cancel_requested = {"done": False}

    def fake_run_enabled_analyzers_bundle(
        file_path: Path,
        prefix: str,
        mode: str,
        session_id: str,
        selected_analyzers: set[str] | None = None,
        persist_to_store: bool = True,
    ) -> dict[str, list[dict[str, object]]]:
        _ = (prefix, mode, selected_analyzers, persist_to_store)
        if not cancel_requested["done"]:
            cancel_requested["done"] = True
            from session_io import request_session_cancel

            request_session_cancel(session_id)
        return {
            "results": [
                {
                    "session_id": session_id,
                    "detector_id": "video_metrics",
                    "payload": {"source_name": file_path.name},
                }
            ],
            "alerts": [],
        }

    monkeypatch.setattr(
        "session_runner.run_enabled_analyzers_bundle",
        fake_run_enabled_analyzers_bundle,
    )
    monkeypatch.setattr("session_runner.black_frame_store.flush", lambda: None)
    monkeypatch.setattr("session_runner.blur_metrics_store.flush", lambda: None)

    metadata = run_local_session(
        mode="video_segments",
        input_path=input_dir,
        selected_detectors=["video_metrics"],
    )

    session_dir = (tmp_path / "sessions") / metadata.session_id
    progress = json.loads((session_dir / "progress.json").read_text(encoding="utf-8"))
    results_lines = (session_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()

    assert metadata.status == "cancelled"
    assert progress["status"] == "cancelled"
    assert progress["status_reason"] == "cancel_requested"
    assert progress["status_detail"] == "Cancellation requested by client"
    assert progress["processed_count"] == 1
    assert len(results_lines) == 1


def test_run_local_session_persists_runtime_failure_progress_details(
    monkeypatch, tmp_path: Path
) -> None:
    """A detector/runtime failure should persist failed progress diagnostics."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")

    input_dir = tmp_path / "segments"
    input_dir.mkdir()
    (input_dir / "segment_0001.ts").write_bytes(b"aa")

    def fake_run_enabled_analyzers_bundle(
        file_path: Path,
        prefix: str,
        mode: str,
        session_id: str,
        selected_analyzers: set[str] | None = None,
        persist_to_store: bool = True,
    ) -> dict[str, list[dict[str, object]]]:
        _ = (file_path, prefix, mode, session_id, selected_analyzers, persist_to_store)
        raise ValueError("simulated analyzer failure")

    monkeypatch.setattr(
        "session_runner.run_enabled_analyzers_bundle",
        fake_run_enabled_analyzers_bundle,
    )

    with pytest.raises(ValueError, match="simulated analyzer failure"):
        run_local_session(
            mode="video_segments",
            input_path=input_dir,
            selected_detectors=["video_metrics"],
            session_id="session-runtime-failure",
        )

    snapshot = read_session_snapshot("session-runtime-failure")

    assert snapshot["session"]["status"] == "failed"
    assert snapshot["progress"]["status"] == "failed"
    assert snapshot["progress"]["status_reason"] == "session_runtime_error"
    assert snapshot["progress"]["status_detail"] == "simulated analyzer failure"


def test_run_local_session_persists_validation_failure_progress_details(
    monkeypatch, tmp_path: Path
) -> None:
    """A source validation failure should still persist failed session progress."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    missing_input = tmp_path / "missing-segments"

    with pytest.raises(OSError, match="Input path does not exist"):
        run_local_session(
            mode="video_segments",
            input_path=missing_input,
            selected_detectors=["video_metrics"],
            session_id="session-validation-failure",
        )

    snapshot = read_session_snapshot("session-validation-failure")

    assert snapshot["session"]["status"] == "failed"
    assert snapshot["progress"]["status"] == "failed"
    assert snapshot["progress"]["status_reason"] == "validation_failed"
    assert "Input path does not exist" in str(snapshot["progress"]["status_detail"])


def test_run_local_session_with_no_selected_detectors_runs_none(
    monkeypatch, tmp_path: Path
) -> None:
    """An explicit empty detector selection should mean "run none", not "run all"."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")

    input_dir = tmp_path / "segments"
    input_dir.mkdir()
    (input_dir / "segment_0001.ts").write_bytes(b"aa")

    observed: dict[str, object] = {}

    def fake_run_enabled_analyzers_bundle(
        file_path: Path,
        prefix: str,
        mode: str,
        session_id: str,
        selected_analyzers: set[str] | None = None,
        persist_to_store: bool = True,
    ) -> dict[str, list[dict[str, object]]]:
        _ = (file_path, prefix, mode, session_id, persist_to_store)
        observed["selected_analyzers"] = selected_analyzers
        return {"results": [], "alerts": []}

    monkeypatch.setattr(
        "session_runner.run_enabled_analyzers_bundle",
        fake_run_enabled_analyzers_bundle,
    )
    monkeypatch.setattr("session_runner.black_frame_store.flush", lambda: None)
    monkeypatch.setattr("session_runner.blur_metrics_store.flush", lambda: None)

    metadata = run_local_session(
        mode="video_segments",
        input_path=input_dir,
        selected_detectors=[],
    )

    assert metadata.status == "completed"
    assert observed["selected_analyzers"] == set()


def test_discover_input_files_prefers_playlist_order_for_video_segments(
    tmp_path: Path,
) -> None:
    """Segment discovery should follow playlist order instead of filesystem mtime order."""
    from session_runner import discover_input_files

    input_dir = tmp_path / "segments"
    input_dir.mkdir()
    first = input_dir / "segment_0001.ts"
    second = input_dir / "segment_0002.ts"
    third = input_dir / "segment_0003.ts"
    first.write_bytes(b"aa")
    second.write_bytes(b"bb")
    third.write_bytes(b"cc")
    (input_dir / "index.m3u8").write_text(
        "\n".join(
            [
                "#EXTM3U",
                "#EXTINF:1.0,",
                "segment_0003.ts",
                "#EXTINF:1.0,",
                "segment_0001.ts",
                "#EXTINF:1.0,",
                "segment_0002.ts",
            ]
        ),
        encoding="utf-8",
    )

    discovered = discover_input_files("video_segments", input_dir)

    assert [path.name for path in discovered] == [
        "segment_0003.ts",
        "segment_0001.ts",
        "segment_0002.ts",
    ]


def test_discover_input_files_accepts_playlist_file_for_video_segments(
    tmp_path: Path,
) -> None:
    """A direct HLS playlist input should expand to its referenced segment files."""
    from session_runner import discover_input_files

    input_dir = tmp_path / "segments"
    input_dir.mkdir()
    (input_dir / "segment_0001.ts").write_bytes(b"aa")
    playlist_path = input_dir / "index.m3u8"
    playlist_path.write_text(
        "\n".join(["#EXTM3U", "#EXTINF:1.0,", "segment_0001.ts"]),
        encoding="utf-8",
    )

    discovered = discover_input_files("video_segments", playlist_path)

    assert [path.name for path in discovered] == ["segment_0001.ts"]


def test_discover_input_files_returns_empty_for_malformed_playlist_file(
    tmp_path: Path,
) -> None:
    """A malformed direct playlist should degrade to no segments instead of becoming input."""
    from session_runner import discover_input_files

    input_dir = tmp_path / "segments"
    input_dir.mkdir()
    playlist_path = input_dir / "index.m3u8"
    playlist_path.write_text("not-a-playlist", encoding="utf-8")

    discovered = discover_input_files("video_segments", playlist_path)

    assert discovered == []


def test_discover_input_files_ignores_playlist_entries_outside_root(
    tmp_path: Path,
) -> None:
    """Playlist-based discovery should ignore traversal-style segment references."""
    from session_runner import discover_input_files

    input_dir = tmp_path / "segments"
    input_dir.mkdir()
    outside = tmp_path / "outside.ts"
    outside.write_bytes(b"video")
    playlist_path = input_dir / "index.m3u8"
    playlist_path.write_text(
        "\n".join(["#EXTM3U", "#EXTINF:1.0,", "../outside.ts"]),
        encoding="utf-8",
    )

    discovered = discover_input_files("video_segments", input_dir)

    assert discovered == []


def test_discover_input_files_rejects_oversized_segment_from_playlist(
    monkeypatch, tmp_path: Path,
) -> None:
    """Playlist-driven discovery should still enforce per-segment size limits."""
    from session_runner import discover_input_files

    input_dir = tmp_path / "segments"
    input_dir.mkdir()
    segment_path = input_dir / "segment_0001.ts"
    segment_path.write_bytes(b"video")
    playlist_path = input_dir / "index.m3u8"
    playlist_path.write_text(
        "\n".join(["#EXTM3U", "#EXTINF:1.0,", "segment_0001.ts"]),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "LOCAL_MEDIA_MAX_BYTES", 1)

    try:
        discover_input_files("video_segments", input_dir)
    except ValueError as error:
        assert "exceeds size limit" in str(error)
    else:
        raise AssertionError("Expected oversized playlist segment to be rejected")


def test_discover_input_slices_expands_video_files_into_one_second_windows(
    monkeypatch, tmp_path: Path
) -> None:
    """Video files should be expanded into temporal analysis slices."""
    from session_runner import discover_input_slices

    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video")
    monkeypatch.setattr("session_runner._probe_video_duration", lambda file_path: 2.4)

    slices = discover_input_slices("video_files", video_path)

    assert len(slices) == 3
    assert slices[0].source_group == video_path.name
    assert slices[0].source_name == f"{video_path.name} @ 00:00"
    assert slices[0].window_start_sec == 0.0
    assert slices[0].window_duration_sec == 1.0
    assert slices[2].window_start_sec == 2.0
    assert slices[2].window_duration_sec == 0.4


def test_discover_input_slices_routes_api_streams_through_loader_seam(
    monkeypatch, tmp_path: Path
) -> None:
    """api_stream slice discovery should use the dedicated loader seam."""
    observed: dict[str, object] = {}
    live_slice = AnalysisSlice(
        file_path=tmp_path / "live-window-001.ts",
        source_group="stream-a",
        source_name="live-window-001.ts",
        window_index=0,
    )
    live_slice.file_path.write_bytes(b"ts")

    class ObservedLoader(StaticApiStreamLoader):
        def connect(self, source) -> None:
            observed["source"] = source
            super().connect(source)

        def close(self) -> None:
            observed["closed"] = True
            super().close()

    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: ObservedLoader([live_slice]),
    )

    slices = session_runner.discover_input_slices(
        "api_stream",
        "https://example.com/live/playlist.m3u8",
    )

    assert slices == [live_slice]
    assert observed["source"] == build_api_stream_source_contract(
        "https://example.com/live/playlist.m3u8"
    )
    assert observed["closed"] is True


def test_run_local_session_keeps_snapshot_contract_when_fake_loader_skips_bad_live_events(
    monkeypatch, tmp_path: Path
) -> None:
    """Live ingestion changes should not change the persisted session snapshot model."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")

    stream_source = build_api_stream_source_contract("https://example.com/live/playlist.m3u8")
    for index in range(3):
        (tmp_path / f"live-window-{index:03d}.ts").write_bytes(b"ts")

    fake_loader = FakeApiStreamLoader(
        [
            FakeApiStreamEvent(
                kind="chunk",
                chunk_index=0,
                current_item="live-window-000.ts",
                file_path=tmp_path / "live-window-000.ts",
            ),
            FakeApiStreamEvent(
                kind="temporary_failure",
                chunk_index=1,
                current_item="live-window-001.ts",
                message="temporary fetch timeout",
            ),
            FakeApiStreamEvent(
                kind="chunk",
                chunk_index=1,
                current_item="live-window-001.ts",
                file_path=tmp_path / "live-window-001.ts",
            ),
            FakeApiStreamEvent(
                kind="chunk",
                chunk_index=1,
                current_item="live-window-001.ts",
                file_path=tmp_path / "live-window-001.ts",
            ),
            FakeApiStreamEvent(
                kind="malformed_chunk",
                chunk_index=3,
                current_item="bad-window.ts",
                file_path=tmp_path / "live-window-002.ts",
            ),
            FakeApiStreamEvent(
                kind="chunk",
                chunk_index=2,
                current_item="live-window-002.ts",
                file_path=tmp_path / "live-window-002.ts",
            ),
        ]
    )

    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: fake_loader,
    )

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
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    fake_loader = FakeApiStreamLoader(
        [
            FakeApiStreamEvent(
                kind="terminal_failure",
                message="playlist permanently unavailable",
            )
        ]
    )
    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: fake_loader,
    )

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
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    info_logs: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        session_runner.logger,
        "info",
        lambda message, *args: info_logs.append((message, args)),
    )
    (tmp_path / "live-window-000.ts").write_bytes(b"000")
    (tmp_path / "live-window-001.ts").write_bytes(b"001")

    fake_loader = FakeApiStreamLoader(
        [
            FakeApiStreamEvent(
                kind="chunk",
                chunk_index=0,
                current_item="live-window-000.ts",
                file_path=tmp_path / "live-window-000.ts",
            ),
            FakeApiStreamEvent(
                kind="chunk",
                chunk_index=1,
                current_item="live-window-001.ts",
                file_path=tmp_path / "live-window-001.ts",
            ),
        ]
    )
    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: fake_loader,
    )

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

    completion_logs = [args[1] for message, args in info_logs if message == "Completed session %s [%s]"]
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
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    live_file = tmp_path / "live-window-000.ts"
    live_file.write_bytes(b"ts")

    fake_loader = FakeApiStreamLoader(
        [
            FakeApiStreamEvent(
                kind="chunk",
                chunk_index=0,
                current_item="live-window-000.ts",
                file_path=live_file,
            )
        ]
    )
    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: fake_loader,
    )

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


def test_run_local_session_deletes_current_api_stream_temp_file_on_cancel(
    monkeypatch, tmp_path: Path
) -> None:
    """A yielded live chunk should be deleted immediately when cancel stops the session."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
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
    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: StaticApiStreamLoader([slice_]),
    )

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


def test_run_local_session_completes_remote_api_stream_like_session(
    monkeypatch, tmp_path: Path
) -> None:
    """Remote api-stream inputs should progress through live-like slices and complete."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    remote_url = "https://example.com/live/playlist.m3u8"

    slices = _make_live_slices(
        tmp_path,
        source_group="stream-a",
        names=["live-window-001.ts", "live-window-002.ts", "live-window-003.ts"],
    )
    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: StaticApiStreamLoader(slices),
    )

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
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")

    names = ["live-window-001.ts", "live-window-002.ts", "live-window-003.ts"]
    slices = _make_live_slices(tmp_path, source_group="stream-a", names=names)
    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: StaticApiStreamLoader(slices),
    )

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
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")

    slices = _make_live_slices(
        tmp_path,
        source_group="stream-a",
        names=["live-window-001.ts", "live-window-002.ts", "live-window-003.ts"],
    )
    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: StaticApiStreamLoader(slices),
    )

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


def test_run_local_session_tolerates_repeated_temporary_live_chunk_failures(
    monkeypatch, tmp_path: Path
) -> None:
    """Repeated live-chunk detector failures should still allow the session to complete."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")

    names = [f"live-window-{index:03d}.ts" for index in range(1, 9)]
    slices = _make_live_slices(tmp_path, source_group="stream-a", names=names)
    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: StaticApiStreamLoader(slices),
    )

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


def test_run_local_session_live_like_blur_progression_tracks_alert_reentry(
    monkeypatch, tmp_path: Path
) -> None:
    """Live-like slice sequences should persist progress and timed blur alerts."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")

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
    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: StaticApiStreamLoader(slices),
    )

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


def test_run_local_session_marks_remote_api_stream_failed_when_processing_raises(
    monkeypatch, tmp_path: Path
) -> None:
    """Unrecoverable live processing errors should persist failed session state."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    logged: list[tuple[str, tuple[object, ...]]] = []

    slices = _make_live_slices(
        tmp_path,
        source_group="stream-a",
        names=["live-window-001.ts", "live-window-002.ts", "live-window-003.ts"],
    )
    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: StaticApiStreamLoader(slices),
    )

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
                    "payload": {"source_name": analysis_slice.source_name if analysis_slice else None},
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
        raise AssertionError("Expected the session runner to surface the processing failure")


def test_run_local_session_ignores_playlist_corruption_after_slice_discovery(
    monkeypatch, tmp_path: Path
) -> None:
    """Playlist corruption after startup should not destabilize the already discovered run."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")

    input_dir = tmp_path / "segments"
    input_dir.mkdir()
    for index in range(4):
        (input_dir / f"segment_{index:04d}.ts").write_bytes(b"video")
    playlist_path = input_dir / "index.m3u8"
    playlist_path.write_text(
        "\n".join(
            [
                "#EXTM3U",
                "#EXTINF:1.0,",
                "segment_0000.ts",
                "#EXTINF:1.0,",
                "segment_0001.ts",
                "#EXTINF:1.0,",
                "segment_0002.ts",
                "#EXTINF:1.0,",
                "segment_0003.ts",
            ]
        ),
        encoding="utf-8",
    )

    call_count = {"value": 0}

    def fake_run_enabled_analyzers_bundle(
        file_path: Path,
        prefix: str,
        mode: str,
        session_id: str,
        selected_analyzers: set[str] | None = None,
        persist_to_store: bool = True,
        analysis_slice: AnalysisSlice | None = None,
    ) -> dict[str, list[dict[str, object]]]:
        _ = (prefix, mode, selected_analyzers, persist_to_store)
        call_count["value"] += 1
        if call_count["value"] == 1:
            playlist_path.write_text("not a valid playlist anymore", encoding="utf-8")
        return {
            "results": [
                {
                    "session_id": session_id,
                    "detector_id": "video_metrics",
                    "payload": {"source_name": analysis_slice.source_name if analysis_slice else file_path.name},
                }
            ],
            "alerts": [],
        }

    monkeypatch.setattr("session_runner.run_enabled_analyzers_bundle", fake_run_enabled_analyzers_bundle)
    monkeypatch.setattr("session_runner.black_frame_store.flush", lambda: None)
    monkeypatch.setattr("session_runner.blur_metrics_store.flush", lambda: None)

    metadata = run_local_session(
        mode="video_segments",
        input_path=input_dir,
        selected_detectors=["video_metrics"],
        session_id="session-playlist-mutation",
    )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == 4
    assert [event["payload"]["source_name"] for event in snapshot["results"]] == [
        "segment_0000.ts",
        "segment_0001.ts",
        "segment_0002.ts",
        "segment_0003.ts",
    ]


def test_run_local_session_http_hls_api_stream_completes_end_to_end(
    monkeypatch, tmp_path: Path
) -> None:
    """A real local HTTP HLS run should complete incrementally and persist results and alerts."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(session_runner, "get_api_stream_loader", lambda session_id=None: HttpHlsApiStreamLoader(session_id or "session-api-http-complete"))
    monkeypatch.setattr("stream_loader.time.sleep", lambda seconds: None)

    scores = {
        "segment_000.ts": 0.82,
        "segment_001.ts": 0.79,
        "segment_002.ts": 0.60,
        "segment_003.ts": 0.40,
        "segment_004.ts": 0.42,
        "segment_005.ts": 0.45,
        "segment_006.ts": 0.81,
        "segment_007.ts": 0.77,
    }
    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer(scores),
        supported_modes=("api_stream",),
    )

    routes = {
        "/live/index.m3u8": [
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:0",
                        "#EXTINF:1.0,",
                        "segment_000.ts",
                        "#EXTINF:1.0,",
                        "segment_001.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:2",
                        "#EXTINF:1.0,",
                        "segment_002.ts",
                        "#EXTINF:1.0,",
                        "segment_003.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:4",
                        "#EXTINF:1.0,",
                        "segment_004.ts",
                        "#EXTINF:1.0,",
                        "segment_005.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:6",
                        "#EXTINF:1.0,",
                        "segment_006.ts",
                        "#EXTINF:1.0,",
                        "segment_007.ts",
                        "#EXT-X-ENDLIST",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
        ],
    }
    for index in range(8):
        routes[f"/live/segment_{index:03d}.ts"] = (
            200,
            f"segment-{index}".encode("utf-8"),
            "video/mp2t",
        )

    with _serve_local_hls(routes) as base_url:
        metadata = run_local_session(
            mode="api_stream",
            input_path=f"{base_url}/live/index.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-http-complete",
        )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["session"]["status"] == "completed"
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == 8
    assert snapshot["progress"]["current_item"] == "segment_007.ts"
    assert len(snapshot["results"]) == 8
    assert snapshot["progress"]["alert_count"] == 2
    assert len(snapshot["alerts"]) == 2


def test_run_local_session_http_hls_api_stream_cancels_end_to_end(
    monkeypatch, tmp_path: Path
) -> None:
    """A real local HTTP HLS run should persist a cancelled snapshot once the user stops it."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(session_runner, "get_api_stream_loader", lambda session_id=None: HttpHlsApiStreamLoader(session_id or "session-api-http-cancel"))
    monkeypatch.setattr("stream_loader.time.sleep", lambda seconds: None)

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
        _ = (file_path, prefix, source_group)
        if not cancel_requested["done"]:
            cancel_requested["done"] = True
            from session_io import request_session_cancel

            request_session_cancel("session-api-http-cancel")
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

    playlist_text = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-TARGETDURATION:1",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXTINF:1.0,",
            "segment_000.ts",
            "#EXTINF:1.0,",
            "segment_001.ts",
            "#EXTINF:1.0,",
            "segment_002.ts",
            "#EXT-X-ENDLIST",
        ]
    )
    routes = {
        "/live/index.m3u8": (200, playlist_text, "application/vnd.apple.mpegurl"),
        "/live/segment_000.ts": (200, b"000", "video/mp2t"),
        "/live/segment_001.ts": (200, b"001", "video/mp2t"),
        "/live/segment_002.ts": (200, b"002", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        metadata = run_local_session(
            mode="api_stream",
            input_path=f"{base_url}/live/index.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-http-cancel",
        )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "cancelled"
    assert snapshot["session"]["status"] == "cancelled"
    assert snapshot["progress"]["status"] == "cancelled"
    assert snapshot["progress"]["processed_count"] == 1
    assert len(snapshot["results"]) == 1
    assert snapshot["progress"]["status_reason"] == "cancel_requested"
    assert snapshot["progress"]["status_detail"] == "Cancellation requested after iteration"


def test_run_local_session_http_hls_api_stream_persists_failed_snapshot_on_loader_budget_exhaustion(
    monkeypatch, tmp_path: Path
) -> None:
    """A real local HTTP HLS loader failure should persist a failed live-session snapshot."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_MAX_RECONNECT_ATTEMPTS", 1)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(session_runner, "get_api_stream_loader", lambda session_id=None: HttpHlsApiStreamLoader(session_id or "session-api-http-failed"))
    monkeypatch.setattr("stream_loader.time.sleep", lambda seconds: None)

    routes = {
        "/live/index.m3u8": [
            (503, "busy", "text/plain"),
            (503, "busy", "text/plain"),
        ],
    }

    with _serve_local_hls(routes) as base_url:
        with pytest.raises(ValueError, match="reconnect budget exhausted"):
            run_local_session(
                mode="api_stream",
                input_path=f"{base_url}/live/index.m3u8",
                selected_detectors=["video_blur"],
                session_id="session-api-http-failed",
            )

    snapshot = read_session_snapshot("session-api-http-failed")

    assert snapshot["session"]["status"] == "failed"
    assert snapshot["progress"]["status"] == "failed"
    assert snapshot["progress"]["processed_count"] == 0
    assert snapshot["results"] == []
    assert snapshot["alerts"] == []
    assert snapshot["progress"]["status_reason"] == "source_unreachable"
    assert "reconnect_budget_exhausted" in str(snapshot["progress"]["status_detail"])


def test_run_local_session_logs_api_stream_failure_summary(
    monkeypatch, tmp_path: Path
) -> None:
    """Failed api_stream runs should log one terminal transport/session summary for operators."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_MAX_RECONNECT_ATTEMPTS", 1)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: HttpHlsApiStreamLoader(session_id or "session-api-log-failed"),
    )
    monkeypatch.setattr("stream_loader.time.sleep", lambda seconds: None)

    error_logs: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        session_runner.logger,
        "error",
        lambda message, *args: error_logs.append((message, args)),
    )

    routes = {
        "/live/index.m3u8": [
            (503, "busy", "text/plain"),
            (503, "busy", "text/plain"),
        ],
    }

    with _serve_local_hls(routes) as base_url:
        with pytest.raises(ValueError, match="reconnect budget exhausted"):
            run_local_session(
                mode="api_stream",
                input_path=f"{base_url}/live/index.m3u8",
                selected_detectors=["video_blur"],
                session_id="session-api-log-failed",
            )

    failure_logs = [args[2] for message, args in error_logs if message == "Session %s failed: %s [%s]"]
    assert failure_logs
    assert any("session_end_reason='terminal_failure'" in str(entry) for entry in failure_logs)
    assert any("source_url_class='hls_playlist_url'" in str(entry) for entry in failure_logs)
    assert any("reconnect_budget_exhaustion_count=1" in str(entry) for entry in failure_logs)
    assert any(
        "terminal_failure_reason='reconnect_budget_exhausted:api_stream upstream returned HTTP 503'"
        in str(entry)
        for entry in failure_logs
    )
    assert any("temp_cleanup_success_count=0" in str(entry) for entry in failure_logs)
    assert any("temp_cleanup_failure_count=0" in str(entry) for entry in failure_logs)


def test_run_local_session_http_hls_api_stream_stops_cleanly_after_idle_poll_budget(
    monkeypatch, tmp_path: Path
) -> None:
    """A non-ENDLIST live run should complete cleanly once the bounded idle poll policy is exhausted."""
    monkeypatch.setattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", True)
    monkeypatch.setattr(config, "API_STREAM_POLL_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_RECONNECT_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(config, "API_STREAM_MAX_IDLE_PLAYLIST_POLLS", 1)
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path / "sessions")
    monkeypatch.setattr(config, "API_STREAM_TEMP_ROOT", tmp_path / "api-temp")
    monkeypatch.setattr(
        session_runner,
        "get_api_stream_loader",
        lambda session_id=None: HttpHlsApiStreamLoader(
            session_id or "session-api-http-idle-stop"
        ),
    )
    monkeypatch.setattr("stream_loader.time.sleep", lambda seconds: None)

    _patch_processor_with_analyzer(
        monkeypatch,
        analyzer_name="video_blur",
        store_name="blur_metrics",
        analyzer=_build_blur_analyzer(
            {
                "segment_000.ts": 0.82,
                "segment_001.ts": 0.79,
            }
        ),
        supported_modes=("api_stream",),
    )

    routes = {
        "/live/index.m3u8": [
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:0",
                        "#EXTINF:1.0,",
                        "segment_000.ts",
                        "#EXTINF:1.0,",
                        "segment_001.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
            (
                200,
                "\n".join(
                    [
                        "#EXTM3U",
                        "#EXT-X-TARGETDURATION:1",
                        "#EXT-X-MEDIA-SEQUENCE:0",
                        "#EXTINF:1.0,",
                        "segment_000.ts",
                        "#EXTINF:1.0,",
                        "segment_001.ts",
                    ]
                ),
                "application/vnd.apple.mpegurl",
            ),
        ],
        "/live/segment_000.ts": (200, b"000", "video/mp2t"),
        "/live/segment_001.ts": (200, b"001", "video/mp2t"),
    }

    with _serve_local_hls(routes) as base_url:
        metadata = run_local_session(
            mode="api_stream",
            input_path=f"{base_url}/live/index.m3u8",
            selected_detectors=["video_blur"],
            session_id="session-api-http-idle-stop",
        )

    snapshot = read_session_snapshot(metadata.session_id)

    assert metadata.status == "completed"
    assert snapshot["session"]["status"] == "completed"
    assert snapshot["progress"]["status"] == "completed"
    assert snapshot["progress"]["processed_count"] == 2
    assert snapshot["progress"]["current_item"] == "segment_001.ts"
    assert len(snapshot["results"]) == 2
    assert snapshot["progress"]["status_reason"] == "completed"
    assert snapshot["progress"]["status_detail"] == "Idle poll budget exhausted"


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
