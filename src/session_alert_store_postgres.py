"""PostgreSQL-backed alert store and schema helpers.

This module owns the database-facing side of the Postgres alert backend:
schema, bootstrap, and the concrete `SessionAlertStore` implementation.
"""

from __future__ import annotations

from datetime import datetime
import importlib
from typing import Any, Protocol, Self, cast

from session_alert_store import (
    AlertEventPayload,
    SessionAlertStore,
    SessionAlertsNotFoundError,
)
from session_alert_store_postgres_config import (
    PostgresAlertStoreConfigurationError,
    PostgresAlertStoreSettings,
    get_postgres_alert_store_settings,
    validate_postgres_alert_store_settings,
)
from session_models import AlertEvent, EventSeverity
from session_store_runtime import get_default_session_store


POSTGRES_ALERT_EVENTS_TABLE_NAME = "session_alert_events"
POSTGRES_ALERT_EVENT_COLUMNS: tuple[str, ...] = (
    "session_id",
    "timestamp_utc",
    "detector_id",
    "title",
    "message",
    "severity",
    "source_name",
    "window_index",
    "window_start_sec",
)
POSTGRES_ALERT_EVENT_NULLABLE_COLUMNS: tuple[str, ...] = (
    "window_index",
    "window_start_sec",
)
POSTGRES_ALERT_EVENT_COLUMN_COUNT = len(POSTGRES_ALERT_EVENT_COLUMNS)
POSTGRES_ALERT_EVENT_READ_ORDER = "id ASC"
POSTGRES_ALERT_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
POSTGRES_ALERT_TIMESTAMP_TO_CHAR_FORMAT = "YYYY-MM-DD HH24:MI:SS"

