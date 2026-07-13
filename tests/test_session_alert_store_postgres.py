"""Store-level contract and bootstrap tests for the PostgreSQL alert store.

This file owns the concrete Postgres backend below the service and boundary
layers: schema/bootstrap behavior, SQL mapping, row normalization,
unknown-session parity, and the opt-in live store smoke path. Live cases run
only with an explicitly selected, disposable PostgreSQL database. File-backed
alerts remain the default runtime backend outside this explicit seam.
"""

from __future__ import annotations

from datetime import datetime
import os
from typing import Any

import pytest

from session_alert_incidents import (
    build_session_incident_summary,
    build_session_timeline,
)
from session_alerts import (
    filter_session_alert_events,
    read_session_alert_events,
    summarize_session_alert_events,
)
from session_alert_store import AlertEventPayload, SessionAlertsNotFoundError
from session_alert_store_postgres import (
    POSTGRES_ALERT_EVENT_COLUMNS,
    POSTGRES_ALERT_EVENT_NULLABLE_COLUMNS,
    POSTGRES_ALERT_EVENT_READ_ORDER,
    POSTGRES_ALERT_EVENTS_INSERT_SQL,
    POSTGRES_ALERT_EVENTS_READ_SQL,
    POSTGRES_ALERT_STORE_SCHEMA_DROP_STATEMENTS,
    POSTGRES_ALERT_STORE_SCHEMA_STATEMENTS,
    POSTGRES_ALERT_TIMESTAMP_FORMAT,
    PostgresSessionAlertStore,
    bootstrap_postgres_alert_store,
    connect_postgres_alert_store,
    initialize_postgres_alert_store,
    reset_postgres_alert_store_schema,
)
from session_alert_store_postgres_config import (
    POSTGRES_ALERT_DATABASE_URL_ENV,
    PostgresAlertStoreSettings,
)
from session_models import AlertEvent, EventSeverity
from tests.session_alert_test_support import (
    REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    build_isolated_postgres_alert_store,
    build_normalized_alert,
    build_unique_session_id,
    close_store_if_possible,
)


class RecordingCursor:
    """Small cursor that records SQL and replays preloaded rows."""

    def __init__(
        self,
        *,
        executed_statements: list[tuple[str, object | None]],
        rows: list[object] | None = None,
    ) -> None:
        self._executed_statements = executed_statements
        self._rows = rows or []

    def __enter__(self) -> "RecordingCursor":
        """Return the same cursor inside the context manager block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        """Close the recording context without extra cleanup behavior."""

    def execute(self, query: str, params: object | None = None) -> object:
        """Record one executed SQL statement."""
        self._executed_statements.append((query, params))
        return object()

    def fetchall(self) -> list[object]:
        """Return the preloaded rows for one read query."""
        return list(self._rows)


class RecordingConnection:
    """Small connection that records executed statements and commit state."""

    def __init__(self, *, rows: list[object] | None = None) -> None:
        self.executed_statements: list[tuple[str, object | None]] = []
        self.committed = False
        self.commit_count = 0
        self._rows = rows or []

    def cursor(self) -> RecordingCursor:
        """Return a recording cursor over the shared statement log."""
        return RecordingCursor(
            executed_statements=self.executed_statements,
            rows=self._rows,
        )

    def commit(self) -> None:
        """Record that the current store operation committed successfully."""
        self.committed = True
        self.commit_count += 1


class FailingCursor:
    """Cursor that raises on execute so failure paths stay easy to assert."""

    def __enter__(self) -> "FailingCursor":
        """Return the same failing cursor inside the context manager block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        """Close the failing cursor context without extra cleanup work."""
        return None

    def execute(self, query: str, params: object | None = None) -> object:
        """Raise a stable database failure during one store operation."""
        raise RuntimeError("database failed")

    def fetchall(self) -> list[object]:
        """Return an empty row list after a forced execute failure."""
        return []


class FailingConnection:
    """Connection that always returns the failing cursor."""

    def __init__(self) -> None:
        self.committed = False

    def cursor(self) -> FailingCursor:
        """Return the failing cursor used by the propagation tests."""
        return FailingCursor()

    def commit(self) -> None:
        """Record an otherwise unexpected commit call on the failing connection."""
        self.committed = True


