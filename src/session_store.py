"""Durable storage contract for monitoring-session state.

`SessionStore` is the boundary for migrating session metadata, latest progress,
and ordered detector results from files to PostgreSQL. It deliberately excludes
runtime artifacts such as logs, temp media, cancel markers, and HTTP/HLS replay
keys.
"""

from __future__ import annotations

from typing import Protocol, TypedDict

from analyzer_contract import InputMode
from session_models import ResultEvent, SessionMetadata, SessionProgress, SessionStatus

SESSION_SNAPSHOT_KEYS = ("session", "progress", "alerts", "results", "latest_result")


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
    """Append-ordered detector result row."""

    session_id: str
    detector_id: str
    payload: dict[str, object]


class SessionSnapshotPayload(TypedDict):
    """Stable session read model consumed by API, CLI, bridge, and tests."""

    session: SessionMetadataPayload | None
    progress: SessionProgressPayload | None
    alerts: list[dict[str, object]]
    results: list[ResultEventPayload]
    latest_result: ResultEventPayload | None


def build_empty_session_snapshot_payload() -> SessionSnapshotPayload:
    """Return the low-level snapshot shape for missing or unreadable sessions.

    Services translate `session is None` into user-facing not-found behavior.
    """
    return {
        "session": None,
        "progress": None,
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def is_missing_session_snapshot(snapshot: SessionSnapshotPayload) -> bool:
    """Return whether the snapshot has no durable session metadata."""
    return snapshot["session"] is None


def build_session_snapshot_payload(
    *,
    session: SessionMetadataPayload | None,
    progress: SessionProgressPayload | None,
    alerts: list[dict[str, object]],
    results: list[ResultEventPayload],
) -> SessionSnapshotPayload:
    """Build a snapshot from validated durable session rows.

    Results must already be in append order. `latest_result` is derived from
    the final result row; progress is the latest payload, not history.
    """
    return {
        "session": session,
        "progress": progress,
        "alerts": alerts,
        "results": results,
        "latest_result": results[-1] if results else None,
    }


class SessionStoreReader(Protocol):
    """Read contract for durable session state.

    Readers expose snapshot semantics without leaking backend layout.
    """

    def session_exists(self, session_id: str) -> bool:
        """Return whether durable metadata exists for the session."""
        ...

    def read_snapshot(self, session_id: str) -> SessionSnapshotPayload:
        """Return the stable snapshot shape for one session.

        Implementations return the empty snapshot shape for missing or
        malformed durable data. Unexpected backend failures may still surface.
        """
        ...

    def read_results(self, session_id: str) -> list[ResultEventPayload]:
        """Return validated detector results in append order.

        PostgreSQL implementations should order by a monotonic field, not only
        by timestamp.
        """
        ...


class SessionStoreWriter(Protocol):
    """Write contract for durable session lifecycle data.

    Lifecycle-specific operations such as start, cancel, and finalize stay in
    runner/service code.
    """

    def write_metadata(self, metadata: SessionMetadata) -> None:
        """Persist the authoritative session metadata payload."""
        ...

    def write_progress(self, progress: SessionProgress) -> None:
        """Persist the latest progress payload for one session.

        This replaces the previous progress read model.
        """
        ...

    def append_result(self, event: ResultEvent) -> None:
        """Append one detector result while preserving read order."""
        ...


class SessionStore(SessionStoreReader, SessionStoreWriter, Protocol):
    """Combined durable session-store contract for concrete backends.

    Alert storage, logs, temp media, cancel markers, and HTTP/HLS replay keys
    remain outside this contract.
    """
