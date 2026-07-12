"""PostgreSQL session-store adapter plus explicit bootstrap helpers.

This module owns the opt-in PostgreSQL backend for session persistence:
contract-owned table mapping, driver and connection setup, schema bootstrap for
known tables, the concrete `SessionStore` adapter, and test-only schema reset
helpers for live smoke runs. The default runtime path still stays file-backed
elsewhere. Within the PostgreSQL store, progress stays latest-only, results
stay append-ordered, and cancel intent stays a small current-state row rather
than a broader command history.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Mapping, Protocol, Self, cast

from session_models import (
    ResultEvent,
    SessionMetadata,
    SessionProgress,
    parse_session_metadata_payload,
    parse_session_progress_payload,
    parse_result_event_payload,
)
from session_store import (
    ResultEventPayload,
    SessionMetadataPayload,
    SessionProgressPayload,
    SessionSnapshotPayload,
    SessionStore,
    build_empty_session_snapshot_payload,
    build_session_snapshot_payload,
)

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
POSTGRES_SESSION_CANCEL_TABLE_NAME = "session_cancel_requests"


@dataclass(frozen=True)
class PostgresSessionStoreTableSpec:
    """Describe one contract-owned PostgreSQL session table."""

    table_name: str
    contract_methods: tuple[str, ...]
    payload_fields: tuple[str, ...]
    purpose: str


POSTGRES_SESSION_METADATA_FIELDS: tuple[str, ...] = (
    "session_id",
    "mode",
    "input_path",
    "selected_detectors",
    "status",
)
POSTGRES_SESSION_PROGRESS_FIELDS: tuple[str, ...] = (
    "session_id",
    "status",
    "processed_count",
    "total_count",
    "current_item",
    "latest_result_detector",
    "alert_count",
    "last_updated_utc",
    "latest_result_detectors",
    "status_reason",
    "status_detail",
)
POSTGRES_SESSION_RESULT_FIELDS: tuple[str, ...] = (
    "id",
    "session_id",
    "detector_id",
    "detector_name",
    "event_timestamp_utc",
    "payload_json",
)
POSTGRES_SESSION_CANCEL_FIELDS: tuple[str, ...] = (
    "session_id",
    "cancel_requested",
)

POSTGRES_SESSION_STORE_TABLE_SPECS: tuple[PostgresSessionStoreTableSpec, ...] = (
    PostgresSessionStoreTableSpec(
        table_name=POSTGRES_SESSION_METADATA_TABLE_NAME,
        contract_methods=("write_metadata", "session_exists", "read_snapshot"),
        payload_fields=POSTGRES_SESSION_METADATA_FIELDS,
        purpose="One authoritative durable metadata row per session.",
    ),
    PostgresSessionStoreTableSpec(
        table_name=POSTGRES_SESSION_PROGRESS_TABLE_NAME,
        contract_methods=("write_progress", "read_snapshot"),
        payload_fields=POSTGRES_SESSION_PROGRESS_FIELDS,
        purpose="Latest-only progress read model keyed by session id.",
    ),
    PostgresSessionStoreTableSpec(
        table_name=POSTGRES_SESSION_RESULTS_TABLE_NAME,
        contract_methods=("append_result", "read_results", "read_snapshot"),
        payload_fields=POSTGRES_SESSION_RESULT_FIELDS,
        purpose="Append-ordered detector result history keyed by session id.",
    ),
    PostgresSessionStoreTableSpec(
        table_name=POSTGRES_SESSION_CANCEL_TABLE_NAME,
        contract_methods=("request_cancel", "is_cancel_requested"),
        payload_fields=POSTGRES_SESSION_CANCEL_FIELDS,
        purpose="One current-state cancel row per session for cooperative runtime polling.",
    ),
)

POSTGRES_SESSION_STORE_METHOD_TABLE_MAP: dict[str, tuple[str, ...]] = {
    "write_metadata": (POSTGRES_SESSION_METADATA_TABLE_NAME,),
    "session_exists": (POSTGRES_SESSION_METADATA_TABLE_NAME,),
    "write_progress": (POSTGRES_SESSION_PROGRESS_TABLE_NAME,),
    "append_result": (POSTGRES_SESSION_RESULTS_TABLE_NAME,),
    "read_results": (POSTGRES_SESSION_RESULTS_TABLE_NAME,),
    "request_cancel": (POSTGRES_SESSION_CANCEL_TABLE_NAME,),
    "is_cancel_requested": (POSTGRES_SESSION_CANCEL_TABLE_NAME,),
    "read_snapshot": (
        POSTGRES_SESSION_METADATA_TABLE_NAME,
        POSTGRES_SESSION_PROGRESS_TABLE_NAME,
        POSTGRES_SESSION_RESULTS_TABLE_NAME,
    ),
}

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
    status_detail TEXT NULL,
    FOREIGN KEY (session_id)
        REFERENCES {POSTGRES_SESSION_METADATA_TABLE_NAME} (session_id)
        ON DELETE CASCADE
)
""".strip()

