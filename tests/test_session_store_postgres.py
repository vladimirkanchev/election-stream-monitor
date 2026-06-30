"""Focused tests for PostgreSQL session-store bootstrap.

These checks stay below runtime selection. They cover schema/bootstrap
behavior, dependency loading, and one opt-in live isolation path.
"""

from __future__ import annotations

from typing import Any
from types import ModuleType

import pytest

from session_store_postgres import (
    POSTGRES_SESSION_METADATA_TABLE_NAME,
    POSTGRES_SESSION_METADATA_TABLE_SQL,
    POSTGRES_SESSION_PROGRESS_TABLE_NAME,
    POSTGRES_SESSION_PROGRESS_TABLE_SQL,
    POSTGRES_SESSION_RESULTS_TABLE_NAME,
    POSTGRES_SESSION_RESULTS_TABLE_SQL,
    POSTGRES_SESSION_STORE_SCHEMA_DROP_STATEMENTS,
    POSTGRES_SESSION_STORE_SCHEMA_STATEMENTS,
    PostgresSessionStoreBootstrapError,
    bootstrap_postgres_session_store,
    connect_postgres_session_store,
    drop_postgres_session_store_schema,
    initialize_postgres_session_store,
    load_postgres_session_store_driver,
    reset_postgres_session_store_schema,
)
from session_store_postgres_config import PostgresSessionStoreSettings
from tests import session_store_postgres_test_support
from tests.session_store_postgres_test_support import (
    REAL_POSTGRES_SESSION_STORE_SMOKE_ENABLED,
    bootstrap_isolated_postgres_session_store,
    close_postgres_session_store_connection_if_possible,
)

VALID_POSTGRES_SESSION_URL = "postgresql://session:secret@db.example/esm"


class RecordingCursor:
    """Cursor double that records executed schema statements."""

    def __init__(self, *, executed_statements: list[tuple[str, object | None]]) -> None:
        self._executed_statements = executed_statements

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        return None

    def execute(self, query: str, params: object | None = None) -> object:
        self._executed_statements.append((query, params))
        return object()


class RecordingConnection:
    """Connection double that records statements and commit activity."""

    def __init__(self) -> None:
        self.executed_statements: list[tuple[str, object | None]] = []
        self.committed = False
        self.commit_count = 0

    def cursor(self) -> RecordingCursor:
        return RecordingCursor(executed_statements=self.executed_statements)

    def commit(self) -> None:
        self.committed = True
        self.commit_count = getattr(self, "commit_count", 0) + 1


class FakePsycopgModule:
    """Small psycopg-shaped test double for connection-path tests."""

    class Error(Exception):
        """Driver-shaped base error used by bootstrap tests."""

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
        self.connect_calls.append(database_url)
        if self.connect_error is not None:
            raise self.connect_error
        return self.connection


class MidSchemaFailureCursor:
    """Cursor double that fails mid-bootstrap to prove commit behavior."""

    def __init__(self) -> None:
        self.calls = 0

    def __enter__(self) -> "MidSchemaFailureCursor":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        return None

    def execute(self, query: str, params: object | None = None) -> object:
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("index creation failed")
        return object()


class MidSchemaFailureConnection:
    """Connection double that surfaces a mid-bootstrap failure before commit."""

    def __init__(self) -> None:
        self.committed = False
        self.cursor_instance = MidSchemaFailureCursor()

    def cursor(self) -> MidSchemaFailureCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True


def _postgres_settings(
    *,
    database_url: str | None = VALID_POSTGRES_SESSION_URL,
    auto_create_tables: bool = False,
) -> PostgresSessionStoreSettings:
    """Build compact bootstrap settings for focused PostgreSQL tests."""
    return PostgresSessionStoreSettings(
        database_url=database_url,
        auto_create_tables=auto_create_tables,
        real_smoke_enabled=False,
    )


