"""Shared backend-equivalence tests for session-store persistence behavior.

This suite compares the file-backed store with the PostgreSQL-backed store at
the `SessionStore` boundary. It focuses on progress-state behavior, ordered
result behavior, and the narrow cancel-request signal that must stay
storage-neutral while the PostgreSQL migration is in flight.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import config
import pytest

from session_models import ResultEvent, SessionMetadata, SessionProgress, SessionStatus
from session_store import SessionStore
from session_store_file import FileSessionStore
from session_store_postgres import (
    POSTGRES_SESSION_CANCEL_EXISTS_SQL,
    POSTGRES_SESSION_CANCEL_UPSERT_SQL,
    POSTGRES_SESSION_METADATA_EXISTS_SQL,
    POSTGRES_SESSION_METADATA_SELECT_SQL,
    POSTGRES_SESSION_METADATA_UPSERT_SQL,
    POSTGRES_SESSION_PROGRESS_SELECT_SQL,
    POSTGRES_SESSION_PROGRESS_UPSERT_SQL,
    POSTGRES_SESSION_RESULTS_INSERT_SQL,
    POSTGRES_SESSION_RESULTS_SELECT_SQL,
    PostgresSessionStore,
)


class InMemoryPostgresSessionStoreCursor:
    """Tiny cursor that simulates the SQL used by session-store parity checks."""

    def __init__(self, connection: "InMemoryPostgresSessionStoreConnection") -> None:
        self._connection = connection
        self._fetchone_result: object | None = None
        self._fetchall_result: list[object] = []

    def __enter__(self) -> "InMemoryPostgresSessionStoreCursor":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        return None

    def execute(self, query: str, params: object | None = None) -> object:
        """Handle only the metadata/progress reads and writes used in this suite."""
        if query == POSTGRES_SESSION_METADATA_EXISTS_SQL:
            session_id = cast(tuple[str], params)[0]
            self._fetchone_result = (1,) if session_id in self._connection.metadata_rows else None
            return object()
        if query == POSTGRES_SESSION_METADATA_SELECT_SQL:
            session_id = cast(tuple[str], params)[0]
            self._fetchone_result = self._connection.metadata_rows.get(session_id)
            return object()
        if query == POSTGRES_SESSION_METADATA_UPSERT_SQL:
            session_id, mode, input_path, selected_detectors, status = cast(
                tuple[object, object, object, object, object],
                params,
            )
            self._connection.metadata_rows[str(session_id)] = {
                "session_id": str(session_id),
                "mode": mode,
                "input_path": str(input_path),
                "selected_detectors": list(cast(list[str], selected_detectors)),
                "status": status,
            }
            self._fetchone_result = None
            return object()
        if query == POSTGRES_SESSION_PROGRESS_SELECT_SQL:
            session_id = cast(tuple[str], params)[0]
            self._fetchone_result = self._connection.progress_rows.get(session_id)
            return object()
        if query == POSTGRES_SESSION_PROGRESS_UPSERT_SQL:
            (
                session_id,
                status,
                processed_count,
                total_count,
                current_item,
                latest_result_detector,
                alert_count,
                last_updated_utc,
                latest_result_detectors,
                status_reason,
                status_detail,
            ) = cast(
                tuple[
                    object,
                    object,
                    object,
                    object,
                    object,
                    object,
                    object,
                    object,
                    object,
                    object,
                    object,
                ],
                params,
            )
            self._connection.progress_rows[str(session_id)] = {
                "session_id": str(session_id),
                "status": status,
                "processed_count": processed_count,
                "total_count": total_count,
                "current_item": current_item,
                "latest_result_detector": latest_result_detector,
                "alert_count": alert_count,
                "last_updated_utc": str(last_updated_utc),
                "latest_result_detectors": list(cast(list[str], latest_result_detectors)),
                "status_reason": status_reason,
                "status_detail": status_detail,
            }
            self._fetchone_result = None
            return object()
        if query == POSTGRES_SESSION_CANCEL_EXISTS_SQL:
            session_id = cast(tuple[str], params)[0]
            self._fetchone_result = (
                (1,)
                if self._connection.cancel_rows.get(session_id) is True
                else None
            )
            return object()
        if query == POSTGRES_SESSION_CANCEL_UPSERT_SQL:
            session_id, cancel_requested = cast(tuple[object, object], params)
            self._connection.cancel_rows[str(session_id)] = bool(cancel_requested)
            self._fetchone_result = None
            return object()
        if query == POSTGRES_SESSION_RESULTS_SELECT_SQL:
            session_id = cast(tuple[str], params)[0]
            self._fetchone_result = None
            self._fetchall_result = [
                {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "detector_id": row["detector_id"],
                    "payload": row["payload_json"],
                }
                for row in self._connection.result_rows
                if row["session_id"] == session_id
            ]
            return object()
        if query == POSTGRES_SESSION_RESULTS_INSERT_SQL:
            (
                session_id,
                detector_id,
                detector_name,
                event_timestamp_utc,
                payload_json,
            ) = cast(
                tuple[object, object, object, object, object],
                params,
            )
            self._connection.result_sequence += 1
            self._connection.result_rows.append(
                {
                    "id": self._connection.result_sequence,
                    "session_id": str(session_id),
                    "detector_id": str(detector_id),
                    "detector_name": detector_name,
                    "event_timestamp_utc": event_timestamp_utc,
                    "payload_json": payload_json,
                }
            )
            self._fetchone_result = None
            self._fetchall_result = []
            return object()
        raise AssertionError(f"Unexpected SQL in session-store parity test: {query}")

    def fetchone(self) -> object | None:
        return self._fetchone_result

    def fetchall(self) -> list[object]:
        return self._fetchall_result


class InMemoryPostgresSessionStoreConnection:
    """Minimal connection double for storage-neutral session-store parity checks."""

    def __init__(self) -> None:
        self.metadata_rows: dict[str, object] = {}
        self.progress_rows: dict[str, object] = {}
        self.cancel_rows: dict[str, bool] = {}
        self.result_rows: list[dict[str, object]] = []
        self.result_sequence = 0
        self.commit_count = 0

    def cursor(self) -> InMemoryPostgresSessionStoreCursor:
        return InMemoryPostgresSessionStoreCursor(self)

    def commit(self) -> None:
        self.commit_count += 1


@pytest.fixture
def file_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FileSessionStore:
    """Return an isolated file-backed store rooted under a temporary directory."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)
    return FileSessionStore()


