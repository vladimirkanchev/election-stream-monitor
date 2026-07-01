"""File-backed `SessionStore` implementation.

This adapter keeps the current `session_io` behavior behind the shared store
contract while preserving the existing session directory layout. It is still
the runtime default, and cancel intent still uses the legacy marker-file shape
so detached-worker polling and compatibility tests stay stable while
PostgreSQL session storage remains explicit opt-in.
"""

from __future__ import annotations

from typing import cast

from session_io import (
    append_result,
    is_session_cancel_requested,
    read_session_result_events,
    read_session_snapshot,
    request_session_cancel,
    session_exists,
    write_session_metadata,
    write_session_progress,
)
from session_models import ResultEvent, SessionMetadata, SessionProgress
from session_store import (
    ResultEventPayload,
    SessionSnapshotPayload,
    SessionStore,
)


class FileSessionStore(SessionStore):
    """`SessionStore` backed by the existing session files and marker helpers."""

    def session_exists(self, session_id: str) -> bool:
        """Return whether file-backed session metadata exists."""
        return session_exists(session_id)

    def read_snapshot(self, session_id: str) -> SessionSnapshotPayload:
        """Return the current file-backed snapshot shape."""
        return cast(SessionSnapshotPayload, read_session_snapshot(session_id))

    def read_results(self, session_id: str) -> list[ResultEventPayload]:
        """Return validated file-backed detector results in append order."""
        return cast(list[ResultEventPayload], read_session_result_events(session_id))

    def write_metadata(self, metadata: SessionMetadata) -> None:
        """Persist metadata through the existing file helper."""
        write_session_metadata(metadata)

    def write_progress(self, progress: SessionProgress) -> None:
        """Persist latest progress through the existing file helper."""
        write_session_progress(progress)

    def append_result(self, event: ResultEvent) -> None:
        """Append one detector result through the existing file helper."""
        append_result(event)

    def request_cancel(self, session_id: str) -> None:
        """Persist cancel intent through the existing marker-file helper."""
        request_session_cancel(session_id)

    def is_cancel_requested(self, session_id: str) -> bool:
        """Return whether file-backed cancel intent exists for one session."""
        return is_session_cancel_requested(session_id)


DEFAULT_FILE_SESSION_STORE = FileSessionStore()
