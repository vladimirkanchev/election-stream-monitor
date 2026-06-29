"""Storage-neutral write-path tests for session runner helpers."""

from dataclasses import replace
from typing import cast

import session_runner_execution
import session_runner_lifecycle
import session_runner_terminal
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
    """Small in-memory store that records write ordering for runner tests."""

    def __init__(self) -> None:
        self.metadata_writes: list[SessionMetadata] = []
        self.progress_writes: list[SessionProgress] = []
        self.result_writes: list[ResultEvent] = []

    def session_exists(self, session_id: str) -> bool:
        """Return whether metadata was written for the requested session."""
        return self._latest_metadata(session_id) is not None

    def read_snapshot(self, session_id: str) -> SessionSnapshotPayload:
        """Return a compact snapshot from recorded writes."""
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
    """Build one runner-owned metadata payload."""
    return SessionMetadata(
        session_id=session_id,
        mode="video_files",
        input_path="/tmp/input.mp4",
        selected_detectors=["video_metrics"],
        status=cast(SessionStatus, status),
    )


def test_lifecycle_writes_metadata_and_latest_progress_through_store() -> None:
    """Lifecycle transitions should write through the injected session store."""
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


def test_terminal_outcome_writes_terminal_metadata_and_latest_progress_through_store() -> None:
    """Terminal persistence should update metadata and overwrite progress via the store."""
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