@pytest.fixture
def postgres_store() -> PostgresSessionStore:
    """Return a PostgreSQL store backed by the in-memory parity connection."""
    return PostgresSessionStore(InMemoryPostgresSessionStoreConnection())


def _metadata(session_id: str, *, status: SessionStatus) -> SessionMetadata:
    """Build one storage-neutral session metadata payload."""
    return SessionMetadata(
        session_id=session_id,
        mode="video_files",
        input_path="/tmp/clip.mp4",
        selected_detectors=["video_metrics"],
        status=status,
    )


def _running_progress(session_id: str) -> SessionProgress:
    """Build a representative in-flight progress payload."""
    return SessionProgress(
        session_id=session_id,
        status="running",
        processed_count=2,
        total_count=5,
        current_item="segment_0002.ts",
        latest_result_detector="video_metrics",
        alert_count=1,
        last_updated_utc="2026-06-30 10:00:02",
        latest_result_detectors=["video_metrics"],
        status_reason="running",
        status_detail=None,
    )


def _terminal_progress(
    session_id: str,
    *,
    status: SessionStatus,
    processed_count: int,
    current_item: str | None,
    status_reason: str,
    status_detail: str | None,
) -> SessionProgress:
    """Build one terminal latest-progress payload with explicit lifecycle detail."""
    return replace(
        SessionProgress.initial(session_id=session_id, total_count=5),
        status=status,
        processed_count=processed_count,
        current_item=current_item,
        latest_result_detector="video_metrics",
        latest_result_detectors=["video_metrics"],
        alert_count=1 if processed_count else 0,
        last_updated_utc="2026-06-30 10:00:05",
        status_reason=status_reason,
        status_detail=status_detail,
    )


