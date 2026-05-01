"""Tests for local `session_runner` lifecycle and discovery behavior.

These cases primarily exercise:

- orchestration in `src/session_runner.py`
- local file/slice expansion seams now owned by `src/session_runner_discovery.py`

They intentionally stay separate from the `api_stream` runner files so the
local-mode contract remains easy to scan.
"""

import json
from pathlib import Path

import config
import pytest
import session_runner
from analyzer_contract import AnalysisSlice
from session_io import read_session_snapshot
from session_runner import run_local_session
from stream_loader import StaticApiStreamLoader, build_api_stream_source_contract
from tests.session_runner_api_stream_test_support import (
    _configure_runner_output_paths,
    _patch_runner_bundle,
)


def _make_segment_input_dir(tmp_path: Path, *names: str) -> Path:
    input_dir = tmp_path / "segments"
    input_dir.mkdir()
    for name in names:
        (input_dir / name).write_bytes(b"aa")
    return input_dir


def test_run_local_session_writes_incremental_files(
    monkeypatch, tmp_path: Path
) -> None:
    """A normal session should persist metadata, progress, and result events incrementally."""
    _configure_runner_output_paths(monkeypatch, tmp_path)
    input_dir = _make_segment_input_dir(tmp_path, "segment_0001.ts", "segment_0002.ts")

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

    _patch_runner_bundle(monkeypatch, fake_run_enabled_analyzers_bundle)

    metadata = run_local_session(
        mode="video_segments",
        input_path=input_dir,
        selected_detectors=["video_metrics"],
    )

    session_dir = (tmp_path / "sessions") / metadata.session_id
    progress = json.loads((session_dir / "progress.json").read_text(encoding="utf-8"))
    results_lines = (
        session_dir / "results.jsonl"
    ).read_text(encoding="utf-8").splitlines()

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
    _configure_runner_output_paths(monkeypatch, tmp_path)
    input_dir = _make_segment_input_dir(tmp_path, "segment_0001.ts", "segment_0002.ts")

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

    _patch_runner_bundle(monkeypatch, fake_run_enabled_analyzers_bundle)

    metadata = run_local_session(
        mode="video_segments",
        input_path=input_dir,
        selected_detectors=["video_metrics"],
    )

    session_dir = (tmp_path / "sessions") / metadata.session_id
    progress = json.loads((session_dir / "progress.json").read_text(encoding="utf-8"))
    results_lines = (
        session_dir / "results.jsonl"
    ).read_text(encoding="utf-8").splitlines()

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
    _configure_runner_output_paths(monkeypatch, tmp_path)
    input_dir = _make_segment_input_dir(tmp_path, "segment_0001.ts")

    def fake_run_enabled_analyzers_bundle(
        file_path: Path,
        prefix: str,
        mode: str,
        session_id: str,
        selected_analyzers: set[str] | None = None,
        persist_to_store: bool = True,
    ) -> dict[str, list[dict[str, object]]]:
        _ = (
            file_path,
            prefix,
            mode,
            session_id,
            selected_analyzers,
            persist_to_store,
        )
        raise ValueError("simulated analyzer failure")

    _patch_runner_bundle(monkeypatch, fake_run_enabled_analyzers_bundle, patch_flushes=False)

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
    _configure_runner_output_paths(monkeypatch, tmp_path)
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
    _configure_runner_output_paths(monkeypatch, tmp_path)
    input_dir = _make_segment_input_dir(tmp_path, "segment_0001.ts")

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

    _patch_runner_bundle(monkeypatch, fake_run_enabled_analyzers_bundle)

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
    monkeypatch, tmp_path: Path
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


def test_get_api_stream_loader_delegates_to_public_loader_factory(monkeypatch) -> None:
    """The stable runner wrapper should delegate loader creation unchanged."""
    sentinel_loader = object()
    observed: dict[str, object] = {}

    def fake_create_api_stream_loader(*, session_id=None):
        observed["session_id"] = session_id
        return sentinel_loader

    monkeypatch.setattr(
        session_runner,
        "create_api_stream_loader",
        fake_create_api_stream_loader,
    )

    loader = session_runner.get_api_stream_loader(session_id="session-loader-wrapper")

    assert loader is sentinel_loader
    assert observed["session_id"] == "session-loader-wrapper"


def test_create_session_id_keeps_runner_owned_stable_prefix() -> None:
    """The public session id helper should keep the stable runner-owned format."""
    session_id = session_runner.create_session_id()

    assert session_id.startswith("session-")
    assert len(session_id.split("-")) >= 4
    assert len(session_id.rsplit("-", 1)[-1]) == 8


def test_run_local_session_ignores_playlist_corruption_after_slice_discovery(
    monkeypatch, tmp_path: Path
) -> None:
    """Playlist corruption after startup should not destabilize the already discovered run."""
    _configure_runner_output_paths(monkeypatch, tmp_path)
    input_dir = _make_segment_input_dir(
        tmp_path,
        "segment_0000.ts",
        "segment_0001.ts",
        "segment_0002.ts",
        "segment_0003.ts",
    )
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
                    "payload": {
                        "source_name": (
                            analysis_slice.source_name if analysis_slice else file_path.name
                        )
                    },
                }
            ],
            "alerts": [],
        }

    _patch_runner_bundle(monkeypatch, fake_run_enabled_analyzers_bundle)

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