def test_postgres_session_schema_constants_match_current_store_contract() -> None:
    """The schema should model metadata, latest progress, and ordered results."""
    assert POSTGRES_SESSION_METADATA_TABLE_NAME == "session_metadata"
    assert POSTGRES_SESSION_PROGRESS_TABLE_NAME == "session_progress"
    assert POSTGRES_SESSION_RESULTS_TABLE_NAME == "session_result_events"
    assert "selected_detectors JSONB NOT NULL" in POSTGRES_SESSION_METADATA_TABLE_SQL
    assert "latest_result_detectors JSONB NOT NULL" in POSTGRES_SESSION_PROGRESS_TABLE_SQL
    assert "payload JSONB NOT NULL" in POSTGRES_SESSION_RESULTS_TABLE_SQL
    assert "alerts" not in POSTGRES_SESSION_METADATA_TABLE_SQL.lower()
    assert "worker.log" not in POSTGRES_SESSION_PROGRESS_TABLE_SQL.lower()
    assert "cancel_requested" not in POSTGRES_SESSION_RESULTS_TABLE_SQL.lower()


def test_initialize_postgres_session_store_executes_schema_statements_in_order() -> None:
    """Bootstrap should execute the frozen table/index statements in order."""
    connection = RecordingConnection()

    initialize_postgres_session_store(connection)

    assert connection.executed_statements == [
        (statement, None) for statement in POSTGRES_SESSION_STORE_SCHEMA_STATEMENTS
    ]
    assert connection.committed is True


def test_initialize_postgres_session_store_is_repeatable_for_idempotent_bootstrap_calls(
) -> None:
    """Repeated bootstrap calls should stay safe for idempotent table/index creation."""
    connection = RecordingConnection()

    initialize_postgres_session_store(connection)
    initialize_postgres_session_store(connection)

    expected_statements = [
        *POSTGRES_SESSION_STORE_SCHEMA_STATEMENTS,
        *POSTGRES_SESSION_STORE_SCHEMA_STATEMENTS,
    ]
    assert connection.executed_statements == [
        (statement, None) for statement in expected_statements
    ]
    assert connection.commit_count == 2


def test_initialize_postgres_session_store_does_not_commit_after_mid_schema_failure() -> None:
    """Bootstrap should not commit partial schema work after a later statement fails."""
    connection = MidSchemaFailureConnection()

    with pytest.raises(RuntimeError, match="index creation failed"):
        initialize_postgres_session_store(connection)

    assert connection.cursor_instance.calls == 2
    assert connection.committed is False


def test_drop_postgres_session_store_schema_executes_drop_statements_in_safe_order() -> None:
    """Cleanup should drop result rows before progress and metadata tables."""
    connection = RecordingConnection()

    drop_postgres_session_store_schema(connection)

    assert connection.executed_statements == [
        (statement, None) for statement in POSTGRES_SESSION_STORE_SCHEMA_DROP_STATEMENTS
    ]
    assert connection.committed is True


def test_reset_postgres_session_store_schema_recreates_clean_schema_after_drop() -> None:
    """Isolation reset should drop old tables, then recreate the durable schema."""
    connection = RecordingConnection()

    reset_postgres_session_store_schema(connection)

    expected_statements = [
        *POSTGRES_SESSION_STORE_SCHEMA_DROP_STATEMENTS,
        *POSTGRES_SESSION_STORE_SCHEMA_STATEMENTS,
    ]
    assert connection.executed_statements == [
        (statement, None) for statement in expected_statements
    ]
    assert connection.commit_count == 2


