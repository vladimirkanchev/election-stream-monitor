"""Storage-neutral runner-write tests for latest progress, metadata, and results."""

from dataclasses import replace
from pathlib import Path
from typing import cast

import session_runner_execution
import session_runner_lifecycle
import session_runner_terminal
from analyzer_contract import AnalysisSlice
from session_models import ResultEvent, SessionMetadata, SessionProgress, SessionStatus
from session_store import (
    ResultEventPayload,
    SessionMetadataPayload,
    SessionProgressPayload,
    SessionSnapshotPayload,
    build_empty_session_snapshot_payload,
    build_session_snapshot_payload,
)


class RecordingSessionStore:
    """Small in-memory store that records runner writes in contract order."""

    def __init__(self) -> None:
        self.metadata_writes: list[SessionMetadata] = []
        self.progress_writes: list[SessionProgress] = []
        self.result_writes: list[ResultEvent] = []
        self.cancelled_session_ids: set[str] = set()

    def session_exists(self, session_id: str) -> bool:
        """Return whether metadata was written for the requested session."""
        return self._latest_metadata(session_id) is not None

    def read_snapshot(self, session_id: str) -> SessionSnapshotPayload:
        """Assemble one public snapshot from the latest recorded writes."""
        metadata = self._latest_metadata(session_id)
        progress = self._latest_progress(session_id)
        results = self.read_results(session_id)
        if metadata is None:
            return build_empty_session_snapshot_payload()
        return build_session_snapshot_payload(
            session=cast(SessionMetadataPayload, metadata.to_dict()),
            progress=cast(SessionProgressPayload, progress.to_dict()) if progress else None,
            alerts=[],
            results=results,
        )

    def read_results(self, session_id: str) -> list[ResultEventPayload]:
        """Return result writes in append order."""
        return [
            cast(ResultEventPayload, result.to_dict())
            for result in self.result_writes
            if result.session_id == session_id
        ]

    def write_metadata(self, metadata: SessionMetadata) -> None:
        """Record one metadata write."""
        metadata.validate()
        self.metadata_writes.append(metadata)

    def write_progress(self, progress: SessionProgress) -> None:
        """Record one latest-progress write."""
        progress.validate()
        self.progress_writes.append(progress)

    def append_result(self, event: ResultEvent) -> None:
        """Record one result append."""
        self.result_writes.append(event)

    def request_cancel(self, session_id: str) -> None:
        """Record current cancel intent for one session."""
        self.cancelled_session_ids.add(session_id)

    def is_cancel_requested(self, session_id: str) -> bool:
        """Return whether current cancel intent was recorded for one session."""
        return session_id in self.cancelled_session_ids

    def _latest_metadata(self, session_id: str) -> SessionMetadata | None:
        """Return the latest recorded metadata write for one session."""
        return next(
            (
                metadata
                for metadata in reversed(self.metadata_writes)
                if metadata.session_id == session_id
            ),
            None,
        )

    def _latest_progress(self, session_id: str) -> SessionProgress | None:
        """Return the latest recorded progress write for one session."""
        return next(
            (
                progress
                for progress in reversed(self.progress_writes)
                if progress.session_id == session_id
            ),
            None,
        )


def _metadata(session_id: str, *, status: str = "pending") -> SessionMetadata:
    """Build one runner-owned session metadata payload."""
    return SessionMetadata(
        session_id=session_id,
        mode="video_files",
        input_path="/tmp/input.mp4",
        selected_detectors=["video_metrics"],
        status=cast(SessionStatus, status),
    )


def _analysis_slice(source_name: str, *, window_index: int) -> AnalysisSlice:
    """Build one local segment slice for runner execution tests."""
    return AnalysisSlice(
        file_path=Path(f"/tmp/{source_name}"),
        source_group="local_segments",
        source_name=source_name,
        window_index=window_index,
    )


def _result_bundle(session_id: str, *, window_index: int) -> dict[str, list[dict[str, object]]]:
    """Return one analyzer bundle with a single metrics result and no alerts."""
    return {
        "results": [
            {
                "session_id": session_id,
                "detector_id": "video_metrics",
                "payload": {"window_index": window_index},
            }
        ],
        "alerts": [],
    }


def _running_progress(
    metadata: SessionMetadata,
    *,
    total_count: int,
    processed_count: int = 0,
    current_item: str | None = None,
) -> SessionProgress:
    """Build a running latest-progress snapshot for storage-neutral runner tests."""
    return replace(
        SessionProgress.initial(session_id=metadata.session_id, total_count=total_count),
        status="running",
        processed_count=processed_count,
        current_item=current_item,
        status_reason="running",
    )


def test_lifecycle_writes_metadata_and_latest_progress_through_store() -> None:
    """Lifecycle transitions should persist metadata and latest progress through the store."""
    store = RecordingSessionStore()

    metadata, progress = session_runner_lifecycle.initialize_pending_session(
        mode="video_files",
        input_path="/tmp/input.mp4",
        selected_detectors=["video_metrics"],
        session_id="session-store-lifecycle",
        session_store=store,
    )
    running_metadata, running_progress = session_runner_lifecycle.start_running_session(
        metadata,
        progress,
        total_count=3,
        session_store=store,
    )

    assert [metadata.status for metadata in store.metadata_writes] == ["pending", "running"]
    assert [progress.status for progress in store.progress_writes] == ["pending", "pending", "running"]
    assert running_metadata.status == "running"
    assert running_progress.status == "running"


