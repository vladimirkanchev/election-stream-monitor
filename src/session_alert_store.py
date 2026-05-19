"""Shared alert persistence seam.

This module owns the storage boundary for session-scoped raw alert events and
the default backend selection used by current callers. Query behavior stays in
the alert read-model modules.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Protocol, TypedDict, cast

from logger import get_logger
from session_alert_store_runtime_config import (
    AlertStoreRuntimeConfigurationError,
    AlertStoreRuntimeSettings,
    clear_alert_store_runtime_settings_cache,
    get_alert_store_runtime_settings,
)
from session_io import get_session_dir, session_exists
from session_models import AlertEvent, EventSeverity
from session_models import parse_alert_event_payload

logger = get_logger(__name__)
ALERT_LOG_FILENAME = "alerts.jsonl"
__all__ = [
    "ALERT_LOG_FILENAME",
    "AlertEventPayload",
    "clear_default_session_alert_store_cache",
    "DEFAULT_SESSION_ALERT_STORE",
    "FileSessionAlertStore",
    "SessionAlertsNotFoundError",
    "SessionAlertStore",
    "get_default_session_alert_store",
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
    """Raised when a read targets a session with no known persisted metadata."""


class SessionAlertStore(Protocol):
    """Minimal contract for appending and reading raw session alerts."""

    def append_alert(self, event: AlertEvent) -> None:
        """Persist one validated alert event."""
        ...

    def read_session_alert_events(self, session_id: str) -> list[AlertEventPayload]:
        """Return validated raw alert rows for one session."""
        ...


class FileSessionAlertStore:
    """File-backed store over the session-local `alerts.jsonl` log."""

    def append_alert(self, event: AlertEvent) -> None:
        """Append one validated alert event to the file-backed alert log."""
        _append_jsonl(
            _get_alerts_file_path(event.session_id, require_known_session=False),
            event.to_dict(),
        )

    def read_session_alert_events(self, session_id: str) -> list[AlertEventPayload]:
        """Return file-backed validated raw alert rows for one known session."""
        return _read_alert_jsonl(_get_alerts_file_path(session_id, require_known_session=True))


_FILE_SESSION_ALERT_STORE = FileSessionAlertStore()


@lru_cache(maxsize=1)
def get_default_session_alert_store() -> SessionAlertStore:
    """Return the cached default alert store for the current runtime mode."""
    return _build_default_session_alert_store(get_alert_store_runtime_settings())


def clear_default_session_alert_store_cache() -> None:
    """Clear cached default-store selection plus its config caches."""
    get_default_session_alert_store.cache_clear()
    clear_alert_store_runtime_settings_cache()

    from session_alert_store_postgres_config import (
        clear_postgres_alert_store_settings_cache,
    )

    clear_postgres_alert_store_settings_cache()


def _build_default_session_alert_store(
    settings: AlertStoreRuntimeSettings,
) -> SessionAlertStore:
    """Build the configured default store without leaking backend choice to callers."""
    if settings.backend == "file":
        return _FILE_SESSION_ALERT_STORE
    if settings.backend == "postgres":
        return _build_postgres_default_session_alert_store()
    raise AlertStoreRuntimeConfigurationError(
        f"Unsupported alert-store backend: {settings.backend}"
    )


def _build_postgres_default_session_alert_store() -> SessionAlertStore:
    """Build the PostgreSQL-backed default store through the bootstrap seam."""
    from session_alert_store_postgres import (
        PostgresSessionAlertStore,
        bootstrap_postgres_alert_store,
    )

    return PostgresSessionAlertStore(bootstrap_postgres_alert_store())


class _DefaultSessionAlertStoreProxy:
    """Runtime-resolved proxy that preserves the existing alert-store call path."""

    def _store(self) -> SessionAlertStore:
        """Resolve the current default store for one proxy operation."""
        return get_default_session_alert_store()

    def append_alert(self, event: AlertEvent) -> None:
        """Append one alert through the currently selected default store backend."""
        self._store().append_alert(event)

    def read_session_alert_events(self, session_id: str) -> list[AlertEventPayload]:
        """Read alerts through the currently selected default store backend."""
        return self._store().read_session_alert_events(session_id)


DEFAULT_SESSION_ALERT_STORE: SessionAlertStore = _DefaultSessionAlertStoreProxy()


def _get_alerts_file_path(session_id: str, *, require_known_session: bool) -> Path:
    """Return the alert-log path for one file-store operation."""
    if require_known_session and not session_exists(session_id):
        raise SessionAlertsNotFoundError(session_id)
    return get_session_dir(session_id) / ALERT_LOG_FILENAME


def _append_jsonl(file_path: Path, payload: dict[str, object]) -> None:
    """Append one JSON object to a JSONL file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload) + "\n")


def _read_alert_jsonl(file_path: Path) -> list[AlertEventPayload]:
    """Read a JSONL alert log and skip unreadable or malformed rows."""
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
        parsed = _parse_alert_log_line(
            line,
            file_path=file_path,
            line_number=line_number,
        )
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
