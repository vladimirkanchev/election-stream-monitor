"""Storage contract for durable monitoring-session state.

`SessionStore` covers session metadata, latest progress, ordered detector
results, and cancel intent. It does not own alerts, logs, temp media, or
HTTP/HLS replay state.
"""

from __future__ import annotations

from typing import Protocol, TypedDict

from analyzer_contract import InputMode
from session_models import ResultEvent, SessionMetadata, SessionProgress, SessionStatus

SESSION_SNAPSHOT_KEYS = ("session", "progress", "alerts", "results", "latest_result")
RESULT_EVENT_PUBLIC_KEYS = ("session_id", "detector_id", "payload")
RESULT_EVENT_SHARED_PAYLOAD_HINT_KEYS = (
    "timestamp_utc",
    "detector_name",
    "source_name",
    "window_index",
    "window_start_sec",
    "title",
    "message",
    "severity",
)


class SessionMetadataPayload(TypedDict):
    """Session metadata as exposed in snapshot payloads."""

    session_id: str
    mode: InputMode
    input_path: str
    selected_detectors: list[str]
    status: SessionStatus


class SessionProgressPayload(TypedDict):
    """Latest progress snapshot exposed in session payloads."""

    session_id: str
    status: SessionStatus
    processed_count: int
    total_count: int
    current_item: str | None
    latest_result_detector: str | None
    alert_count: int
    last_updated_utc: str
    latest_result_detectors: list[str]
    status_reason: str | None
    status_detail: str | None


class ResultEventPayload(TypedDict):
    """Stored detector result row exposed through snapshot and history reads."""

    session_id: str
    detector_id: str
    payload: dict[str, object]


class SessionSnapshotPayload(TypedDict):
    """Stable session read model shared by API, CLI, bridge, and tests."""

    session: SessionMetadataPayload | None
    progress: SessionProgressPayload | None
    alerts: list[dict[str, object]]
    results: list[ResultEventPayload]
    latest_result: ResultEventPayload | None


def build_latest_result_payload(
    results: list[ResultEventPayload],
) -> ResultEventPayload | None:
    """Return the last valid row from append-ordered result history."""
    return results[-1] if results else None


def build_empty_session_snapshot_payload() -> SessionSnapshotPayload:
    """Return the canonical empty snapshot shape."""
    return {
        "session": None,
        "progress": None,
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def is_missing_session_snapshot(snapshot: SessionSnapshotPayload) -> bool:
    """Return whether a snapshot has no durable session metadata."""
    return snapshot["session"] is None


def build_session_snapshot_payload(
    *,
    session: SessionMetadataPayload | None,
    progress: SessionProgressPayload | None,
    alerts: list[dict[str, object]],
    results: list[ResultEventPayload],
) -> SessionSnapshotPayload:
    """Build a snapshot from validated durable rows.

    Results must already be in append order, and progress is latest-state only.
    """
    return {
        "session": session,
        "progress": progress,
        "alerts": alerts,
        "results": results,
        "latest_result": build_latest_result_payload(results),
    }


class SessionStoreReader(Protocol):
    """Read contract for durable session state."""

    def session_exists(self, session_id: str) -> bool:
        """Return whether durable metadata exists for the session."""
        ...

    def read_snapshot(self, session_id: str) -> SessionSnapshotPayload:
        """Return the stable snapshot shape for one session.

        Missing or unreadable durable data should degrade to the empty shape.
        """
        ...

    def read_results(self, session_id: str) -> list[ResultEventPayload]:
        """Return validated detector results in append order."""
        ...


class SessionStoreWriter(Protocol):
    """Write contract for durable session state."""

    def write_metadata(self, metadata: SessionMetadata) -> None:
        """Persist the authoritative session metadata payload."""
        ...

    def write_progress(self, progress: SessionProgress) -> None:
        """Persist the latest progress payload for one session.

        Stores replace the current read model rather than appending progress
        history. Freshness checks stay above the storage layer.
        """
        ...

    def append_result(self, event: ResultEvent) -> None:
        """Append one detector result while preserving read order."""
        ...


class SessionStoreCancellationControl(Protocol):
    """Minimal contract for durable cooperative-cancel state."""

    def request_cancel(self, session_id: str) -> None:
        """Persist cancel intent for one session."""
        ...

    def is_cancel_requested(self, session_id: str) -> bool:
        """Return whether cancel intent currently exists for the session."""
        ...


class SessionStore(
    SessionStoreReader,
    SessionStoreWriter,
    SessionStoreCancellationControl,
    Protocol,
):
    """Combined contract implemented by concrete session-store backends."""