def _result(
    session_id: str,
    detector_id: str,
    *,
    window_index: int,
    timestamp_utc: str,
) -> ResultEvent:
    """Build one storage-neutral detector result payload."""
    return ResultEvent(
        session_id=session_id,
        detector_id=detector_id,
        payload={
            "timestamp_utc": timestamp_utc,
            "detector_name": detector_id.replace("_", " ").title(),
            "source_name": f"segment_{window_index:04d}.ts",
            "window_index": window_index,
        },
    )


def _rich_result(
    session_id: str,
    detector_id: str,
    *,
    window_index: int,
    timestamp_utc: str,
) -> ResultEvent:
    """Build one richer detector result payload for backend-parity checks."""
    return ResultEvent(
        session_id=session_id,
        detector_id=detector_id,
        payload={
            "timestamp_utc": timestamp_utc,
            "detector_name": detector_id.replace("_", " ").title(),
            "source_name": f"segment_{window_index:04d}.ts",
            "window_index": window_index,
            "window_start_sec": float(window_index),
            "title": "Blur warning",
            "message": "Frame quality degraded in the sampled window.",
            "severity": "warning",
            "blur_score": 0.91,
            "blur_detected": True,
        },
    )


def _state_payloads(session_id: str) -> dict[str, tuple[SessionMetadata, SessionProgress]]:
    """Return the durable session/progress combinations shared by both backends."""
    return {
        "running": (
            _metadata(session_id, status="running"),
            _running_progress(session_id),
        ),
        "completed": (
            _metadata(session_id, status="completed"),
            _terminal_progress(
                session_id,
                status="completed",
                processed_count=5,
                current_item="segment_0005.ts",
                status_reason="completed",
                status_detail="session completed",
            ),
        ),
        "failed": (
            _metadata(session_id, status="failed"),
            _terminal_progress(
                session_id,
                status="failed",
                processed_count=3,
                current_item="segment_0003.ts",
                status_reason="source_unreachable",
                status_detail="upstream returned HTTP 503",
            ),
        ),
        "cancelled": (
            _metadata(session_id, status="cancelled"),
            _terminal_progress(
                session_id,
                status="cancelled",
                processed_count=2,
                current_item=None,
                status_reason="cancel_requested",
                status_detail="Cancellation requested by client",
            ),
        ),
    }


def _persist_session_state(
    store: SessionStore,
    *,
    metadata: SessionMetadata,
    progress: SessionProgress,
) -> dict[str, object]:
    """Write one durable session/progress pair and return the public snapshot."""
    store.write_metadata(metadata)
    store.write_progress(progress)
    return cast(dict[str, object], store.read_snapshot(metadata.session_id))


def _persist_results(
    store: SessionStore,
    *,
    metadata: SessionMetadata,
    results: list[ResultEvent],
) -> dict[str, object]:
    """Write one metadata row plus ordered results and return the snapshot."""
    store.write_metadata(metadata)
    for result in results:
        store.append_result(result)
    return cast(dict[str, object], store.read_snapshot(metadata.session_id))


def _assert_snapshot_latest_result_matches_ordered_history(
    store: SessionStore,
    *,
    session_id: str,
    snapshot: dict[str, object],
) -> None:
    """Assert the public latest-result invariant shared by both backends."""
    ordered_results = cast(list[dict[str, object]], store.read_results(session_id))
    snapshot_results = cast(list[dict[str, object]], snapshot["results"])

    assert snapshot_results == ordered_results
    if not ordered_results:
        assert snapshot["latest_result"] is None
        return
    assert snapshot["latest_result"] == ordered_results[-1]
    assert snapshot["latest_result"] == snapshot_results[-1]


def _assert_store_results_match(
    store: SessionStore,
    *,
    session_id: str,
    snapshot: dict[str, object],
    results: list[ResultEvent],
) -> None:
    """Assert the result-history contract for one backend."""
    expected_results = [result.to_dict() for result in results]

    assert store.read_results(session_id) == expected_results
    _assert_snapshot_latest_result_matches_ordered_history(
        store,
        session_id=session_id,
        snapshot=snapshot,
    )


