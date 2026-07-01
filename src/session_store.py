"""Storage contract for monitoring-session state.

`SessionStore` is the storage contract for session metadata, latest progress,
ordered detector results, and cancel intent. The file-backed implementation is
still the runtime default; PostgreSQL is available only through explicit
opt-in. Broader runtime artifacts such as logs, temp media, and HTTP/HLS replay
keys stay outside this contract.
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
    """Append-ordered detector result row.

    The durable public row stays compact: stable session id, stable detector
    id, and raw detector payload JSON. Stores own ordering internally;
    detectors may optionally include shared timing/source hints inside
    `payload`, but the contract does not require every detector to populate the
    same nested keys. `latest_result` is derived from the final valid ordered
    row rather than stored independently.
    """

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


def build_latest_result_payload(
    results: list[ResultEventPayload],
) -> ResultEventPayload | None:
    """Return the latest result from append-ordered history.

    Result history is append-only: callers pass already ordered rows, and the
    latest item is always the final valid row rather than a timestamp-derived
    choice.
    """
    return results[-1] if results else None


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
        "latest_result": build_latest_result_payload(results),
    }


class SessionStoreReader(Protocol):
    """Read contract for durable session state.

    Readers expose snapshot semantics without leaking backend layout or file
    names.
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

    Lifecycle-specific operations such as start and finalize stay in
    runner/service code, while result ordering remains a backend concern.
    """

    def write_metadata(self, metadata: SessionMetadata) -> None:
        """Persist the authoritative session metadata payload."""
        ...

    def write_progress(self, progress: SessionProgress) -> None:
        """Persist the latest progress payload for one session.

        This replaces the previous progress read model for the same session id
        instead of appending a progress-history stream.
        """
        ...

    def append_result(self, event: ResultEvent) -> None:
        """Append one detector result while preserving read order."""
        ...


class SessionStoreCancellationControl(Protocol):
    """Minimal runtime-control contract for cooperative session cancellation.

    This stays intentionally small: one idempotent write method and one cheap
    boolean read method. The contract records current cancel intent without
    turning cancellation into a broader command or event framework. Public
    request validation and transient `cancelling` responses stay above this
    contract in service and route code.
    """

    def request_cancel(self, session_id: str) -> None:
        """Persist cancel intent for one session.

        The low-level contract is intentionally tolerant and idempotent. Route
        and service layers still own lifecycle validation and missing-session
        behavior.
        """
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
    """Combined session-store contract for concrete backends.

    Durable session reads and writes live here together with a narrow cancel
    signal. Alert storage, logs, temp media, and HTTP/HLS replay keys remain
    outside this contract.
    """