POSTGRES_SESSION_RESULTS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {POSTGRES_SESSION_RESULTS_TABLE_NAME} (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    detector_id TEXT NOT NULL,
    detector_name TEXT NULL,
    event_timestamp_utc TEXT NULL,
    payload_json JSONB NOT NULL,
    FOREIGN KEY (session_id)
        REFERENCES {POSTGRES_SESSION_METADATA_TABLE_NAME} (session_id)
        ON DELETE CASCADE
)
""".strip()

POSTGRES_SESSION_CANCEL_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {POSTGRES_SESSION_CANCEL_TABLE_NAME} (
    session_id TEXT PRIMARY KEY,
    cancel_requested BOOLEAN NOT NULL
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
    f"""
    CREATE INDEX IF NOT EXISTS idx_{POSTGRES_SESSION_RESULTS_TABLE_NAME}_session_id_detector_id_id
    ON {POSTGRES_SESSION_RESULTS_TABLE_NAME} (session_id, detector_id, id)
    """.strip(),
)

POSTGRES_SESSION_STORE_SCHEMA_STATEMENTS: tuple[str, ...] = (
    POSTGRES_SESSION_METADATA_TABLE_SQL,
    POSTGRES_SESSION_PROGRESS_TABLE_SQL,
    POSTGRES_SESSION_RESULTS_TABLE_SQL,
    POSTGRES_SESSION_CANCEL_TABLE_SQL,
    *POSTGRES_SESSION_SCHEMA_INDEX_STATEMENTS,
)
POSTGRES_SESSION_STORE_SCHEMA_DROP_STATEMENTS: tuple[str, ...] = (
    f"DROP TABLE IF EXISTS {POSTGRES_SESSION_CANCEL_TABLE_NAME}",
    f"DROP TABLE IF EXISTS {POSTGRES_SESSION_RESULTS_TABLE_NAME}",
    f"DROP TABLE IF EXISTS {POSTGRES_SESSION_PROGRESS_TABLE_NAME}",
    f"DROP TABLE IF EXISTS {POSTGRES_SESSION_METADATA_TABLE_NAME}",
)


class PostgresSessionStoreBootstrapError(RuntimeError):
    """Raised when PostgreSQL session-store startup cannot complete."""


class PostgresSessionStoreCursor(Protocol):
    """Minimal cursor interface used by the adapter and bootstrap helpers."""

    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None: ...
    def execute(self, query: str, params: object | None = None) -> object: ...
    def fetchone(self) -> object | None: ...
    def fetchall(self) -> list[object]: ...


class PostgresSessionStoreConnection(Protocol):
    """Minimal connection interface used by the adapter and bootstrap helpers."""

    def cursor(self) -> PostgresSessionStoreCursor: ...
    def commit(self) -> None: ...


POSTGRES_SESSION_METADATA_COLUMN_SQL = ", ".join(POSTGRES_SESSION_METADATA_FIELDS)
POSTGRES_SESSION_METADATA_EXISTS_SQL = "SELECT 1 FROM session_metadata WHERE session_id = %s"
POSTGRES_SESSION_METADATA_SELECT_SQL = """
SELECT session_id, mode, input_path, selected_detectors, status
FROM session_metadata
WHERE session_id = %s
""".strip()
POSTGRES_SESSION_METADATA_UPSERT_SQL = """
INSERT INTO session_metadata (
    session_id,
    mode,
    input_path,
    selected_detectors,
    status
) VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (session_id) DO UPDATE SET
    mode = EXCLUDED.mode,
    input_path = EXCLUDED.input_path,
    selected_detectors = EXCLUDED.selected_detectors,
    status = EXCLUDED.status