def _assert_cancel_state_matches(store: SessionStore, session_id: str, expected: bool) -> None:
    """Assert the narrow cancel-request contract for one backend."""
    assert store.is_cancel_requested(session_id) is expected


def _prepare_cancel_state(store: SessionStore, *, session_id: str, state: str) -> None:
    """Prepare one lifecycle state before exercising the cancel signal."""
    if state == "missing":
        return

    lifecycle_state = "cancelled" if state == "already_canceled" else state
    metadata, progress = _state_payloads(session_id)[lifecycle_state]
    _persist_session_state(store, metadata=metadata, progress=progress)


def _exercise_cancel_signal(store: SessionStore, *, session_id: str, state: str) -> dict[str, object]:
    """Apply one cancel request and return the resulting public snapshot."""
    _prepare_cancel_state(store, session_id=session_id, state=state)
    if state == "already_canceled":
        store.request_cancel(session_id)
        _assert_cancel_state_matches(store, session_id, True)

    store.request_cancel(session_id)
    return cast(dict[str, object], store.read_snapshot(session_id))


def test_session_store_progress_parity_keeps_missing_session_contract(
    file_store: FileSessionStore,
    postgres_store: PostgresSessionStore,
) -> None:
    """Missing sessions should read the same stable snapshot from both backends."""
    session_id = "session-parity-missing"

    file_snapshot = file_store.read_snapshot(session_id)
    postgres_snapshot = postgres_store.read_snapshot(session_id)

    assert file_store.session_exists(session_id) is False
    assert postgres_store.session_exists(session_id) is False
    _assert_cancel_state_matches(file_store, session_id, False)
    _assert_cancel_state_matches(postgres_store, session_id, False)
    assert postgres_snapshot == file_snapshot


@pytest.mark.parametrize(
    ("state", "expected_exists"),
    [
        ("missing", False),
        ("running", True),
        ("already_canceled", True),
        ("completed", True),
    ],
)
def test_session_store_cancel_parity_matches_file_backed_behavior_across_lifecycle_states(
    state: str,
    expected_exists: bool,
    file_store: FileSessionStore,
    postgres_store: PostgresSessionStore,
) -> None:
    """Cancel intent should stay backend-neutral across key lifecycle states.

    The store-level contract is intentionally narrow: writing cancel intent must
    not mutate the public snapshot shape or session existence semantics, even
    though higher-level service code may reject cancel for terminal sessions.
    """
    session_id = f"session-parity-cancel-{state}"

    file_snapshot_before = _exercise_cancel_signal(
        file_store,
        session_id=session_id,
        state=state,
    )
    postgres_snapshot_before = _exercise_cancel_signal(
        postgres_store,
        session_id=session_id,
        state=state,
    )

    assert file_store.session_exists(session_id) is expected_exists
    assert postgres_store.session_exists(session_id) is expected_exists
    _assert_cancel_state_matches(file_store, session_id, True)
    _assert_cancel_state_matches(postgres_store, session_id, True)
    assert postgres_snapshot_before == file_snapshot_before

    file_store.request_cancel(session_id)
    postgres_store.request_cancel(session_id)

    file_snapshot_after_repeat = cast(dict[str, object], file_store.read_snapshot(session_id))
    postgres_snapshot_after_repeat = cast(
        dict[str, object],
        postgres_store.read_snapshot(session_id),
    )

    assert file_snapshot_after_repeat == file_snapshot_before
    assert postgres_snapshot_after_repeat == postgres_snapshot_before