class MissingSchemaCursor:
    """Small cursor that simulates a missing alert table after bootstrap."""

    def __enter__(self) -> "MissingSchemaCursor":
        """Return the same missing-schema cursor inside the context manager block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        """Close the missing-schema cursor context without extra cleanup work."""
        return None

    def execute(self, query: str, params: object | None = None) -> object:
        """Raise the missing-table failure used by disabled-auto-create tests."""
        raise RuntimeError('relation "session_alert_events" does not exist')

    def fetchall(self) -> list[object]:
        """Return an empty row list after the missing-schema failure."""
        return []


class MissingSchemaConnection:
    """Connection used to prove disabled auto-create leaves schema errors visible."""

    def cursor(self) -> MissingSchemaCursor:
        """Return the missing-schema cursor used by the bootstrap-path test."""
        return MissingSchemaCursor()

    def commit(self) -> None:
        """Ignore commit calls because the missing-schema cursor always fails first."""
        return None


class MidSchemaFailureCursor:
    """Small cursor that fails partway through schema bootstrap."""

    def __init__(self) -> None:
        self.calls = 0

    def __enter__(self) -> "MidSchemaFailureCursor":
        """Return the same cursor inside the context manager block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        """Close the cursor context without extra cleanup work."""
        return None

    def execute(self, query: str, params: object | None = None) -> object:
        """Succeed once, then fail before bootstrap can commit."""
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("index creation failed")
        return object()

    def fetchall(self) -> list[object]:
        """Return no rows because schema bootstrap never performs a read."""
        return []


class MidSchemaFailureConnection:
    """Connection that exposes a mid-bootstrap failure before commit."""

    def __init__(self) -> None:
        self.committed = False
        self.cursor_instance = MidSchemaFailureCursor()

    def cursor(self) -> MidSchemaFailureCursor:
        """Return the reusable cursor used by the mid-bootstrap failure test."""
        return self.cursor_instance

    def commit(self) -> None:
        """Record an unexpected commit if bootstrap reaches the end."""
        self.committed = True


class FakePsycopgModule:
    """Small fake psycopg module for connect-path tests."""

    class Error(Exception):
        """Small driver-shaped base error used by bootstrap tests."""

    def __init__(
        self,
        *,
        connection: RecordingConnection | None = None,
        connect_error: BaseException | None = None,
    ) -> None:
        self.connection = connection or RecordingConnection()
        self.connect_error = connect_error
        self.connect_calls: list[str] = []

    def connect(self, database_url: str) -> RecordingConnection:
        """Record one connect call and optionally raise one fake driver error."""
        self.connect_calls.append(database_url)
        if self.connect_error is not None:
            raise self.connect_error
        return self.connection


class KnownOnlySessionStore:
    """Minimal session store stub for alert/session existence checks."""

    def __init__(self, *known_session_ids: str) -> None:
        self._known_session_ids = set(known_session_ids)
        self.checked_session_ids: list[str] = []

    def session_exists(self, session_id: str) -> bool:
        """Return whether the test session id is known to this store."""
        self.checked_session_ids.append(session_id)
        return session_id in self._known_session_ids


def _mark_known_sessions(
    monkeypatch: pytest.MonkeyPatch,
    *session_ids: str,
) -> None:
    """Patch the shared known-session adapter for one Postgres store test."""
    known_sessions = set(session_ids)

    def _require_known_session(candidate_session_id: str) -> None:
        if candidate_session_id not in known_sessions:
            raise SessionAlertsNotFoundError(candidate_session_id)

    monkeypatch.setattr(
        "session_alert_store_postgres.require_known_session",
        _require_known_session,
    )


def _raise_unknown_session(session_id: str) -> None:
    """Raise the shared unknown-session error for one patched store test."""
    raise SessionAlertsNotFoundError(session_id)


def _postgres_store(
    *,
    rows: list[object] | None = None,
) -> tuple[PostgresSessionAlertStore, RecordingConnection]:
    """Build one PostgreSQL store plus its recording connection."""
    connection = RecordingConnection(rows=rows)
    return PostgresSessionAlertStore(connection), connection


def _sample_alert_event(
    *,
    session_id: str = "session-123",
    timestamp_utc: str = "2026-05-18 10:30:45",
    detector_id: str = "black_screen",
    title: str = "Black screen detected",
    message: str = "The frame was almost fully black.",
    severity: EventSeverity = "warning",
    source_name: str = "segment-001.ts",
    window_index: int | None = 3,
    window_start_sec: float | None = 6.0,
) -> AlertEvent:
    """Build one stable alert event for store tests."""
    return AlertEvent(
        session_id=session_id,
        timestamp_utc=timestamp_utc,
        detector_id=detector_id,
        title=title,
        message=message,
        severity=severity,
        source_name=source_name,
        window_index=window_index,
        window_start_sec=window_start_sec,
    )