POSTGRES_ALERT_EVENTS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {POSTGRES_ALERT_EVENTS_TABLE_NAME} (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    timestamp_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    detector_id TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning')),
    source_name TEXT NOT NULL,
    window_index INTEGER NULL,
    window_start_sec DOUBLE PRECISION NULL
)
""".strip()

POSTGRES_ALERT_EVENTS_INDEX_SQL: tuple[str, ...] = (
    f"""
    CREATE INDEX IF NOT EXISTS idx_{POSTGRES_ALERT_EVENTS_TABLE_NAME}_session_id_id
    ON {POSTGRES_ALERT_EVENTS_TABLE_NAME} (session_id, id)
    """.strip(),
)

POSTGRES_ALERT_STORE_SCHEMA_STATEMENTS: tuple[str, ...] = (
    POSTGRES_ALERT_EVENTS_TABLE_SQL,
    *POSTGRES_ALERT_EVENTS_INDEX_SQL,
)
POSTGRES_ALERT_EVENTS_INSERT_SQL = f"""
INSERT INTO {POSTGRES_ALERT_EVENTS_TABLE_NAME} (
    session_id,
    timestamp_utc,
    detector_id,
    title,
    message,
    severity,
    source_name,
    window_index,
    window_start_sec
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
""".strip()
POSTGRES_ALERT_EVENTS_READ_SQL = f"""
SELECT
    session_id,
    to_char(timestamp_utc, '{POSTGRES_ALERT_TIMESTAMP_TO_CHAR_FORMAT}') AS timestamp_utc,
    detector_id,
    title,
    message,
    severity,
    source_name,
    window_index,
    window_start_sec
FROM {POSTGRES_ALERT_EVENTS_TABLE_NAME}
WHERE session_id = %s
ORDER BY {POSTGRES_ALERT_EVENT_READ_ORDER}
""".strip()

__all__ = [
    "POSTGRES_ALERT_EVENTS_INDEX_SQL",
    "POSTGRES_ALERT_EVENTS_INSERT_SQL",
    "POSTGRES_ALERT_EVENTS_READ_SQL",
    "POSTGRES_ALERT_EVENTS_TABLE_NAME",
    "POSTGRES_ALERT_EVENTS_TABLE_SQL",
    "POSTGRES_ALERT_EVENT_COLUMNS",
    "POSTGRES_ALERT_EVENT_NULLABLE_COLUMNS",
    "POSTGRES_ALERT_EVENT_READ_ORDER",
    "POSTGRES_ALERT_TIMESTAMP_FORMAT",
    "POSTGRES_ALERT_TIMESTAMP_TO_CHAR_FORMAT",
    "POSTGRES_ALERT_STORE_SCHEMA_STATEMENTS",
    "PostgresSessionAlertStore",
    "PostgresAlertStoreBootstrapError",
    "PostgresAlertStoreConnection",
    "bootstrap_postgres_alert_store",
    "connect_postgres_alert_store",
    "initialize_postgres_alert_store",
]


class PostgresAlertStoreBootstrapError(RuntimeError):
    """Raised when PostgreSQL alert-store bootstrap cannot complete."""


class PostgresAlertStoreCursor(Protocol):
    """Minimal cursor protocol needed for schema bootstrap and store queries."""

    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None: ...
    def execute(self, query: str, params: object | None = None) -> object: ...
    def fetchall(self) -> list[object]: ...


class PostgresAlertStoreConnection(Protocol):
    """Minimal connection protocol needed for schema bootstrap and store queries."""

    def cursor(self) -> PostgresAlertStoreCursor: ...
    def commit(self) -> None: ...


class PostgresSessionAlertStore(SessionAlertStore):
    """PostgreSQL-backed store that preserves the shared alert seam contract."""

    def __init__(self, connection: PostgresAlertStoreConnection) -> None:
        """Bind one PostgreSQL connection to the alert persistence seam."""
        self._connection = connection

    def append_alert(self, event: AlertEvent) -> None:
        """Insert one validated alert event into the PostgreSQL alert table."""
        with self._connection.cursor() as cursor:
            cursor.execute(POSTGRES_ALERT_EVENTS_INSERT_SQL, _event_insert_params(event))
        self._connection.commit()

    def read_session_alert_events(self, session_id: str) -> list[AlertEventPayload]:
        """Return validated raw alert rows for one known session.

        Unknown-session behavior still follows the session metadata seam so the
        alert store preserves the same contract while sessions remain file-backed.
        """
        _require_known_session(session_id)

        with self._connection.cursor() as cursor:
            cursor.execute(POSTGRES_ALERT_EVENTS_READ_SQL, (session_id,))
            rows = cursor.fetchall()
        return [_row_to_alert_event_payload(row) for row in rows]


def connect_postgres_alert_store(
    settings: PostgresAlertStoreSettings | None = None,
) -> PostgresAlertStoreConnection:
    """Open one PostgreSQL connection for the alert-store bootstrap path."""
    resolved_settings = settings or get_postgres_alert_store_settings()
    database_url = _validated_postgres_alert_database_url(resolved_settings)

    try:
        psycopg = importlib.import_module("psycopg")
    except ImportError as err:
        raise PostgresAlertStoreBootstrapError(
            "Install psycopg to use the PostgreSQL alert-store bootstrap path"
        ) from err

    try:
        return cast(
            PostgresAlertStoreConnection,
            psycopg.connect(database_url),
        )
    except psycopg.Error as err:
        raise PostgresAlertStoreBootstrapError(
            "Could not connect to the PostgreSQL alert store"
        ) from err


def initialize_postgres_alert_store(connection: PostgresAlertStoreConnection) -> None:
    """Create the PostgreSQL alert schema for the current seam design."""
    with connection.cursor() as cursor:
        for statement in POSTGRES_ALERT_STORE_SCHEMA_STATEMENTS:
            cursor.execute(statement)
    connection.commit()


def bootstrap_postgres_alert_store(
    settings: PostgresAlertStoreSettings | None = None,
) -> PostgresAlertStoreConnection:
    """Connect to PostgreSQL and initialize the alert schema when configured."""
    resolved_settings = settings or get_postgres_alert_store_settings()
    connection = connect_postgres_alert_store(resolved_settings)
    if resolved_settings.auto_create_tables:
        initialize_postgres_alert_store(connection)
    return connection


def session_exists(session_id: str) -> bool:
    """Return whether durable session metadata exists for one session."""
    return get_default_session_store().session_exists(session_id)


def _event_insert_params(event: AlertEvent) -> tuple[object, ...]:
    """Build insert parameters for one validated alert event."""
    return (
        event.session_id,
        datetime.strptime(event.timestamp_utc, POSTGRES_ALERT_TIMESTAMP_FORMAT),
        event.detector_id,
        event.title,
        event.message,
        event.severity,
        event.source_name,
        event.window_index,
        event.window_start_sec,
    )


def _require_known_session(session_id: str) -> None:
    """Preserve the shared unknown-session contract before issuing a read query."""
    if not session_exists(session_id):
        raise SessionAlertsNotFoundError(session_id)


def _validated_postgres_alert_database_url(
    settings: PostgresAlertStoreSettings,
) -> str:
    """Validate bootstrap settings and return the required PostgreSQL URL."""
    try:
        validate_postgres_alert_store_settings(settings)
    except PostgresAlertStoreConfigurationError as err:
        raise PostgresAlertStoreBootstrapError(str(err)) from err

    database_url = settings.database_url
    if database_url is None:  # pragma: no cover - defensive guard after validation
        raise PostgresAlertStoreBootstrapError(
            "PostgreSQL alert store requires a configured database URL"
        )
    return database_url


def _row_to_alert_event_payload(row: object) -> AlertEventPayload:
    """Map one PostgreSQL row into the shared raw alert payload contract."""
    values = _normalize_row_values(row)
    (
        session_id,
        timestamp_utc,
        detector_id,
        title,
        message,
        severity,
        source_name,
        window_index,
        window_start_sec,
    ) = values
    return {
        "session_id": cast(str, session_id),
        "timestamp_utc": cast(str, timestamp_utc),
        "detector_id": cast(str, detector_id),
        "title": cast(str, title),
        "message": cast(str, message),
        "severity": cast(EventSeverity, severity),
        "source_name": cast(str, source_name),
        "window_index": cast(int | None, window_index),
        "window_start_sec": cast(float | None, window_start_sec),
    }


def _normalize_row_values(row: object) -> tuple[object, ...]:
    """Normalize one driver row into the frozen alert-column tuple shape."""
    if not isinstance(row, (tuple, list)):
        raise ValueError(_POSTGRES_ALERT_ROW_SHAPE_ERROR)
    values = tuple(row)

    if len(values) != POSTGRES_ALERT_EVENT_COLUMN_COUNT:
        raise ValueError(_POSTGRES_ALERT_ROW_SHAPE_ERROR)
    return values


_POSTGRES_ALERT_ROW_SHAPE_ERROR = (
    "PostgreSQL alert row does not match the expected column contract"
)
