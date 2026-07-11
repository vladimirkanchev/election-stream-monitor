"""Shared doubles and opt-in live helpers for PostgreSQL session-store tests.

This module owns the SQL-aware in-memory double plus the real-DB bootstrap
helpers shared by the focused store-smoke and runtime-smoke lanes.
"""

from __future__ import annotations

import json
import os
from typing import Any, cast

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
    PostgresSessionStoreConnection,
    connect_postgres_session_store,
    reset_postgres_session_store_schema,
)
from session_store_postgres_config import (
    POSTGRES_SESSION_DATABASE_URL_ENV,
    POSTGRES_SESSION_STORE_REAL_SMOKE_ENV,
)
from session_store_runtime_config import SESSION_STORE_BACKEND_ENV


def is_real_postgres_session_store_smoke_enabled() -> bool:
    """Return whether the opt-in live store smoke env is fully enabled."""
    return (
        os.getenv(POSTGRES_SESSION_STORE_REAL_SMOKE_ENV) == "1"
        and bool(os.getenv(POSTGRES_SESSION_DATABASE_URL_ENV))
    )


REAL_POSTGRES_SESSION_STORE_SMOKE_ENABLED = is_real_postgres_session_store_smoke_enabled()


def is_real_postgres_session_runtime_smoke_enabled() -> bool:
    """Return whether live runtime smoke is enabled for explicit Postgres mode."""
    return (
        is_real_postgres_session_store_smoke_enabled()
        and os.getenv(SESSION_STORE_BACKEND_ENV, "").strip().lower() == "postgres"
    )


REAL_POSTGRES_SESSION_RUNTIME_SMOKE_ENABLED = (
    is_real_postgres_session_runtime_smoke_enabled()
)


def _decode_json_param(value: object) -> object:
    """Normalize one JSONB-bound parameter back into Python data."""
    if isinstance(value, str):
        return json.loads(value)
    return value


class InMemoryPostgresSessionStoreCursor:
    """SQL-aware cursor double for the fast adapter-contract lane."""

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
        """Handle only the SQL statements owned by the adapter contract tests."""
        self._connection.executed_statements.append((query, params))
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
                "selected_detectors": cast(
                    list[str],
                    _decode_json_param(selected_detectors),
                ),
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
                "latest_result_detectors": cast(
                    list[str],
                    _decode_json_param(latest_result_detectors),
                ),
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
                    "payload": row.get("payload_json", row.get("payload")),
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
                    "payload_json": cast(
                        dict[str, object],
                        _decode_json_param(payload_json),
                    ),
                }
            )
            self._fetchone_result = None
            self._fetchall_result = []
            return object()
        raise AssertionError(f"Unexpected PostgreSQL adapter query in test double: {query}")

    def fetchone(self) -> object | None:
        return self._fetchone_result

    def fetchall(self) -> list[object]:
        return self._fetchall_result


class InMemoryPostgresSessionStoreConnection:
    """In-memory connection double used by the fast PostgreSQL adapter tests."""

    def __init__(self) -> None:
        self.metadata_rows: dict[str, object] = {}
        self.progress_rows: dict[str, object] = {}
        self.cancel_rows: dict[str, bool] = {}
        self.result_rows: list[dict[str, object]] = []
        self.result_sequence = 0
        self.executed_statements: list[tuple[str, object | None]] = []
        self.commit_count = 0

    def cursor(self) -> InMemoryPostgresSessionStoreCursor:
        return InMemoryPostgresSessionStoreCursor(self)

    def commit(self) -> None:
        self.commit_count += 1


def close_postgres_session_store_connection_if_possible(connection: object) -> None:
    """Close a connection when the object exposes `close()`."""
    close = getattr(connection, "close", None)
    if callable(close):
        close()


def bootstrap_isolated_postgres_session_store() -> PostgresSessionStoreConnection:
    """Return one live PostgreSQL connection with only the known store tables reset."""
    connection = cast(PostgresSessionStoreConnection, connect_postgres_session_store())
    reset_postgres_session_store_schema(connection)
    return connection


def build_isolated_postgres_session_store() -> tuple[
    PostgresSessionStoreConnection,
    PostgresSessionStore,
]:
    """Return one reset live connection together with its bound session store."""
    connection = bootstrap_isolated_postgres_session_store()
    return connection, PostgresSessionStore(connection)