def _sample_alert_row(
    *,
    session_id: str = "session-123",
    timestamp_utc: str = "2026-05-18 10:30:45",
    detector_id: str = "black_screen",
    title: str = "Black screen detected",
    message: str = "The frame was almost fully black.",
    severity: str = "warning",
    source_name: str = "segment-001.ts",
    window_index: int | None = 3,
    window_start_sec: float | None = 6.0,
) -> tuple[object, ...]:
    """Build one stable database-shaped alert row for store tests."""
    return (
        session_id,
        timestamp_utc,
        detector_id,
        title,
        message,
        severity,
        source_name,
        window_index,
        window_start_sec,
    )


def _sample_normalized_alert(
    *,
    session_id: str = "session-123",
    timestamp_utc: str = "2026-05-18 10:30:45",
    detector_id: str = "black_screen",
    title: str = "Black screen detected",
    message: str = "The frame was almost fully black.",
    severity: EventSeverity = "warning",
    source_name: str = "segment-001.ts",
    window_index: int | None = 3,
    window_start_sec: float | None = 6.0,
) -> AlertEventPayload:
    """Build one normalized alert row matching the shared seam payload."""
    return build_normalized_alert(
        session_id,
        timestamp_utc=timestamp_utc,
        detector_id=detector_id,
        title=title,
        message=message,
        severity=severity,
        source_name=source_name,
        window_index=window_index,
        window_start_sec=window_start_sec,
    )