def test_bootstrap_isolated_postgres_session_store_resets_schema_before_returning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The isolation helper should connect once and reset the known session tables."""
    connection = RecordingConnection()
    seen: list[str] = []

    monkeypatch.setattr(
        session_store_postgres_test_support,
        "connect_postgres_session_store",
        lambda: seen.append("connect") or connection,
    )
    monkeypatch.setattr(
        session_store_postgres_test_support,
        "reset_postgres_session_store_schema",
        lambda resolved_connection: seen.append("reset")
        if resolved_connection is connection
        else None,
    )

    result = bootstrap_isolated_postgres_session_store()

    assert result is connection
    assert seen == ["connect", "reset"]


def test_close_postgres_session_store_connection_if_possible_ignores_objects_without_close(
) -> None:
    """The close helper should stay no-op for simple fake objects."""
    close_postgres_session_store_connection_if_possible(object())


def test_bootstrap_postgres_session_store_initializes_schema_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should connect and initialize when auto-create is enabled."""
    settings = _postgres_settings(auto_create_tables=True)
    connection = RecordingConnection()
    seen: list[str] = []

    def fake_connect(
        resolved_settings: PostgresSessionStoreSettings,
    ) -> RecordingConnection:
        assert resolved_settings == settings
        seen.append("connect")
        return connection

    def fake_initialize(resolved_connection: RecordingConnection) -> None:
        assert resolved_connection is connection
        seen.append("initialize")

    monkeypatch.setattr(
        "session_store_postgres.connect_postgres_session_store",
        fake_connect,
    )
    monkeypatch.setattr(
        "session_store_postgres.initialize_postgres_session_store",
        fake_initialize,
    )

    result = bootstrap_postgres_session_store(settings)

    assert result is connection
    assert seen == ["connect", "initialize"]


def test_bootstrap_postgres_session_store_skips_schema_init_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should skip schema creation when auto-create is disabled."""
    settings = _postgres_settings()
    connection = RecordingConnection()
    seen: list[str] = []

    def fake_connect(
        resolved_settings: PostgresSessionStoreSettings,
    ) -> RecordingConnection:
        assert resolved_settings == settings
        seen.append("connect")
        return connection

    def fake_initialize(resolved_connection: RecordingConnection) -> None:
        assert resolved_connection is connection
        seen.append("initialize")

    monkeypatch.setattr(
        "session_store_postgres.connect_postgres_session_store",
        fake_connect,
    )
    monkeypatch.setattr(
        "session_store_postgres.initialize_postgres_session_store",
        fake_initialize,
    )

    result = bootstrap_postgres_session_store(settings)

    assert result is connection
    assert seen == ["connect"]


def test_bootstrap_postgres_session_store_uses_cached_settings_when_not_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should fall back to the cached session-store settings."""
    settings = _postgres_settings()
    connection = RecordingConnection()
    seen: list[str] = []

    monkeypatch.setattr(
        "session_store_postgres.get_postgres_session_store_settings",
        lambda: settings,
    )

    def fake_connect(
        resolved_settings: PostgresSessionStoreSettings,
    ) -> RecordingConnection:
        assert resolved_settings == settings
        seen.append("connect")
        return connection

    monkeypatch.setattr(
        "session_store_postgres.connect_postgres_session_store",
        fake_connect,
    )

    result = bootstrap_postgres_session_store()

    assert result is connection
    assert seen == ["connect"]


def test_bootstrap_postgres_session_store_explicit_settings_override_stale_cached_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit bootstrap settings should win over already-cached env-derived settings."""
    stale_settings = PostgresSessionStoreSettings(
        database_url="postgresql://stale:stale@localhost:5432/election_stream_monitor",
        auto_create_tables=False,
        real_smoke_enabled=False,
    )
    explicit_settings = PostgresSessionStoreSettings(
        database_url="postgresql://fresh:secret@db.example/esm",
        auto_create_tables=False,
        real_smoke_enabled=False,
    )
    connection = RecordingConnection()
    seen_settings: list[PostgresSessionStoreSettings] = []

    monkeypatch.setattr(
        "session_store_postgres.get_postgres_session_store_settings",
        lambda: stale_settings,
    )

    def fake_connect(
        resolved_settings: PostgresSessionStoreSettings,
    ) -> RecordingConnection:
        seen_settings.append(resolved_settings)
        return connection

    monkeypatch.setattr(
        "session_store_postgres.connect_postgres_session_store",
        fake_connect,
    )

    result = bootstrap_postgres_session_store(explicit_settings)

    assert result is connection
    assert seen_settings == [explicit_settings]


def test_load_postgres_session_store_driver_reports_missing_psycopg_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should fail clearly when the psycopg dependency is unavailable."""
    monkeypatch.setattr(
        "session_store_postgres.importlib.import_module",
        lambda name: (_ for _ in ()).throw(ImportError("psycopg missing")),
    )

    with pytest.raises(
        PostgresSessionStoreBootstrapError,
        match="Install psycopg to use the PostgreSQL session-store backend",
    ):
        load_postgres_session_store_driver()


