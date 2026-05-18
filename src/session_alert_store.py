"""Alert persistence seam for session-scoped raw alert storage.

This module defines the smallest storage boundary needed for the upcoming alert
persistence refactor:

- append one validated alert event
- read validated raw alert rows for one session

It intentionally does not own filtering, timestamp parsing, summaries, or
grouped incident shaping. Those behaviors remain in `session_alerts.py` and
`session_alert_incidents.py` so the first storage abstraction stays narrow and
easy to replace with a PostgreSQL-backed implementation later.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, TypedDict, cast

from logger import get_logger
from session_io import get_session_dir, session_exists
from session_models import AlertEvent, EventSeverity
from session_models import parse_alert_event_payload

logger = get_logger(__name__)
ALERT_LOG_FILENAME = "alerts.jsonl"
__all__ = [
    "ALERT_LOG_FILENAME",
    "AlertEventPayload",
    "DEFAULT_SESSION_ALERT_STORE",
    "FileSessionAlertStore",
    "SessionAlertsNotFoundError",
    "SessionAlertStore",
]


class AlertEventPayload(TypedDict):
    """Validated raw alert row shared across store and read-model seams."""

    session_id: str
    timestamp_utc: str
    detector_id: str
    title: str
    message: str
    severity: EventSeverity
    source_name: str
    window_index: int | None
    window_start_sec: float | None


class SessionAlertsNotFoundError(ValueError):
    """Raised when a read targets a session that has no persisted metadata."""


class SessionAlertStore(Protocol):
    """Minimal alert persistence contract for session-scoped storage.

    The store owns only raw alert event persistence. Callers remain responsible
    for query semantics such as filtering, summaries, and grouped incident
    construction.
    """

    def append_alert(self, event: AlertEvent) -> None:
        """Persist one validated alert event."""
        ...

    def read_session_alert_events(self, session_id: str) -> list[AlertEventPayload]:
        """Return validated raw alert rows for one session."""
        ...


class FileSessionAlertStore:
    """File-backed alert store over the current session-local `alerts.jsonl` log.

    This implementation owns only the raw persistence mechanics:

    - append validated alert events to the session alert log
    - read validated raw alert rows for one known session

    Filtering, summaries, and grouped incident semantics stay in the shared
    alert-query modules so the storage seam remains small. Existing
    `session_io.append_alert(...)` callers still reach this implementation
    through the default store instance.
    """

    def append_alert(self, event: AlertEvent) -> None:
        """Append one validated alert event to the file-backed alert log."""
        _append_jsonl(_get_alerts_file_path(event.session_id, require_known_session=False), event.to_dict())

    def read_session_alert_events(self, session_id: str) -> list[AlertEventPayload]:
        """Return file-backed validated raw alert rows for one known session."""
        return _read_alert_jsonl(_get_alerts_file_path(session_id, require_known_session=True))


DEFAULT_SESSION_ALERT_STORE = FileSessionAlertStore()


def _get_alerts_file_path(session_id: str, *, require_known_session: bool) -> Path:
    """Return the session-local alert-log path for one store operation."""
    if require_known_session and not session_exists(session_id):
        raise SessionAlertsNotFoundError(session_id)
    return get_session_dir(session_id) / ALERT_LOG_FILENAME


def _append_jsonl(file_path: Path, payload: dict[str, object]) -> None:
    """Append one JSON object to a JSONL file, creating parent dirs when needed."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload) + "\n")


def _read_alert_jsonl(file_path: Path) -> list[AlertEventPayload]:
    """Read a JSONL alert log and ignore unreadable or malformed rows safely."""
    if not file_path.exists():
        return []

    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        logger.warning("Ignoring unreadable alert log: %s", file_path)
        return []

    alerts: list[AlertEventPayload] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        parsed = _parse_alert_log_line(line, file_path=file_path, line_number=line_number)
        if parsed is not None:
            alerts.append(parsed)
    return alerts


def _parse_alert_log_line(
    line: str,
    *,
    file_path: Path,
    line_number: int,
) -> AlertEventPayload | None:
    """Parse one persisted alert-log line into the shared validated row shape."""
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        logger.warning("Ignoring unreadable alert line: %s:%d", file_path, line_number)
        return None

    parsed = parse_alert_event_payload(payload)
    if parsed is None:
        logger.warning("Ignoring malformed alert line: %s:%d", file_path, line_number)
        return None
    return cast(AlertEventPayload, parsed)