def test_postgres_alert_contract_constants_match_current_alert_payload() -> None:
    """The Postgres seam should preserve the current raw alert row contract."""
    assert POSTGRES_ALERT_EVENT_COLUMNS == (
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
    assert POSTGRES_ALERT_EVENT_NULLABLE_COLUMNS == (
        "window_index",
        "window_start_sec",
    )
    assert POSTGRES_ALERT_EVENT_READ_ORDER == "id ASC"


def test_initialize_postgres_alert_store_executes_schema_statements_in_order() -> None:
    """Schema bootstrap should execute the frozen table/index statements in order."""
    connection = RecordingConnection()

    initialize_postgres_alert_store(connection)

    assert connection.executed_statements == [
        (statement, None) for statement in POSTGRES_ALERT_STORE_SCHEMA_STATEMENTS
    ]
    assert connection.committed is True


def test_initialize_postgres_alert_store_does_not_commit_after_mid_schema_failure() -> None:
    """Bootstrap should not commit partial schema work after a later statement fails."""
    connection = MidSchemaFailureConnection()

    with pytest.raises(RuntimeError, match="index creation failed"):
        initialize_postgres_alert_store(connection)

    assert connection.cursor_instance.calls == 2
    assert connection.committed is False


def test_reset_postgres_alert_store_schema_recreates_known_schema_after_drop() -> None:
    """Isolation reset should drop the alert table before recreating its schema."""
    connection = RecordingConnection()

    reset_postgres_alert_store_schema(connection)

    expected_statements = [
        *POSTGRES_ALERT_STORE_SCHEMA_DROP_STATEMENTS,
        *POSTGRES_ALERT_STORE_SCHEMA_STATEMENTS,
    ]
    assert connection.executed_statements == [
        (statement, None) for statement in expected_statements
    ]
    assert connection.commit_count == 2


def test_bootstrap_postgres_alert_store_initializes_schema_when_enabled(
    monkeypatch,
) -> None:
    """Bootstrap should connect and initialize when auto-create is enabled."""
    settings = PostgresAlertStoreSettings(
        database_url="postgresql://alerts:secret@db.example/esm",
        auto_create_tables=True,
    )
    connection = RecordingConnection()
    seen: list[str] = []

    def fake_connect(
        resolved_settings: PostgresAlertStoreSettings,
    ) -> RecordingConnection:
        assert resolved_settings == settings
        seen.append("connect")
        return connection

    def fake_initialize(resolved_connection: RecordingConnection) -> None:
        assert resolved_connection is connection
        seen.append("initialize")

    monkeypatch.setattr(
        "session_alert_store_postgres.connect_postgres_alert_store",
        fake_connect,
    )
    monkeypatch.setattr(
        "session_alert_store_postgres.initialize_postgres_alert_store",
        fake_initialize,
    )

    result = bootstrap_postgres_alert_store(settings)

    assert result is connection
    assert seen == ["connect", "initialize"]


def test_bootstrap_postgres_alert_store_skips_schema_init_when_disabled(
    monkeypatch,
) -> None:
    """Bootstrap should skip schema creation when auto-create is disabled."""
    settings = PostgresAlertStoreSettings(
        database_url="postgresql://alerts:secret@db.example/esm",
        auto_create_tables=False,
    )
    connection = RecordingConnection()
    seen: list[str] = []

    def fake_connect(
        resolved_settings: PostgresAlertStoreSettings,
    ) -> RecordingConnection:
        assert resolved_settings == settings
        seen.append("connect")
        return connection

    def fake_initialize(resolved_connection: RecordingConnection) -> None:
        assert resolved_connection is connection
        seen.append("initialize")

    monkeypatch.setattr(
        "session_alert_store_postgres.connect_postgres_alert_store",
        fake_connect,
    )
    monkeypatch.setattr(
        "session_alert_store_postgres.initialize_postgres_alert_store",
        fake_initialize,
    )

    result = bootstrap_postgres_alert_store(settings)

    assert result is connection
    assert seen == ["connect"]


def test_bootstrap_postgres_alert_store_uses_cached_settings_when_not_provided(
    monkeypatch,
) -> None:
    """Bootstrap should fall back to the cached Postgres alert-store settings."""
    settings = PostgresAlertStoreSettings(
        database_url="postgresql://alerts:secret@db.example/esm",
        auto_create_tables=False,
    )
    connection = RecordingConnection()
    seen: list[str] = []

    monkeypatch.setattr(
        "session_alert_store_postgres.get_postgres_alert_store_settings",
        lambda: settings,
    )

    def fake_connect(
        resolved_settings: PostgresAlertStoreSettings,
    ) -> RecordingConnection:
        assert resolved_settings == settings
        seen.append("connect")
        return connection

    monkeypatch.setattr(
        "session_alert_store_postgres.connect_postgres_alert_store",
        fake_connect,
    )

    result = bootstrap_postgres_alert_store()

    assert result is connection
    assert seen == ["connect"]


def test_bootstrap_postgres_alert_store_explicit_settings_override_stale_cached_env(
    monkeypatch,
) -> None:
    """Explicit bootstrap settings should win over already-cached env-derived settings."""
    stale_settings = PostgresAlertStoreSettings(
        database_url="postgresql://stale:stale@localhost:5432/election_stream_monitor",
        auto_create_tables=False,
    )
    explicit_settings = PostgresAlertStoreSettings(
        database_url="postgresql://fresh:secret@db.example/esm",
        auto_create_tables=False,
    )
    connection = RecordingConnection()
    seen_settings: list[PostgresAlertStoreSettings] = []

    monkeypatch.setenv(POSTGRES_ALERT_DATABASE_URL_ENV, stale_settings.database_url or "")
    monkeypatch.setattr(
        "session_alert_store_postgres.get_postgres_alert_store_settings",
        lambda: stale_settings,
    )

    def fake_connect(
        resolved_settings: PostgresAlertStoreSettings,
    ) -> RecordingConnection:
        seen_settings.append(resolved_settings)
        return connection

    monkeypatch.setattr(
        "session_alert_store_postgres.connect_postgres_alert_store",
        fake_connect,
    )

    result = bootstrap_postgres_alert_store(explicit_settings)

    assert result is connection
    assert seen_settings == [explicit_settings]


def test_connect_postgres_alert_store_reports_missing_psycopg_dependency(
    monkeypatch,
) -> None:
    """Bootstrap should fail clearly when the psycopg dependency is unavailable."""
    monkeypatch.setattr(
        "session_alert_store_postgres.importlib.import_module",
        lambda name: (_ for _ in ()).throw(ImportError("psycopg missing")),
    )

    with pytest.raises(
        RuntimeError,
        match="Install psycopg to use the PostgreSQL alert-store bootstrap path",
    ):
        connect_postgres_alert_store(
            PostgresAlertStoreSettings(
                database_url="postgresql://alerts:secret@db.example/esm",
                auto_create_tables=True,
            )
        )


def test_connect_postgres_alert_store_uses_validated_database_url_with_driver_success(
    monkeypatch,
) -> None:
    """Bootstrap should pass the validated URL through to psycopg.connect."""
    fake_psycopg = FakePsycopgModule()
    settings = PostgresAlertStoreSettings(
        database_url="postgresql://alerts:secret@db.example/esm",
        auto_create_tables=True,
    )
    monkeypatch.setattr(
        "session_alert_store_postgres.importlib.import_module",
        lambda name: fake_psycopg,
    )

    connection = connect_postgres_alert_store(settings)

    assert connection is fake_psycopg.connection
    assert fake_psycopg.connect_calls == [settings.database_url]


def test_connect_postgres_alert_store_wraps_driver_connection_errors(
    monkeypatch,
) -> None:
    """Driver connection failures should become one stable bootstrap error."""
    fake_psycopg = FakePsycopgModule(
        connect_error=FakePsycopgModule.Error("database unavailable")
    )
    monkeypatch.setattr(
        "session_alert_store_postgres.importlib.import_module",
        lambda name: fake_psycopg,
    )

    with pytest.raises(
        RuntimeError,
        match="Could not connect to the PostgreSQL alert store",
    ):
        connect_postgres_alert_store(
            PostgresAlertStoreSettings(
                database_url="postgresql://alerts:secret@db.example/esm",
                auto_create_tables=True,
            )
        )

    assert fake_psycopg.connect_calls == [
        "postgresql://alerts:secret@db.example/esm"
    ]


def test_bootstrap_postgres_alert_store_surfaces_schema_init_failures_after_connect(
    monkeypatch,
) -> None:
    """Bootstrap should not hide schema-init failures after a successful connect."""
    settings = PostgresAlertStoreSettings(
        database_url="postgresql://alerts:secret@db.example/esm",
        auto_create_tables=True,
    )
    connection = RecordingConnection()
    seen: list[str] = []

    def fake_connect(
        resolved_settings: PostgresAlertStoreSettings,
    ) -> RecordingConnection:
        assert resolved_settings == settings
        seen.append("connect")
        return connection

    def fake_initialize(resolved_connection: RecordingConnection) -> None:
        assert resolved_connection is connection
        seen.append("initialize")
        raise RuntimeError("schema bootstrap failed")

    monkeypatch.setattr(
        "session_alert_store_postgres.connect_postgres_alert_store",
        fake_connect,
    )
    monkeypatch.setattr(
        "session_alert_store_postgres.initialize_postgres_alert_store",
        fake_initialize,
    )

    with pytest.raises(RuntimeError, match="schema bootstrap failed"):
        bootstrap_postgres_alert_store(settings)

    assert seen == ["connect", "initialize"]


def test_bootstrap_postgres_alert_store_leaves_missing_schema_failures_visible_when_auto_create_is_disabled(
    monkeypatch,
) -> None:
    """Disabled schema auto-creation should not hide the first missing-table failure."""
    settings = PostgresAlertStoreSettings(
        database_url="postgresql://alerts:secret@db.example/esm",
        auto_create_tables=False,
    )
    connection = MissingSchemaConnection()
    monkeypatch.setattr(
        "session_alert_store_postgres.connect_postgres_alert_store",
        lambda resolved_settings: connection,
    )

    store = PostgresSessionAlertStore(bootstrap_postgres_alert_store(settings))

    with pytest.raises(RuntimeError, match='relation "session_alert_events" does not exist'):
        store.append_alert(_sample_alert_event())


def test_postgres_session_alert_store_appends_one_alert_event() -> None:
    """The PostgreSQL store should insert one raw alert row and commit once."""
    event = _sample_alert_event()
    store, connection = _postgres_store()

    store.append_alert(event)

    assert connection.executed_statements == [
        (
            POSTGRES_ALERT_EVENTS_INSERT_SQL,
            (
                "session-123",
                datetime.strptime("2026-05-18 10:30:45", POSTGRES_ALERT_TIMESTAMP_FORMAT),
                "black_screen",
                "Black screen detected",
                "The frame was almost fully black.",
                "warning",
                "segment-001.ts",
                3,
                6.0,
            ),
        )
    ]
    assert connection.committed is True


def test_postgres_session_alert_store_reads_alert_rows_in_persisted_order(
    monkeypatch,
) -> None:
    """The PostgreSQL store should preserve append-order semantics on reads."""
    store, connection = _postgres_store(
        rows=[
            _sample_alert_row(
                timestamp_utc="2026-05-18 10:30:45",
                title="First alert",
                message="First message.",
                source_name="segment-001.ts",
                window_index=1,
                window_start_sec=0.0,
            ),
            _sample_alert_row(
                timestamp_utc="2026-05-18 10:30:46",
                title="Second alert",
                message="Second message.",
                source_name="segment-002.ts",
                window_index=2,
                window_start_sec=1.0,
            ),
        ]
    )
    _mark_known_sessions(monkeypatch, "session-123")

    alerts = store.read_session_alert_events("session-123")

    assert connection.executed_statements == [
        (POSTGRES_ALERT_EVENTS_READ_SQL, ("session-123",))
    ]
    assert [alert["title"] for alert in alerts] == ["First alert", "Second alert"]


def test_postgres_session_alert_store_normalizes_nullable_window_fields(
    monkeypatch,
) -> None:
    """The PostgreSQL store should preserve nullable window fields on reads."""
    store, _ = _postgres_store(
        rows=[
            _sample_alert_row(
                window_index=None,
                window_start_sec=None,
            )
        ]
    )
    _mark_known_sessions(monkeypatch, "session-123")

    alerts = store.read_session_alert_events("session-123")

    assert alerts == [
        _sample_normalized_alert(
            window_index=None,
            window_start_sec=None,
        )
    ]


def test_postgres_session_alert_store_rejects_unknown_session_before_read(
    monkeypatch,
) -> None:
    """The PostgreSQL store should preserve current unknown-session semantics."""
    store, connection = _postgres_store()
    monkeypatch.setattr(
        "session_alert_store_postgres.require_known_session",
        _raise_unknown_session,
    )

    with pytest.raises(SessionAlertsNotFoundError, match="session-unknown"):
        store.read_session_alert_events("session-unknown")

    assert connection.executed_statements == []


def test_postgres_session_alert_store_uses_active_session_store_for_known_session_check(
    monkeypatch,
) -> None:
    """Postgres alert reads should not require file-backed session metadata."""
    session_store = KnownOnlySessionStore("postgres-session-123")
    monkeypatch.setattr(
        "session_alert_store.get_default_session_store",
        lambda: session_store,
    )
    store, connection = _postgres_store(
        rows=[_sample_alert_row(session_id="postgres-session-123")]
    )

    alerts = store.read_session_alert_events("postgres-session-123")

    assert session_store.checked_session_ids == ["postgres-session-123"]
    assert connection.executed_statements == [
        (POSTGRES_ALERT_EVENTS_READ_SQL, ("postgres-session-123",))
    ]
    assert alerts == [_sample_normalized_alert(session_id="postgres-session-123")]


def test_postgres_session_alert_store_returns_empty_list_for_known_session_without_rows(
    monkeypatch,
) -> None:
    """The PostgreSQL store should keep known-session empty-history behavior."""
    store, _ = _postgres_store(rows=[])
    _mark_known_sessions(monkeypatch, "session-123")

    alerts = store.read_session_alert_events("session-123")

    assert alerts == []


def test_postgres_session_alert_store_rejects_unexpected_row_shape(
    monkeypatch,
) -> None:
    """The PostgreSQL store should fail fast on broken internal row mapping."""
    store, _ = _postgres_store(rows=[("too", "short")])
    _mark_known_sessions(monkeypatch, "session-123")

    with pytest.raises(
        ValueError,
        match="does not match the expected column contract",
    ):
        store.read_session_alert_events("session-123")


def test_postgres_session_alert_store_propagates_append_failures_without_commit() -> None:
    """Append failures should surface clearly instead of pretending the write succeeded."""
    store = PostgresSessionAlertStore(FailingConnection())

    with pytest.raises(RuntimeError, match="database failed"):
        store.append_alert(_sample_alert_event())


def test_postgres_session_alert_store_rejects_invalid_timestamp_before_execute_or_commit() -> None:
    """Malformed timestamps should fail before the store issues a write query."""
    store, connection = _postgres_store()

    with pytest.raises(ValueError):
        store.append_alert(_sample_alert_event(timestamp_utc="bad-timestamp"))

    assert connection.executed_statements == []
    assert connection.committed is False


def test_postgres_session_alert_store_propagates_read_failures(
    monkeypatch,
) -> None:
    """Read failures should surface clearly instead of being collapsed into empty data."""
    store = PostgresSessionAlertStore(FailingConnection())
    _mark_known_sessions(monkeypatch, "session-123")

    with pytest.raises(RuntimeError, match="database failed"):
        store.read_session_alert_events("session-123")


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL alert-store smoke test is opt-in.",
)
def test_real_postgres_alert_store_reset_clears_old_rows_and_remains_usable(
    monkeypatch,
) -> None:
    """A destructive live reset should clear rows and restore normal public writes."""
    session_id = build_unique_session_id("real-postgres-reset")
    _mark_known_sessions(monkeypatch, session_id)
    connection, store = build_isolated_postgres_alert_store()
    try:
        assert store.read_session_alert_events(session_id) == []

        store.append_alert(
            _sample_alert_event(
                session_id=session_id,
                title="Stale alert before reset",
                message="This row must not survive schema reset.",
            )
        )
        assert [alert["title"] for alert in store.read_session_alert_events(session_id)] == [
            "Stale alert before reset"
        ]

        reset_postgres_alert_store_schema(connection)

        assert store.read_session_alert_events(session_id) == []
        store.append_alert(
            _sample_alert_event(
                session_id=session_id,
                title="Fresh alert after reset",
                message="The recreated schema accepts normal store writes.",
            )
        )
        assert [alert["title"] for alert in store.read_session_alert_events(session_id)] == [
            "Fresh alert after reset"
        ]
    finally:
        close_store_if_possible(connection)


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL alert-store smoke test is opt-in.",
)
def test_real_postgres_alert_store_smoke_round_trip(
    monkeypatch,
) -> None:
    """A live write should agree between the public store and raw read-model seam."""
    session_id = build_unique_session_id("real-postgres-smoke")
    _mark_known_sessions(monkeypatch, session_id)
    connection = connect_postgres_alert_store()
    try:
        initialize_postgres_alert_store(connection)
        store = PostgresSessionAlertStore(connection)
        store.append_alert(
            _sample_alert_event(
                session_id=session_id,
                timestamp_utc="2026-05-19 20:00:00",
                title="Real smoke alert",
                message="Round-tripped through a live PostgreSQL connection.",
                window_index=None,
                window_start_sec=None,
            )
        )
        store_alerts = store.read_session_alert_events(session_id)
        read_model_alerts = read_session_alert_events(session_id, store=store)
    finally:
        close_store_if_possible(connection)

    expected_alerts = [
        _sample_normalized_alert(
            session_id=session_id,
            timestamp_utc="2026-05-19 20:00:00",
            title="Real smoke alert",
            message="Round-tripped through a live PostgreSQL connection.",
            window_index=None,
            window_start_sec=None,
        )
    ]
    assert store_alerts == expected_alerts
    assert read_model_alerts == expected_alerts


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL alert-store smoke test is opt-in.",
)
def test_real_postgres_alert_store_preserves_exact_timestamp_round_trip(
    monkeypatch,
) -> None:
    """Live round trips should preserve the shared timestamp string format exactly."""
    session_id = build_unique_session_id("real-postgres-timestamp")
    expected_timestamp = "2026-05-19 20:15:45"
    _mark_known_sessions(monkeypatch, session_id)
    connection = connect_postgres_alert_store()
    try:
        initialize_postgres_alert_store(connection)
        store = PostgresSessionAlertStore(connection)
        store.append_alert(
            _sample_alert_event(
                session_id=session_id,
                timestamp_utc=expected_timestamp,
                title="Timestamp format alert",
                message="Checks exact timestamp string formatting under a live DB connection.",
            )
        )
        alerts = store.read_session_alert_events(session_id)
    finally:
        close_store_if_possible(connection)

    assert alerts[0]["timestamp_utc"] == expected_timestamp


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL alert-store smoke test is opt-in.",
)
def test_real_postgres_alert_store_preserves_append_order_for_same_timestamp_alerts(
    monkeypatch,
) -> None:
    """Live reads should preserve append order, filters, and summary shapes."""
    session_id = build_unique_session_id("real-postgres-same-timestamp")
    other_session_id = build_unique_session_id("real-postgres-other-session")
    shared_timestamp = "2026-05-19 20:20:00"
    _mark_known_sessions(monkeypatch, session_id, other_session_id)
    connection = connect_postgres_alert_store()
    try:
        initialize_postgres_alert_store(connection)
        store = PostgresSessionAlertStore(connection)
        events = (
            _sample_alert_event(
                session_id=session_id,
                timestamp_utc=shared_timestamp,
                title="Repeated black alert",
                message="Inserted first.",
                source_name="segment-001.ts",
            ),
            _sample_alert_event(
                session_id=session_id,
                timestamp_utc=shared_timestamp,
                title="Repeated black alert",
                message="Inserted second.",
                source_name="segment-002.ts",
            ),
            _sample_alert_event(
                session_id=session_id,
                timestamp_utc="2026-05-19 20:21:00",
                detector_id="motion_blur",
                title="Motion blur alert",
                message="Inserted for a distinct filter result.",
                severity="info",
                source_name="segment-003.ts",
            ),
            _sample_alert_event(
                session_id=other_session_id,
                timestamp_utc=shared_timestamp,
                title="Other session alert",
                message="Must not appear in the target session read.",
                source_name="other-segment.ts",
            ),
        )
        for event in events:
            store.append_alert(event)

        target_alerts = store.read_session_alert_events(session_id)
        other_alerts = store.read_session_alert_events(other_session_id)
        black_warning_alerts = filter_session_alert_events(
            session_id,
            detector_id="black_screen",
            severity="warning",
            store=store,
        )
        black_warning_timeline = build_session_timeline(
            session_id,
            detector_id="black_screen",
            severity="warning",
            store=store,
        )
        black_warning_summary = summarize_session_alert_events(
            session_id,
            detector_id="black_screen",
            severity="warning",
            store=store,
        )
        black_warning_incident_summary = build_session_incident_summary(
            session_id,
            detector_id="black_screen",
            severity="warning",
            store=store,
        )
        unmatched_alerts = filter_session_alert_events(
            session_id,
            detector_id="not-present",
            store=store,
        )
        unmatched_timeline = build_session_timeline(
            session_id,
            detector_id="not-present",
            store=store,
        )
    finally:
        close_store_if_possible(connection)

    assert [alert["source_name"] for alert in target_alerts] == [
        "segment-001.ts",
        "segment-002.ts",
        "segment-003.ts",
    ]
    assert [alert["title"] for alert in other_alerts] == ["Other session alert"]
    assert [alert["source_name"] for alert in black_warning_alerts] == [
        "segment-001.ts",
        "segment-002.ts",
    ]
    assert black_warning_timeline["entries"] == [
        {
            "start_time_utc": shared_timestamp,
            "end_time_utc": shared_timestamp,
            "detector_id": "black_screen",
            "severity": "warning",
            "title": "Repeated black alert",
            "alert_count": 2,
            "source_names": ["segment-001.ts", "segment-002.ts"],
            "sample_message": "Inserted first.",
        }
    ]
    expected_summary = {
        "session_id": session_id,
        "total_alerts": 2,
        "counts_by_detector": {"black_screen": 2},
        "counts_by_severity": {"warning": 2},
        "first_alert_timestamp_utc": shared_timestamp,
        "last_alert_timestamp_utc": shared_timestamp,
    }
    assert black_warning_summary == expected_summary
    assert black_warning_incident_summary == {
        **expected_summary,
        "total_incidents": 1,
        "top_incident_categories": {"Repeated black alert": 1},
        "narrative_summary": (
            f"Session {session_id} had 1 grouped incidents across 2 alerts, mostly from "
            "black_screen, led by repeated black alert, with 2 warning alerts and 0 info "
            "alerts."
        ),
    }
    assert unmatched_alerts == []
    assert unmatched_timeline == {"session_id": session_id, "entries": []}


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL alert-store smoke test is opt-in.",
)
def test_real_postgres_bootstrap_succeeds_without_auto_create_when_schema_already_exists(
    monkeypatch,
) -> None:
    """A pre-existing schema should support auto-create-off bootstrap and round-trip reads."""
    session_id = build_unique_session_id("real-postgres-no-auto-create")
    _mark_known_sessions(monkeypatch, session_id)

    setup_connection = connect_postgres_alert_store()
    try:
        initialize_postgres_alert_store(setup_connection)
    finally:
        close_store_if_possible(setup_connection)

    connection = bootstrap_postgres_alert_store(
        PostgresAlertStoreSettings(
            database_url=os.environ[POSTGRES_ALERT_DATABASE_URL_ENV],
            auto_create_tables=False,
        )
    )
    try:
        store = PostgresSessionAlertStore(connection)
        store.append_alert(
            _sample_alert_event(
                session_id=session_id,
                timestamp_utc="2026-05-19 20:25:00",
                title="Schema already exists",
                message="Round-tripped with auto-create disabled.",
            )
        )
        alerts = store.read_session_alert_events(session_id)
    finally:
        close_store_if_possible(connection)

    assert alerts == [
        _sample_normalized_alert(
            session_id=session_id,
            timestamp_utc="2026-05-19 20:25:00",
            title="Schema already exists",
            message="Round-tripped with auto-create disabled.",
        )
    ]