def test_load_postgres_session_store_driver_returns_imported_driver_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should pass through the loaded PostgreSQL driver module."""
    fake_driver = ModuleType("psycopg")
    monkeypatch.setattr(
        "session_store_postgres.importlib.import_module",
        lambda name: fake_driver,
    )

    loaded_driver = load_postgres_session_store_driver()

    assert loaded_driver is fake_driver


def test_connect_postgres_session_store_reports_missing_psycopg_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should fail clearly when the psycopg dependency is unavailable."""
    monkeypatch.setattr(
        "session_store_postgres.load_postgres_session_store_driver",
        lambda: (_ for _ in ()).throw(
            PostgresSessionStoreBootstrapError(
                "Install psycopg to use the PostgreSQL session-store backend"
            )
        ),
    )

    with pytest.raises(
        PostgresSessionStoreBootstrapError,
        match="Install psycopg to use the PostgreSQL session-store backend",
    ):
        connect_postgres_session_store(_postgres_settings())


def test_connect_postgres_session_store_rejects_missing_database_url_before_driver_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap validation should fail before the driver is loaded when no URL exists."""
    monkeypatch.setattr(
        "session_store_postgres.load_postgres_session_store_driver",
        lambda: (_ for _ in ()).throw(AssertionError("driver should not load")),
    )

    with pytest.raises(
        PostgresSessionStoreBootstrapError,
        match="PostgreSQL session store requires ESM_POSTGRES_SESSION_DATABASE_URL",
    ):
        connect_postgres_session_store(_postgres_settings(database_url=None))


def test_connect_postgres_session_store_rejects_invalid_database_url_before_driver_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap validation should reject invalid URL schemes before driver work starts."""
    monkeypatch.setattr(
        "session_store_postgres.load_postgres_session_store_driver",
        lambda: (_ for _ in ()).throw(AssertionError("driver should not load")),
    )

    with pytest.raises(
        PostgresSessionStoreBootstrapError,
        match="must use a postgres or postgresql URL",
    ):
        connect_postgres_session_store(
            _postgres_settings(database_url="sqlite:///tmp/sessions.db")
        )


def test_connect_postgres_session_store_uses_validated_database_url_with_driver_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should pass the validated URL through to psycopg.connect."""
    fake_psycopg = FakePsycopgModule()
    settings = _postgres_settings()
    monkeypatch.setattr(
        "session_store_postgres.load_postgres_session_store_driver",
        lambda: fake_psycopg,
    )

    connection = connect_postgres_session_store(settings)

    assert connection is fake_psycopg.connection
    assert fake_psycopg.connect_calls == [settings.database_url]


def test_connect_postgres_session_store_wraps_driver_connection_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Driver connection failures should become one stable bootstrap error."""
    fake_psycopg = FakePsycopgModule(
        connect_error=FakePsycopgModule.Error("database unavailable")
    )
    monkeypatch.setattr(
        "session_store_postgres.load_postgres_session_store_driver",
        lambda: fake_psycopg,
    )

    with pytest.raises(
        PostgresSessionStoreBootstrapError,
        match="Could not connect to the PostgreSQL session store",
    ):
        connect_postgres_session_store(_postgres_settings())

    assert fake_psycopg.connect_calls == [VALID_POSTGRES_SESSION_URL]


@pytest.mark.skipif(
    not REAL_POSTGRES_SESSION_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL session-store smoke test is opt-in.",
)
def test_real_postgres_session_store_isolation_helper_resets_schema_cleanly() -> None:
    """The isolation helper should provide a clean live schema without polluting default lanes."""
    connection = bootstrap_isolated_postgres_session_store()
    try:
        initialize_postgres_session_store(connection)
        initialize_postgres_session_store(connection)
    finally:
        close_postgres_session_store_connection_if_possible(connection)