@pytest.mark.parametrize("state", ["running", "completed", "failed", "cancelled"])
def test_session_store_progress_parity_matches_file_backed_behavior_across_lifecycle_states(
    state: str,
    file_store: FileSessionStore,
    postgres_store: PostgresSessionStore,
) -> None:
    """PostgreSQL progress snapshots should match the file-backed lifecycle contract."""
    session_id = f"session-parity-{state}"
    metadata, progress = _state_payloads(session_id)[state]

    file_snapshot = _persist_session_state(file_store, metadata=metadata, progress=progress)
    postgres_snapshot = _persist_session_state(postgres_store, metadata=metadata, progress=progress)

    assert file_store.session_exists(session_id) is True
    assert postgres_store.session_exists(session_id) is True
    assert file_snapshot["session"] == metadata.to_dict()
    assert file_snapshot["progress"] == progress.to_dict()
    assert postgres_snapshot == file_snapshot


def test_session_store_result_append_parity_matches_file_backed_behavior(
    file_store: FileSessionStore,
    postgres_store: PostgresSessionStore,
) -> None:
    """Ordered result appends should read back the same across both backends."""
    session_id = "session-parity-results"
    metadata = _metadata(session_id, status="running")
    results = [
        _result(
            session_id,
            "video_metrics",
            window_index=0,
            timestamp_utc="2026-07-01 10:00:00",
        ),
        _result(
            session_id,
            "video_blur",
            window_index=1,
            timestamp_utc="2026-07-01 10:00:01",
        ),
    ]

    file_snapshot = _persist_results(file_store, metadata=metadata, results=results)
    postgres_snapshot = _persist_results(
        postgres_store,
        metadata=metadata,
        results=results,
    )

    _assert_store_results_match(
        file_store,
        session_id=session_id,
        snapshot=file_snapshot,
        results=results,
    )
    _assert_store_results_match(
        postgres_store,
        session_id=session_id,
        snapshot=postgres_snapshot,
        results=results,
    )
    assert postgres_snapshot == file_snapshot


def test_session_store_result_append_parity_keeps_latest_result_on_equal_timestamps(
    file_store: FileSessionStore,
    postgres_store: PostgresSessionStore,
) -> None:
    """Append order, not timestamp sorting, should define `latest_result` for both backends."""
    session_id = "session-parity-results-same-timestamp"
    metadata = _metadata(session_id, status="running")
    results = [
        _result(
            session_id,
            "video_metrics",
            window_index=0,
            timestamp_utc="2026-07-01 10:00:00",
        ),
        _result(
            session_id,
            "video_blur",
            window_index=1,
            timestamp_utc="2026-07-01 10:00:00",
        ),
    ]

    file_snapshot = _persist_results(file_store, metadata=metadata, results=results)
    postgres_snapshot = _persist_results(
        postgres_store,
        metadata=metadata,
        results=results,
    )

    _assert_store_results_match(
        file_store,
        session_id=session_id,
        snapshot=file_snapshot,
        results=results,
    )
    _assert_store_results_match(
        postgres_store,
        session_id=session_id,
        snapshot=postgres_snapshot,
        results=results,
    )
    assert postgres_snapshot == file_snapshot


def test_session_store_result_parity_preserves_rich_payload_shape(
    file_store: FileSessionStore,
    postgres_store: PostgresSessionStore,
) -> None:
    """Both backends should preserve shared hints and detector-specific payload detail."""
    session_id = "session-parity-results-rich-payload"
    metadata = _metadata(session_id, status="running")
    results = [
        _rich_result(
            session_id,
            "video_blur",
            window_index=7,
            timestamp_utc="2026-07-01 10:00:07",
        ),
        _rich_result(
            session_id,
            "video_metrics",
            window_index=8,
            timestamp_utc="2026-07-01 10:00:08",
        ),
    ]

    file_snapshot = _persist_results(file_store, metadata=metadata, results=results)
    postgres_snapshot = _persist_results(
        postgres_store,
        metadata=metadata,
        results=results,
    )

    _assert_store_results_match(
        file_store,
        session_id=session_id,
        snapshot=file_snapshot,
        results=results,
    )
    _assert_store_results_match(
        postgres_store,
        session_id=session_id,
        snapshot=postgres_snapshot,
        results=results,
    )
    assert file_snapshot["results"][0]["payload"]["blur_score"] == 0.91
    assert file_snapshot["results"][0]["payload"]["severity"] == "warning"
    assert postgres_snapshot == file_snapshot