""".strip()
POSTGRES_SESSION_PROGRESS_COLUMN_SQL = ", ".join(POSTGRES_SESSION_PROGRESS_FIELDS)
POSTGRES_SESSION_PROGRESS_SELECT_SQL = """
SELECT
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
    status_detail
FROM session_progress
WHERE session_id = %s
""".strip()
POSTGRES_SESSION_PROGRESS_UPSERT_SQL = """
INSERT INTO session_progress (
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
    status_detail
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (session_id) DO UPDATE SET
    status = EXCLUDED.status,
    processed_count = EXCLUDED.processed_count,
    total_count = EXCLUDED.total_count,
    current_item = EXCLUDED.current_item,
    latest_result_detector = EXCLUDED.latest_result_detector,
    alert_count = EXCLUDED.alert_count,
    last_updated_utc = EXCLUDED.last_updated_utc,
    latest_result_detectors = EXCLUDED.latest_result_detectors,
    status_reason = EXCLUDED.status_reason,
    status_detail = EXCLUDED.status_detail
""".strip()
POSTGRES_SESSION_RESULT_SELECT_FIELDS: tuple[str, ...] = (
    "id",
    "session_id",
    "detector_id",
    "payload",
)
POSTGRES_SESSION_RESULT_SELECT_COLUMN_SQL = ", ".join(
    (
        "id",
        "session_id",
        "detector_id",
        "payload_json AS payload",
    )
)
POSTGRES_SESSION_RESULTS_SELECT_SQL = """
SELECT id, session_id, detector_id, payload_json AS payload
FROM session_result_events
WHERE session_id = %s
ORDER BY id ASC
""".strip()
POSTGRES_SESSION_RESULTS_INSERT_SQL = """
INSERT INTO session_result_events (
    session_id,
    detector_id,
    detector_name,
    event_timestamp_utc,
    payload_json
) VALUES (%s, %s, %s, %s, %s)
""".strip()
POSTGRES_SESSION_CANCEL_EXISTS_SQL = """
SELECT 1
FROM session_cancel_requests
WHERE session_id = %s AND cancel_requested = TRUE
""".strip()
POSTGRES_SESSION_CANCEL_UPSERT_SQL = """
INSERT INTO session_cancel_requests (
    session_id,
    cancel_requested
) VALUES (%s, %s)
ON CONFLICT (session_id) DO UPDATE SET
    cancel_requested = EXCLUDED.cancel_requested
""".strip()


class PostgresSessionStore(SessionStore):
    """Small PostgreSQL-backed `SessionStore` adapter.

    The adapter owns an injected connection plus the stable store-method
    surface. Query details stay close to the shared contract instead of
    expanding into a larger ORM or repository layer prematurely. Ordered result
    history is preserved by durable row id, not detector timestamp ordering.
    """

    def __init__(self, connection: PostgresSessionStoreConnection) -> None:
        self._connection = connection

    @property
    def connection(self) -> PostgresSessionStoreConnection:
        """Expose the injected connection for focused tests and smoke helpers."""
        return self._connection

    def session_exists(self, session_id: str) -> bool:
        """Return whether durable metadata exists for one session."""
        return self._fetch_one(
            POSTGRES_SESSION_METADATA_EXISTS_SQL,
            (session_id,),
        ) is not None

    def read_snapshot(self, session_id: str) -> SessionSnapshotPayload:
        """Assemble one public session snapshot from PostgreSQL rows."""
        metadata = self._read_metadata_payload(session_id)
        if metadata is None:
            return build_empty_session_snapshot_payload()
        progress = self._read_progress_payload(session_id)
        results = self.read_results(session_id)
        return build_session_snapshot_payload(
            session=metadata,
            progress=progress,
            alerts=[],
            results=results,
        )

    def read_results(self, session_id: str) -> list[ResultEventPayload]:
        """Return ordered detector-result payloads for one session."""
        rows = _sort_result_rows_by_append_sequence(
            self._fetch_all(POSTGRES_SESSION_RESULTS_SELECT_SQL, (session_id,))
        )
        results: list[ResultEventPayload] = []
        for row in rows:
            payload = parse_result_event_payload(
                _row_to_payload(POSTGRES_SESSION_RESULT_SELECT_FIELDS, row)
            )
            if payload is not None:
                results.append(cast(ResultEventPayload, payload))
        return results

    def write_metadata(self, metadata: SessionMetadata) -> None:
        """Upsert the authoritative metadata row for one session."""
        metadata.validate()
        self._execute_and_commit(
            POSTGRES_SESSION_METADATA_UPSERT_SQL,
            (
                metadata.session_id,
                metadata.mode,
                metadata.input_path,
                _postgres_json_param(metadata.selected_detectors),
                metadata.status,
            ),
        )

    def write_progress(self, progress: SessionProgress) -> None:
        """Upsert the latest progress row for one session."""
        progress.validate()
        self._execute_and_commit(
            POSTGRES_SESSION_PROGRESS_UPSERT_SQL,
            (
                progress.session_id,
                progress.status,
                progress.processed_count,
                progress.total_count,
                progress.current_item,
                progress.latest_result_detector,
                progress.alert_count,
                progress.last_updated_utc,
                _postgres_json_param(progress.latest_result_detectors),
                progress.status_reason,
                progress.status_detail,
            ),
        )

    def append_result(self, event: ResultEvent) -> None:
        """Append one detector-result row while preserving read order."""
        event.validate()
        self._execute_and_commit(
            POSTGRES_SESSION_RESULTS_INSERT_SQL,
            _build_postgres_result_insert_params(event),
        )

    def request_cancel(self, session_id: str) -> None:
        """Persist current cancel intent for one session."""
        self._execute_and_commit(
            POSTGRES_SESSION_CANCEL_UPSERT_SQL,
            (session_id, True),
        )

    def is_cancel_requested(self, session_id: str) -> bool:
        """Return whether current cancel intent exists for one session."""
        return self._fetch_one(
            POSTGRES_SESSION_CANCEL_EXISTS_SQL,
            (session_id,),
        ) is not None

    def _read_metadata_payload(self, session_id: str) -> SessionMetadataPayload | None:
        """Return parsed metadata or `None` when the row is missing or invalid."""
        return cast(
            SessionMetadataPayload | None,
            self._read_optional_payload(
                POSTGRES_SESSION_METADATA_SELECT_SQL,
                (session_id,),
                POSTGRES_SESSION_METADATA_FIELDS,
                parse_session_metadata_payload,
            ),
        )

    def _read_progress_payload(self, session_id: str) -> SessionProgressPayload | None:
        """Return parsed progress or `None` when the row is missing or invalid."""
        return cast(
            SessionProgressPayload | None,
            self._read_optional_payload(
                POSTGRES_SESSION_PROGRESS_SELECT_SQL,
                (session_id,),
                POSTGRES_SESSION_PROGRESS_FIELDS,
                parse_session_progress_payload,
            ),
        )

    def _execute_and_commit(
        self,
        query: str,
        params: object | None = None,
    ) -> None:
        """Execute one write statement and commit it."""
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
        self.connection.commit()

    def _fetch_one(self, query: str, params: object | None = None) -> object | None:
        """Execute one query and return the first row."""
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def _fetch_all(self, query: str, params: object | None = None) -> list[object]:
        """Execute one query and return all rows."""
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def _read_optional_payload(
        self,
        query: str,
        params: object | None,
        columns: tuple[str, ...],
        parser: Callable[[dict[str, object]], object | None],
    ) -> object | None:
        """Read one optional row and parse it through a shared payload parser."""
        return _parse_optional_row_payload(
            self._fetch_one(query, params),
            columns,
            parser,
        )


def _execute_schema_statements(
    connection: PostgresSessionStoreConnection,
    statements: tuple[str, ...],
) -> None:
    """Run an ordered schema statement list and commit on success."""
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
    connection.commit()


def _parse_optional_row_payload(
    row: object | None,
    columns: tuple[str, ...],
    parser: Callable[[dict[str, object]], object | None],
) -> SessionMetadataPayload | SessionProgressPayload | None:
    """Normalize one optional row and parse it into a shared payload shape."""
    if row is None:
        return None
    return cast(
        SessionMetadataPayload | SessionProgressPayload | None,
        parser(_row_to_payload(columns, row)),
    )


def _row_to_payload(columns: tuple[str, ...], row: object) -> dict[str, object]:
    """Normalize one fetched row into a plain payload dictionary."""
    if isinstance(row, Mapping):
        return {column: row[column] for column in columns}
    if hasattr(row, "_mapping"):
        mapping = cast(Mapping[str, object], getattr(row, "_mapping"))
        return {column: mapping[column] for column in columns}
    if isinstance(row, tuple):
        return dict(zip(columns, row, strict=True))
    raise TypeError(f"Unsupported PostgreSQL session-store row type: {type(row)!r}")


def _sort_result_rows_by_append_sequence(rows: list[object]) -> list[object]:
    """Return result rows in durable append order.

    The SQL query already orders by `id ASC`; this helper keeps that contract
    explicit inside the adapter and protects simple doubles from accidentally
    smuggling timestamp-based or insertion-list ordering into behavior tests.
    Rows without a usable numeric `id` keep their existing relative order.
    """
    indexed_rows = list(enumerate(rows))

    def sort_key(item: tuple[int, object]) -> tuple[int, int]:
        original_index, row = item
        payload = _row_to_payload(POSTGRES_SESSION_RESULT_SELECT_FIELDS, row)
        row_id = payload.get("id")
        if isinstance(row_id, int):
            return (0, row_id)
        return (1, original_index)

    return [row for _, row in sorted(indexed_rows, key=sort_key)]


def _build_postgres_result_insert_params(
    event: ResultEvent,
) -> tuple[str, str, str | None, str | None, str]:
    """Project shared query fields while keeping the raw payload intact."""
    payload = event.payload
    detector_name = payload.get("detector_name")
    event_timestamp_utc = payload.get("timestamp_utc")
    return (
        event.session_id,
        event.detector_id,
        detector_name if isinstance(detector_name, str) else None,
        event_timestamp_utc if isinstance(event_timestamp_utc, str) else None,
        _postgres_json_param(payload),
    )


def _postgres_json_param(value: object) -> str:
    """Serialize one JSONB-bound value for the real PostgreSQL driver path."""
    return json.dumps(value)


def load_postgres_session_store_driver() -> ModuleType:
    """Import the PostgreSQL driver required by this backend."""
    try:
        return importlib.import_module("psycopg")
    except ImportError as err:
        raise PostgresSessionStoreBootstrapError(
            "Install psycopg to use the PostgreSQL session-store backend"
        ) from err


def connect_postgres_session_store(
    settings: PostgresSessionStoreSettings | None = None,
) -> PostgresSessionStoreConnection:
    """Open one PostgreSQL connection for bootstrap and store operations."""
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
    """Create the known session-store tables and indexes for this contract."""
    _execute_schema_statements(connection, POSTGRES_SESSION_STORE_SCHEMA_STATEMENTS)


def drop_postgres_session_store_schema(connection: PostgresSessionStoreConnection) -> None:
    """Drop the known session-store tables in reverse dependency order."""
    _execute_schema_statements(connection, POSTGRES_SESSION_STORE_SCHEMA_DROP_STATEMENTS)


def reset_postgres_session_store_schema(connection: PostgresSessionStoreConnection) -> None:
    """Reset the known session-store tables for isolated live smoke runs."""
    drop_postgres_session_store_schema(connection)
    initialize_postgres_session_store(connection)


def bootstrap_postgres_session_store(
    settings: PostgresSessionStoreSettings | None = None,
) -> PostgresSessionStoreConnection:
    """Open the PostgreSQL backend and bootstrap known tables only on opt-in."""
    resolved_settings = settings or get_postgres_session_store_settings()
    connection = connect_postgres_session_store(resolved_settings)
    if should_auto_create_postgres_session_store_tables(resolved_settings):
        initialize_postgres_session_store(connection)
    return connection


def _validated_postgres_session_database_url(
    settings: PostgresSessionStoreSettings,
) -> str:
    """Validate settings and return the configured PostgreSQL URL."""
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