def test_bundle_results_append_through_store_in_order() -> None:
    """Result writes should keep analyzer-bundle append order."""
    store = RecordingSessionStore()

    session_runner_execution.persist_bundle_events(
        {
            "results": [
                {
                    "session_id": "session-store-results",
                    "detector_id": "video_metrics",
                    "payload": {"window_index": 0},
                },
                {
                    "session_id": "session-store-results",
                    "detector_id": "video_blur",
                    "payload": {"window_index": 1},
                },
            ],
            "alerts": [],
        },
        session_store=store,
    )

    assert [result.detector_id for result in store.result_writes] == [
        "video_metrics",
        "video_blur",
    ]
    assert store.read_results("session-store-results")[-1] == {
        "session_id": "session-store-results",
        "detector_id": "video_blur",
        "payload": {"window_index": 1},
    }


def test_execution_snapshot_keeps_latest_progress_while_results_keep_history() -> None:
    """Execution should keep one latest progress snapshot while results remain ordered history."""
    store = RecordingSessionStore()
    metadata = _metadata("session-store-execution", status="running")
    progress = _running_progress(metadata, total_count=2)
    input_slices = [
        _analysis_slice("segment_0001.ts", window_index=0),
        _analysis_slice("segment_0002.ts", window_index=1),
    ]

    def bundle_runner(
        *, analysis_slice: AnalysisSlice, **_: object
    ) -> dict[str, list[dict[str, object]]]:
        return _result_bundle(metadata.session_id, window_index=analysis_slice.window_index)

    updated_metadata, updated_progress = session_runner_execution.process_discovered_slices(
        metadata=metadata,
        progress=progress,
        mode="video_segments",
        session_id=metadata.session_id,
        selected_detectors=metadata.selected_detectors,
        input_slices=input_slices,
        bundle_runner=bundle_runner,
        session_store=store,
    )

    snapshot = store.read_snapshot(metadata.session_id)

    assert len(store.progress_writes) == 3
    assert [result["payload"]["window_index"] for result in snapshot["results"]] == [0, 1]
    assert snapshot["progress"] == updated_progress.to_dict()
    assert snapshot["progress"]["processed_count"] == 2
    assert snapshot["progress"]["status"] == "completed"
    assert updated_metadata.status == "completed"


def test_process_discovered_slices_reads_cancel_state_from_passed_session_store() -> None:
    """Execution should read cooperative cancel intent from the provided store."""
    store = RecordingSessionStore()
    metadata = _metadata("session-store-cancel-check", status="running")
    progress = _running_progress(metadata, total_count=1)
    input_slices = [_analysis_slice("segment_0001.ts", window_index=0)]
    store.write_metadata(metadata)
    store.write_progress(progress)
    store.request_cancel(metadata.session_id)

    finalizer_calls: list[dict[str, object]] = []

    def fake_finalizer(**kwargs):
        finalizer_calls.append(kwargs)
        return kwargs["metadata"], kwargs["progress"]

    bundle_called = {"value": False}

    def bundle_runner(**_: object) -> dict[str, list[dict[str, object]]]:
        bundle_called["value"] = True
        return _result_bundle(metadata.session_id, window_index=0)

    updated_metadata, updated_progress = session_runner_execution.process_discovered_slices(
        metadata=metadata,
        progress=progress,
        mode="video_files",
        session_id=metadata.session_id,
        selected_detectors=metadata.selected_detectors,
        input_slices=input_slices,
        bundle_runner=bundle_runner,
        progress_builder=lambda **kwargs: progress,
        finalizer=fake_finalizer,
        session_store=store,
    )

    assert updated_metadata is metadata
    assert updated_progress is progress
    assert bundle_called["value"] is False
    assert finalizer_calls[-1]["status"] == "cancelled"


def test_execution_skips_timestamp_only_progress_rewrites_during_slice_processing() -> None:
    """Execution should skip redundant progress writes when only the timestamp changes."""
    store = RecordingSessionStore()
    metadata = _metadata("session-store-noop-progress", status="running")
    progress = replace(
        _running_progress(
            metadata,
            total_count=1,
            processed_count=1,
            current_item="segment_0001.ts",
        ),
        latest_result_detector="video_metrics",
        latest_result_detectors=["video_metrics"],
        last_updated_utc="2026-06-30 10:00:01",
    )
    input_slices = [_analysis_slice("segment_0001.ts", window_index=0)]

    def bundle_runner(**_: object) -> dict[str, list[dict[str, object]]]:
        return _result_bundle(metadata.session_id, window_index=0)

    def no_op_progress_builder(**_: object) -> SessionProgress:
        return replace(progress, last_updated_utc="2026-06-30 10:00:02")

    _, updated_progress = session_runner_execution.process_discovered_slices(
        metadata=metadata,
        progress=progress,
        mode="video_segments",
        session_id=metadata.session_id,
        selected_detectors=metadata.selected_detectors,
        input_slices=input_slices,
        bundle_runner=bundle_runner,
        progress_builder=no_op_progress_builder,
        session_store=store,
    )

    assert [written.status for written in store.progress_writes] == ["completed"]
    assert updated_progress.status == "completed"


def test_terminal_outcome_writes_terminal_metadata_and_latest_progress_through_store() -> None:
    """Terminal persistence should update metadata and replace latest progress via the store."""
    store = RecordingSessionStore()
    metadata = _metadata("session-store-terminal", status="running")
    progress = replace(
        SessionProgress.initial(session_id=metadata.session_id, total_count=2),
        processed_count=2,
    )

    updated_metadata, updated_progress = session_runner_terminal.finalize_session_outcome(
        metadata=metadata,
        progress=progress,
        status="completed",
        source_kind="video_files",
        flush_stores=False,
        log_level="info",
        log_message="Completed session %s [%s]",
        session_store=store,
    )

    assert store.metadata_writes == [updated_metadata]
    assert store.progress_writes == [updated_progress]
    assert updated_metadata.status == "completed"
    assert updated_progress.status == "completed"
