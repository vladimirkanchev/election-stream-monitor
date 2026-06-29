"""File-backed `SessionStore` implementation.

This adapter keeps current `session_io` behavior behind the new durable store
contract before PostgreSQL is introduced.
"""

from __future__ import annotations

from typing import cast

from session_io import (
    append_result,
    read_session_result_events,
    read_session_snapshot,
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
    """`SessionStore` backed by the existing session files."""

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


DEFAULT_FILE_SESSION_STORE = FileSessionStore()
