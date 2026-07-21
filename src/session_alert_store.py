"""Shared alert persistence seam.

This module owns the runtime-selected store boundary for raw session alert
events. File-backed `alerts.jsonl` remains the default alert backend, while
PostgreSQL stays an explicit opt-in path behind the same call surface.
Each runtime reads and writes one selected backend only; it does not merge or
discover alert history from the other backend.

Known-session checks resolve through the active `SessionStore`, and query
behavior remains in the alert read-model modules.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Protocol, TypedDict, cast

from logger import get_logger
from postgres_diagnostics import redact_postgres_diagnostic
from session_alert_store_runtime_config import (
    AlertStoreRuntimeConfigurationError,
    AlertStoreRuntimeSettings,
    clear_alert_store_runtime_settings_cache,
    get_alert_store_runtime_settings,
)
from session_io import get_session_dir
from session_models import AlertEvent, EventSeverity
from session_models import parse_alert_event_payload
from session_store_runtime import get_default_session_store

logger = get_logger(__name__)
ALERT_LOG_FILENAME = "alerts.jsonl"
__all__ = [
    "ALERT_LOG_FILENAME",
    "AlertEventPayload",
    "clear_default_session_alert_store_cache",
    "DEFAULT_SESSION_ALERT_STORE",
    "FileSessionAlertStore",
    "require_known_session",
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
            _get_alerts_file_path(event.session_id, require_known_session_check=False),
            event.to_dict(),
        )

    def read_session_alert_events(self, session_id: str) -> list[AlertEventPayload]:
        """Return file-backed validated raw alert rows for one known session."""
        return _read_alert_jsonl(
            _get_alerts_file_path(session_id, require_known_session_check=True)
        )


_FILE_SESSION_ALERT_STORE = FileSessionAlertStore()


@lru_cache(maxsize=1)
def get_default_session_alert_store() -> SessionAlertStore:
    """Return the cached default alert store for the current runtime mode.

    The normal branch-default resolution remains the file-backed store unless
    runtime config explicitly opts into PostgreSQL.
    """
    return _build_default_session_alert_store(get_alert_store_runtime_settings())


def clear_default_session_alert_store_cache() -> None:
    """Clear cached default-store selection plus runtime/bootstrap settings."""
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
    """Build explicit PostgreSQL storage and normalize bootstrap configuration errors.

    Once PostgreSQL is selected, failures remain visible to callers rather
    than falling back to the file-backed store.
    """
    from session_alert_store_postgres import (
        PostgresAlertStoreBootstrapError,
        PostgresSessionAlertStore,
        bootstrap_postgres_alert_store,
    )

    try:
        return PostgresSessionAlertStore(bootstrap_postgres_alert_store())
    except PostgresAlertStoreBootstrapError as err:
        detail = redact_postgres_diagnostic(str(err))

    raise AlertStoreRuntimeConfigurationError(detail)


class _DefaultSessionAlertStoreProxy:
    """Runtime-resolved proxy that preserves the existing alert-store call path.

    Callers keep using one stable seam while runtime config decides whether the
    process runs with the default file backend or the opt-in PostgreSQL backend.
    """

    def append_alert(self, event: AlertEvent) -> None:
        """Append one alert through the currently selected default store backend."""
        get_default_session_alert_store().append_alert(event)

    def read_session_alert_events(self, session_id: str) -> list[AlertEventPayload]:
        """Read alerts through the currently selected default store backend."""
        return get_default_session_alert_store().read_session_alert_events(session_id)


DEFAULT_SESSION_ALERT_STORE: SessionAlertStore = _DefaultSessionAlertStoreProxy()


def session_exists(session_id: str) -> bool:
    """Return whether durable session metadata exists for one session."""
    return get_default_session_store().session_exists(session_id)


def require_known_session(session_id: str) -> None:
    """Raise the shared not-found error when durable session metadata is absent."""
    if not session_exists(session_id):
        raise SessionAlertsNotFoundError(session_id)


def _get_alerts_file_path(session_id: str, *, require_known_session_check: bool) -> Path:
    """Return the alert-log path for one file-store operation."""
    if require_known_session_check:
        require_known_session(session_id)
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
