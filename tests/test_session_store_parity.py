"""Shared backend-equivalence tests for session-store progress behavior.

This suite compares the file-backed store with the PostgreSQL-backed store at
the durable `SessionStore` boundary. It focuses on progress-state behavior
that must stay storage-neutral while the PostgreSQL migration is in flight.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import config
import pytest

from session_models import SessionMetadata, SessionProgress, SessionStatus
from session_store import SessionStore
from session_store_file import FileSessionStore
from session_store_postgres import (
    POSTGRES_SESSION_METADATA_EXISTS_SQL,
    POSTGRES_SESSION_METADATA_SELECT_SQL,
    POSTGRES_SESSION_METADATA_UPSERT_SQL,
    POSTGRES_SESSION_PROGRESS_SELECT_SQL,
    POSTGRES_SESSION_PROGRESS_UPSERT_SQL,
    POSTGRES_SESSION_RESULTS_SELECT_SQL,
    PostgresSessionStore,
)


class InMemoryPostgresSessionStoreCursor:
    """Tiny cursor that simulates the SQL used by progress parity checks."""

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
        if query == POSTGRES_SESSION_RESULTS_SELECT_SQL:
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
    assert postgres_snapshot == file_snapshot


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
