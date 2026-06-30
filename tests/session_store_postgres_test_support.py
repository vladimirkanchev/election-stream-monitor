"""Helpers for opt-in PostgreSQL session-store smoke tests."""

from __future__ import annotations

import os
from typing import cast

from session_store_postgres import (
    PostgresSessionStore,
    PostgresSessionStoreConnection,
    connect_postgres_session_store,
    reset_postgres_session_store_schema,
)
from session_store_postgres_config import (
    POSTGRES_SESSION_DATABASE_URL_ENV,
    POSTGRES_SESSION_STORE_REAL_SMOKE_ENV,
)


REAL_POSTGRES_SESSION_STORE_SMOKE_ENABLED = (
    os.getenv(POSTGRES_SESSION_STORE_REAL_SMOKE_ENV) == "1"
    and bool(os.getenv(POSTGRES_SESSION_DATABASE_URL_ENV))
)


def close_postgres_session_store_connection_if_possible(connection: object) -> None:
    """Close a live PostgreSQL connection when the object exposes `close()`."""
    close = getattr(connection, "close", None)
    if callable(close):
        close()


def bootstrap_isolated_postgres_session_store() -> PostgresSessionStoreConnection:
    """Return one reset PostgreSQL connection for an opt-in live smoke run."""
    connection = cast(PostgresSessionStoreConnection, connect_postgres_session_store())
    reset_postgres_session_store_schema(connection)
    return connection


def build_isolated_postgres_session_store() -> tuple[
    PostgresSessionStoreConnection,
    PostgresSessionStore,
]:
    """Return one reset connection together with a bound `PostgresSessionStore`."""
    connection = bootstrap_isolated_postgres_session_store()
    return connection, PostgresSessionStore(connection)
