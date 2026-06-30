"""Bootstrap helpers for the future PostgreSQL-backed session store.

This module owns the narrow PostgreSQL bootstrap surface for session
persistence: driver loading, connection creation, schema initialization, and
opt-in schema reset for focused tests. It does not implement the full runtime
store yet.
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any, Protocol, Self

from session_store_postgres_config import (
    PostgresSessionStoreConfigurationError,
    PostgresSessionStoreSettings,
    get_postgres_session_store_settings,
    should_auto_create_postgres_session_store_tables,
    validate_postgres_session_store_settings,
)


POSTGRES_SESSION_METADATA_TABLE_NAME = "session_metadata"
POSTGRES_SESSION_PROGRESS_TABLE_NAME = "session_progress"
POSTGRES_SESSION_RESULTS_TABLE_NAME = "session_result_events"

POSTGRES_SESSION_METADATA_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {POSTGRES_SESSION_METADATA_TABLE_NAME} (
    session_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    input_path TEXT NOT NULL,
    selected_detectors JSONB NOT NULL,
    status TEXT NOT NULL
)
""".strip()

POSTGRES_SESSION_PROGRESS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {POSTGRES_SESSION_PROGRESS_TABLE_NAME} (
    session_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    processed_count INTEGER NOT NULL,
    total_count INTEGER NOT NULL,
    current_item TEXT NULL,
    latest_result_detector TEXT NULL,
    alert_count INTEGER NOT NULL,
    last_updated_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    latest_result_detectors JSONB NOT NULL,
    status_reason TEXT NULL,
    status_detail TEXT NULL
)
""".strip()

POSTGRES_SESSION_RESULTS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {POSTGRES_SESSION_RESULTS_TABLE_NAME} (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    detector_id TEXT NOT NULL,
    payload JSONB NOT NULL
)
""".strip()

POSTGRES_SESSION_SCHEMA_INDEX_STATEMENTS: tuple[str, ...] = (
    f"""
    CREATE INDEX IF NOT EXISTS idx_{POSTGRES_SESSION_PROGRESS_TABLE_NAME}_status
    ON {POSTGRES_SESSION_PROGRESS_TABLE_NAME} (status)
    """.strip(),
    f"""
    CREATE INDEX IF NOT EXISTS idx_{POSTGRES_SESSION_RESULTS_TABLE_NAME}_session_id_id
    ON {POSTGRES_SESSION_RESULTS_TABLE_NAME} (session_id, id)
    """.strip(),
)

POSTGRES_SESSION_STORE_SCHEMA_STATEMENTS: tuple[str, ...] = (
    POSTGRES_SESSION_METADATA_TABLE_SQL,
    POSTGRES_SESSION_PROGRESS_TABLE_SQL,
    POSTGRES_SESSION_RESULTS_TABLE_SQL,
    *POSTGRES_SESSION_SCHEMA_INDEX_STATEMENTS,
)
POSTGRES_SESSION_STORE_SCHEMA_DROP_STATEMENTS: tuple[str, ...] = (
    f"DROP TABLE IF EXISTS {POSTGRES_SESSION_RESULTS_TABLE_NAME}",
    f"DROP TABLE IF EXISTS {POSTGRES_SESSION_PROGRESS_TABLE_NAME}",
    f"DROP TABLE IF EXISTS {POSTGRES_SESSION_METADATA_TABLE_NAME}",
)


class PostgresSessionStoreBootstrapError(RuntimeError):
    """Raised when PostgreSQL session-store bootstrap cannot proceed cleanly."""


class PostgresSessionStoreCursor(Protocol):
    """Minimal cursor protocol needed by schema bootstrap helpers."""

    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None: ...
    def execute(self, query: str, params: object | None = None) -> object: ...


class PostgresSessionStoreConnection(Protocol):
    """Minimal connection protocol needed by schema bootstrap helpers."""

    def cursor(self) -> PostgresSessionStoreCursor: ...
    def commit(self) -> None: ...


def load_postgres_session_store_driver() -> ModuleType:
    """Load the PostgreSQL driver required by the session-store backend."""
    try:
        return importlib.import_module("psycopg")
    except ImportError as err:
        raise PostgresSessionStoreBootstrapError(
            "Install psycopg to use the PostgreSQL session-store backend"
        ) from err


def connect_postgres_session_store(
    settings: PostgresSessionStoreSettings | None = None,
) -> PostgresSessionStoreConnection:
    """Open one PostgreSQL connection for bootstrap and future store work."""
    resolved_settings = settings or get_postgres_session_store_settings()
    database_url = _validated_postgres_session_database_url(resolved_settings)
    psycopg = load_postgres_session_store_driver()

    try:
        return psycopg.connect(database_url)
    except psycopg.Error as err:
        raise PostgresSessionStoreBootstrapError(
            "Could not connect to the PostgreSQL session store"
        ) from err


def initialize_postgres_session_store(connection: PostgresSessionStoreConnection) -> None:
    """Create the PostgreSQL schema that matches the current store contract."""
    with connection.cursor() as cursor:
        for statement in POSTGRES_SESSION_STORE_SCHEMA_STATEMENTS:
            cursor.execute(statement)
    connection.commit()


def drop_postgres_session_store_schema(connection: PostgresSessionStoreConnection) -> None:
    """Drop the PostgreSQL session schema in reverse dependency order."""
    with connection.cursor() as cursor:
        for statement in POSTGRES_SESSION_STORE_SCHEMA_DROP_STATEMENTS:
            cursor.execute(statement)
    connection.commit()


def reset_postgres_session_store_schema(connection: PostgresSessionStoreConnection) -> None:
    """Reset the PostgreSQL session schema for opt-in isolation helpers."""
    drop_postgres_session_store_schema(connection)
    initialize_postgres_session_store(connection)


def bootstrap_postgres_session_store(
    settings: PostgresSessionStoreSettings | None = None,
) -> PostgresSessionStoreConnection:
    """Connect to PostgreSQL and initialize schema only when explicitly enabled."""
    resolved_settings = settings or get_postgres_session_store_settings()
    connection = connect_postgres_session_store(resolved_settings)
    if should_auto_create_postgres_session_store_tables(resolved_settings):
        initialize_postgres_session_store(connection)
    return connection


def _validated_postgres_session_database_url(
    settings: PostgresSessionStoreSettings,
) -> str:
    """Validate bootstrap settings and return the required PostgreSQL URL."""
    try:
        validate_postgres_session_store_settings(settings)
    except PostgresSessionStoreConfigurationError as err:
        raise PostgresSessionStoreBootstrapError(str(err)) from err

    database_url = settings.database_url
    if database_url is None:  # pragma: no cover - defensive guard after validation
        raise PostgresSessionStoreBootstrapError(
            "PostgreSQL session store requires a configured database URL"
        )
    return database_url
