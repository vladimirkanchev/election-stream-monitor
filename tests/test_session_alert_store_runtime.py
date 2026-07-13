"""Focused tests for the runtime-selected default alert store.

These checks stay at the runtime seam: file-backed alerts remain the default,
explicit Postgres selection must fail clearly on bad bootstrap input, and
callers keep using the same default-store entry points either way. The small
live-smoke gate test remains deterministic and does not connect to PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Iterator
import os

import pytest
import tests.session_alert_test_support as session_alert_test_support
from tests.session_alert_test_support import (
    REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    REAL_POSTGRES_ALERT_STORE_SMOKE_ENV,
    build_normalized_alert,
    close_store_if_possible,
    configure_session_alert_test,
    is_real_postgres_alert_store_smoke_enabled,
    select_live_runtime_postgres_alert_store,
    write_known_session,
)

from session_alert_store import (
    DEFAULT_SESSION_ALERT_STORE,
    FileSessionAlertStore,
    SessionAlertsNotFoundError,
    clear_default_session_alert_store_cache,
    get_default_session_alert_store,
)
from session_alert_store_postgres import (
    POSTGRES_ALERT_EVENTS_INSERT_SQL,
    POSTGRES_ALERT_EVENTS_READ_SQL,
    POSTGRES_ALERT_TIMESTAMP_FORMAT,
    PostgresAlertStoreBootstrapError,
    PostgresSessionAlertStore,
)
from session_alert_store_postgres_config import (
    POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV,
    POSTGRES_ALERT_DATABASE_URL_ENV,
)
from session_alert_store_runtime_config import (
    ALERT_STORE_BACKEND_ENV,
    AlertStoreRuntimeConfigurationError,
)
from session_alerts import read_session_alert_events
from session_models import AlertEvent
from session_store_postgres_config import POSTGRES_SESSION_DATABASE_URL_ENV
from session_store_runtime import clear_default_session_store_cache
from session_store_runtime_config import SESSION_STORE_BACKEND_ENV

STALE_POSTGRES_ALERT_DATABASE_URL = (
    "postgresql://stale:stale@localhost:5432/election_stream_monitor"
)
STALE_POSTGRES_SESSION_DATABASE_URL = (
    "postgresql://stale:stale@localhost:5432/election_stream_monitor_sessions"
)


def test_live_postgres_alert_smoke_requires_all_explicit_opt_ins() -> None:
    """The live-smoke gate requires the flag, Postgres selection, and a URL."""
    enabled_values = {
        REAL_POSTGRES_ALERT_STORE_SMOKE_ENV: "1",
        ALERT_STORE_BACKEND_ENV: "postgres",
        POSTGRES_ALERT_DATABASE_URL_ENV: (
            "postgresql://postgres:postgres@localhost:5432/election_stream_monitor"
        ),
    }
    assert is_real_postgres_alert_store_smoke_enabled(enabled_values) is True
    assert is_real_postgres_alert_store_smoke_enabled(
        {**enabled_values, ALERT_STORE_BACKEND_ENV: "  POSTGRES  "}
    ) is True

    for missing_name in enabled_values:
        incomplete_values = {
            name: value for name, value in enabled_values.items() if name != missing_name
        }
        assert is_real_postgres_alert_store_smoke_enabled(incomplete_values) is False

    blank_url_values = {**enabled_values, POSTGRES_ALERT_DATABASE_URL_ENV: "  "}
    assert is_real_postgres_alert_store_smoke_enabled(blank_url_values) is False


def test_select_live_runtime_postgres_alert_store_aligns_selection_and_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live helper selection should set Postgres runtime state and clear its cache."""
    selected_store = object.__new__(PostgresSessionAlertStore)
    cache_clears: list[None] = []
    monkeypatch.setattr(
        session_alert_test_support,
        "clear_default_session_alert_store_cache",
        lambda: cache_clears.append(None),
    )
    monkeypatch.setattr(
        session_alert_test_support,
        "get_default_session_alert_store",
        lambda: selected_store,
    )

    store = select_live_runtime_postgres_alert_store(monkeypatch)

    assert store is selected_store
    assert cache_clears == [None]
    assert os.environ[ALERT_STORE_BACKEND_ENV] == "postgres"
    assert os.environ[POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV] == "1"


class RecordingRuntimeAlertStore:
    """Tiny fake store for runtime backend-selection routing assertions."""

    def __init__(self) -> None:
        self.read_session_ids: list[str] = []
        self.appended_events: list[AlertEvent] = []

    def append_alert(self, event: AlertEvent) -> None:
        """Record one alert append through the runtime-selected default store."""
        self.appended_events.append(event)

    def read_session_alert_events(self, session_id: str) -> list[dict[str, object]]:
        """Record one read through the runtime-selected default store."""
        self.read_session_ids.append(session_id)
        return []


class InMemoryRuntimePostgresAlertCursor:
    """Small cursor double for runtime tests that exercise the real store mapper."""

    def __init__(self, connection: "InMemoryRuntimePostgresAlertConnection") -> None:
        self._connection = connection
        self._rows: list[tuple[object, ...]] = []

    def __enter__(self) -> "InMemoryRuntimePostgresAlertCursor":
        """Return the cursor itself for store code that uses context managers."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        """Exit cleanly; the in-memory test double needs no cursor cleanup."""

    def execute(self, query: str, params: object | None = None) -> object:
        """Handle only the insert/read SQL used by the Postgres alert store."""
        if query == POSTGRES_ALERT_EVENTS_INSERT_SQL:
            assert isinstance(params, tuple)
            self._connection.append_inserted_row(params)
            return object()
        if query == POSTGRES_ALERT_EVENTS_READ_SQL:
            assert isinstance(params, tuple)
            session_id = params[0]
            assert isinstance(session_id, str)
            self._rows = self._connection.read_rows_for_session(session_id)
            return object()
        raise AssertionError(f"Unexpected SQL in runtime alert-store test: {query}")

    def fetchall(self) -> list[object]:
        """Return the preloaded rows for the current read query."""
        return list(self._rows)


class InMemoryRuntimePostgresAlertConnection:
    """Minimal connection double for Postgres alert-store runtime behavior."""

    def __init__(self) -> None:
        self._rows: list[tuple[object, ...]] = []

    def cursor(self) -> InMemoryRuntimePostgresAlertCursor:
        """Return a cursor over the shared in-memory alert rows."""
        return InMemoryRuntimePostgresAlertCursor(self)

    def commit(self) -> None:
        """Commit is a no-op for the in-memory runtime connection."""

    def append_inserted_row(self, params: tuple[object, ...]) -> None:
        """Store one inserted row in the shape expected by the read mapper."""
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
        ) = params
        self._rows.append(
            (
                session_id,
                timestamp_utc.strftime(POSTGRES_ALERT_TIMESTAMP_FORMAT),
                detector_id,
                title,
                message,
                severity,
                source_name,
                window_index,
                window_start_sec,
            )
        )

    def read_rows_for_session(self, session_id: str) -> list[tuple[object, ...]]:
        """Return rows for one session in persisted append order."""
        return [row for row in self._rows if row[0] == session_id]


class MissingSchemaRuntimeAlertConnection:
    """Connection/cursor double that exposes a post-bootstrap missing-table error.

    It models an operational failure after explicit PostgreSQL selection, not
    a bootstrap configuration failure that the runtime boundary translates.
    """

    def cursor(self) -> "MissingSchemaRuntimeAlertConnection":
        return self

    def __enter__(self) -> "MissingSchemaRuntimeAlertConnection":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        return None

    def execute(self, query: str, params: object | None = None) -> object:
        """Raise the stable missing-table failure used by this boundary test."""
        raise RuntimeError('relation "session_alert_events" does not exist')

    def commit(self) -> None:
        return None


def _install_unexpected_postgres_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail fast if file-mode resolution ever reaches the Postgres builder."""

    def fail_unexpected_build() -> object:
        raise AssertionError("postgres builder should not run")

    monkeypatch.setattr(
        "session_alert_store._build_postgres_default_session_alert_store",
        fail_unexpected_build,
    )


def _set_stale_postgres_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set harmless Postgres URLs that should not affect explicit file mode."""
    monkeypatch.setenv(POSTGRES_ALERT_DATABASE_URL_ENV, STALE_POSTGRES_ALERT_DATABASE_URL)
    monkeypatch.setenv(
        POSTGRES_SESSION_DATABASE_URL_ENV,
        STALE_POSTGRES_SESSION_DATABASE_URL,
    )


def _select_explicit_postgres_alert_backend(
    monkeypatch: pytest.MonkeyPatch,
    *,
    database_url: str | None,
) -> None:
    """Select explicit Postgres alert mode with an optional bootstrap URL override."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    if database_url is None:
        monkeypatch.delenv(POSTGRES_ALERT_DATABASE_URL_ENV, raising=False)
        return
    monkeypatch.setenv(POSTGRES_ALERT_DATABASE_URL_ENV, database_url)


def _select_postgres_runtime_backend(
    monkeypatch: pytest.MonkeyPatch,
    *,
    store: RecordingRuntimeAlertStore | None = None,
) -> RecordingRuntimeAlertStore:
    """Select Postgres mode and patch the default-store builder for one test."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    runtime_store = store or RecordingRuntimeAlertStore()
    monkeypatch.setattr(
        "session_alert_store._build_postgres_default_session_alert_store",
        lambda: runtime_store,
    )
    return runtime_store


def _select_in_memory_postgres_alert_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> PostgresSessionAlertStore:
    """Select the real Postgres alert store over an in-memory connection."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    store = PostgresSessionAlertStore(InMemoryRuntimePostgresAlertConnection())
    monkeypatch.setattr(
        "session_alert_store._build_postgres_default_session_alert_store",
        lambda: store,
    )
    return store


def _alert_event(
    *,
    session_id: str,
    timestamp_utc: str,
    title: str,
    message: str,
) -> AlertEvent:
    """Build one stable runtime alert event for store-selection tests."""
    return AlertEvent(
        session_id=session_id,
        timestamp_utc=timestamp_utc,
        detector_id="video_metrics",
        title=title,
        message=message,
        severity="warning",
        source_name="segment_0001.ts",
    )


@pytest.fixture(autouse=True)
def _clear_default_alert_store_cache() -> Iterator[None]:
    """Keep cached default-store selection isolated between runtime tests."""
    clear_default_session_alert_store_cache()
    clear_default_session_store_cache()
    yield
    clear_default_session_alert_store_cache()
    clear_default_session_store_cache()


def test_get_default_session_alert_store_defaults_to_file_backend(
    monkeypatch,
) -> None:
    """The default alert store should stay file-backed unless explicitly changed."""
    monkeypatch.delenv(ALERT_STORE_BACKEND_ENV, raising=False)

    store = get_default_session_alert_store()

    assert isinstance(store, FileSessionAlertStore)


@pytest.mark.parametrize(
    "backend",
    [
        pytest.param(None, id="unset"),
        pytest.param("file", id="explicit-file"),
    ],
)
def test_file_alert_backend_ignores_stale_postgres_bootstrap_settings(
    monkeypatch: pytest.MonkeyPatch,
    backend: str | None,
) -> None:
    """File mode must ignore stale PostgreSQL URL and bootstrap settings."""
    if backend is None:
        monkeypatch.delenv(ALERT_STORE_BACKEND_ENV, raising=False)
    else:
        monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, backend)
    monkeypatch.setenv(POSTGRES_ALERT_DATABASE_URL_ENV, "sqlite:///stale-alerts.db")
    monkeypatch.setenv(POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV, "0")
    _install_unexpected_postgres_builder(monkeypatch)

    store = get_default_session_alert_store()

    assert isinstance(store, FileSessionAlertStore)


def test_get_default_session_alert_store_builds_postgres_backend_when_selected(
    monkeypatch,
) -> None:
    """The runtime selector should build the Postgres store only when requested."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    built_stores: list[RecordingRuntimeAlertStore] = []

    def fake_build_postgres_default_session_alert_store() -> RecordingRuntimeAlertStore:
        store = RecordingRuntimeAlertStore()
        built_stores.append(store)
        return store

    monkeypatch.setattr(
        "session_alert_store._build_postgres_default_session_alert_store",
        fake_build_postgres_default_session_alert_store,
    )

    first = get_default_session_alert_store()
    second = get_default_session_alert_store()

    assert first is second
    assert built_stores == [first]


def test_get_default_session_alert_store_normalizes_runtime_backend_env_whitespace_and_case(
    monkeypatch,
) -> None:
    """Whitespace and mixed-case backend env values should still select Postgres mode."""
    built_stores: list[RecordingRuntimeAlertStore] = []
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "  PoStGrEs  ")

    def fake_build_postgres_default_session_alert_store() -> RecordingRuntimeAlertStore:
        store = RecordingRuntimeAlertStore()
        built_stores.append(store)
        return store

    monkeypatch.setattr(
        "session_alert_store._build_postgres_default_session_alert_store",
        fake_build_postgres_default_session_alert_store,
    )

    store = get_default_session_alert_store()

    assert store is built_stores[0]


@pytest.mark.parametrize(
    "bootstrap_message",
    [
        pytest.param(
            "schema bootstrap failed",
            id="schema-bootstrap",
        ),
        pytest.param(
            "Install psycopg to use the PostgreSQL alert-store bootstrap path",
            id="missing-driver",
        ),
        pytest.param(
            "Could not connect to the PostgreSQL alert store",
            id="connection-failure",
        ),
    ],
)
def test_explicit_postgres_alert_backend_surfaces_bootstrap_failures_at_runtime_boundary(
    monkeypatch: pytest.MonkeyPatch,
    bootstrap_message: str,
) -> None:
    """Explicit Postgres mode should preserve actionable bootstrap failures."""

    def fail_bootstrap() -> object:
        raise PostgresAlertStoreBootstrapError(bootstrap_message)

    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setattr(
        "session_alert_store_postgres.bootstrap_postgres_alert_store",
        fail_bootstrap,
    )

    with pytest.raises(
        AlertStoreRuntimeConfigurationError,
        match=bootstrap_message,
    ):
        get_default_session_alert_store()


def test_get_default_session_alert_store_only_fails_for_missing_postgres_driver_when_postgres_is_selected(
    monkeypatch,
) -> None:
    """Missing Postgres driver should matter only after explicit Postgres selection."""
    monkeypatch.setenv(
        POSTGRES_ALERT_DATABASE_URL_ENV,
        STALE_POSTGRES_ALERT_DATABASE_URL,
    )
    monkeypatch.delenv(ALERT_STORE_BACKEND_ENV, raising=False)
    _install_unexpected_postgres_builder(monkeypatch)

    default_store = get_default_session_alert_store()
    assert isinstance(default_store, FileSessionAlertStore)

    clear_default_session_alert_store_cache()
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")

    with pytest.raises(AssertionError, match="postgres builder should not run"):
        get_default_session_alert_store()


@pytest.mark.parametrize(
    ("database_url", "expected_message"),
    [
        pytest.param(
            None,
            "PostgreSQL alert store requires ESM_POSTGRES_ALERT_DATABASE_URL",
            id="missing-url",
        ),
        pytest.param(
            "sqlite:///tmp/alerts.db",
            "ESM_POSTGRES_ALERT_DATABASE_URL must use a postgres or postgresql URL",
            id="invalid-url",
        ),
    ],
)
def test_explicit_postgres_alert_backend_rejects_missing_or_invalid_url_without_fallback(
    monkeypatch,
    database_url: str | None,
    expected_message: str,
) -> None:
    """Explicit Postgres mode should surface URL validation failures clearly."""
    _select_explicit_postgres_alert_backend(
        monkeypatch,
        database_url=database_url,
    )

    with pytest.raises(
        AlertStoreRuntimeConfigurationError,
        match=expected_message,
    ):
        get_default_session_alert_store()


def test_explicit_postgres_alert_backend_keeps_missing_schema_failure_visible_after_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A selected Postgres store should not turn later table failures into file reads."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setattr(
        "session_alert_store_postgres.bootstrap_postgres_alert_store",
        MissingSchemaRuntimeAlertConnection,
    )

    store = get_default_session_alert_store()

    assert isinstance(store, PostgresSessionAlertStore)
    with pytest.raises(
        RuntimeError,
        match='relation "session_alert_events" does not exist',
    ):
        store.append_alert(
            _alert_event(
                session_id="runtime-postgres-missing-schema",
                timestamp_utc="2026-06-01 12:00:00",
                title="Missing schema",
                message="The alert table was not bootstrapped.",
            )
        )


def test_default_alert_service_entrypoint_uses_runtime_selected_backend(
    monkeypatch,
) -> None:
    """The raw alert service should honor runtime backend selection without caller churn."""
    store = _select_postgres_runtime_backend(monkeypatch)

    assert read_session_alert_events("runtime-selected-session") == []
    assert store.read_session_ids == ["runtime-selected-session"]


def test_default_alert_service_keeps_file_backed_known_empty_behavior(
    monkeypatch,
    tmp_path,
) -> None:
    """Default file mode should still read a known session with no alerts as empty history."""
    monkeypatch.delenv(ALERT_STORE_BACKEND_ENV, raising=False)
    monkeypatch.delenv(POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV, raising=False)
    _set_stale_postgres_urls(monkeypatch)
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "runtime-file-known-empty")

    assert read_session_alert_events("runtime-file-known-empty") == []


def test_default_alert_service_keeps_file_backed_unknown_session_behavior(
    monkeypatch,
    tmp_path,
) -> None:
    """Default file mode should still reject unknown sessions before any alert read."""
    monkeypatch.delenv(ALERT_STORE_BACKEND_ENV, raising=False)
    _set_stale_postgres_urls(monkeypatch)
    configure_session_alert_test(monkeypatch, tmp_path)

    with pytest.raises(SessionAlertsNotFoundError):
        read_session_alert_events("runtime-file-missing")


def test_default_alert_store_proxy_uses_runtime_selected_backend_for_writes(
    monkeypatch,
) -> None:
    """The default seam proxy should keep the compatibility write path stable."""
    store = _select_postgres_runtime_backend(monkeypatch)

    event = _alert_event(
        session_id="runtime-store-write",
        timestamp_utc="2026-05-19 18:00:00",
        title="Black screen detected",
        message="Delegated through the runtime-selected store backend.",
    )

    DEFAULT_SESSION_ALERT_STORE.append_alert(event)

    assert store.appended_events == [event]


def test_default_alert_store_proxy_keeps_file_backed_append_read_round_trip(
    monkeypatch,
    tmp_path,
) -> None:
    """Default file mode should still append to and read from the file-backed alert log."""
    monkeypatch.delenv(ALERT_STORE_BACKEND_ENV, raising=False)
    _set_stale_postgres_urls(monkeypatch)
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "runtime-file-round-trip")

    DEFAULT_SESSION_ALERT_STORE.append_alert(
        _alert_event(
            session_id="runtime-file-round-trip",
            timestamp_utc="2026-05-19 18:30:00",
            title="File mode alert",
            message="Persisted through the default file-backed alert store.",
        )
    )

    assert read_session_alert_events("runtime-file-round-trip") == [
        build_normalized_alert(
            "runtime-file-round-trip",
            timestamp_utc="2026-05-19 18:30:00",
            detector_id="video_metrics",
            title="File mode alert",
            message="Persisted through the default file-backed alert store.",
            severity="warning",
            source_name="segment_0001.ts",
        )
    ]


def test_postgres_alert_backend_can_validate_against_explicit_file_session_store(
    monkeypatch,
    tmp_path,
) -> None:
    """Mixed mode should work when Postgres alerts use known file-backed sessions."""
    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, "file")
    _set_stale_postgres_urls(monkeypatch)
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "runtime-mixed-known-session")
    _select_in_memory_postgres_alert_backend(monkeypatch)

    DEFAULT_SESSION_ALERT_STORE.append_alert(
        _alert_event(
            session_id="runtime-mixed-known-session",
            timestamp_utc="2026-05-19 19:00:00",
            title="Mixed backend alert",
            message="Postgres alert rows can use file-backed session existence.",
        )
    )

    assert read_session_alert_events("runtime-mixed-known-session") == [
        build_normalized_alert(
            "runtime-mixed-known-session",
            timestamp_utc="2026-05-19 19:00:00",
            detector_id="video_metrics",
            title="Mixed backend alert",
            message="Postgres alert rows can use file-backed session existence.",
            severity="warning",
            source_name="segment_0001.ts",
        )
    ]


def test_postgres_alert_backend_does_not_treat_alert_rows_as_file_sessions(
    monkeypatch,
    tmp_path,
) -> None:
    """Mixed mode should still reject Postgres alert rows for unknown file sessions."""
    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, "file")
    configure_session_alert_test(monkeypatch, tmp_path)
    postgres_store = _select_in_memory_postgres_alert_backend(monkeypatch)
    postgres_store.append_alert(
        _alert_event(
            session_id="runtime-mixed-missing-session",
            timestamp_utc="2026-05-19 19:30:00",
            title="Orphaned mixed backend alert",
            message="An alert row alone must not make the session known.",
        )
    )

    with pytest.raises(SessionAlertsNotFoundError, match="runtime-mixed-missing-session"):
        read_session_alert_events("runtime-mixed-missing-session")


def test_default_alert_store_cache_requires_explicit_clear_before_backend_switch(
    monkeypatch,
) -> None:
    """Runtime backend changes should not silently replace the cached default store."""
    monkeypatch.delenv(ALERT_STORE_BACKEND_ENV, raising=False)
    first = get_default_session_alert_store()

    switched_store = RecordingRuntimeAlertStore()
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setattr(
        "session_alert_store._build_postgres_default_session_alert_store",
        lambda: switched_store,
    )

    still_cached = get_default_session_alert_store()
    clear_default_session_alert_store_cache()
    rebuilt = get_default_session_alert_store()

    assert still_cached is first
    assert rebuilt is switched_store


def test_default_alert_store_cache_recovers_cleanly_after_failed_postgres_bootstrap(
    monkeypatch,
) -> None:
    """A failed Postgres bootstrap should not poison the cache for a later clean rebuild."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setattr(
        "session_alert_store._build_postgres_default_session_alert_store",
        lambda: (_ for _ in ()).throw(RuntimeError("postgres bootstrap failed")),
    )

    with pytest.raises(RuntimeError, match="postgres bootstrap failed"):
        get_default_session_alert_store()

    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "file")
    clear_default_session_alert_store_cache()

    rebuilt = get_default_session_alert_store()

    assert isinstance(rebuilt, FileSessionAlertStore)


def test_default_alert_store_cache_supports_file_to_postgres_to_file_switch_with_explicit_clears(
    monkeypatch,
) -> None:
    """One process should rebuild the default store cleanly across explicit backend switches."""
    monkeypatch.delenv(ALERT_STORE_BACKEND_ENV, raising=False)
    file_store = get_default_session_alert_store()
    assert isinstance(file_store, FileSessionAlertStore)

    switched_store = RecordingRuntimeAlertStore()
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setattr(
        "session_alert_store._build_postgres_default_session_alert_store",
        lambda: switched_store,
    )
    clear_default_session_alert_store_cache()
    postgres_store = get_default_session_alert_store()

    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "file")
    clear_default_session_alert_store_cache()
    rebuilt_file_store = get_default_session_alert_store()

    assert postgres_store is switched_store
    assert isinstance(rebuilt_file_store, FileSessionAlertStore)
    assert rebuilt_file_store is file_store


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL runtime-store smoke test is opt-in.",
)
def test_real_postgres_default_alert_store_cache_reuses_then_rebuilds_store(
    monkeypatch,
) -> None:
    """The runtime cache should reuse one live Postgres store until it is explicitly cleared."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setenv(POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV, "1")

    first = get_default_session_alert_store()
    second = get_default_session_alert_store()
    assert isinstance(first, PostgresSessionAlertStore)
    assert first is second

    clear_default_session_alert_store_cache()
    rebuilt = get_default_session_alert_store()
    assert isinstance(rebuilt, PostgresSessionAlertStore)
    assert rebuilt is not first

    for store in (first, rebuilt):
        close_store_if_possible(store)


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL runtime-store smoke test is opt-in.",
)
def test_real_postgres_default_alert_store_rebuild_reads_existing_rows_after_cache_clear(
    monkeypatch,
    tmp_path,
) -> None:
    """Clearing the runtime cache should rebuild the live Postgres store without losing reads."""

    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setenv(POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV, "1")

    session_id = "runtime-store-cache-rebuild-live"
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, session_id)

    first = get_default_session_alert_store()
    assert isinstance(first, PostgresSessionAlertStore)
    DEFAULT_SESSION_ALERT_STORE.append_alert(
        AlertEvent(
            session_id=session_id,
            timestamp_utc="2026-05-19 22:00:00",
            detector_id="video_metrics",
            title="Cache rebuild alert",
            message="Persisted before clearing the runtime cache.",
            severity="warning",
            source_name="segment_0001.ts",
        )
    )

    clear_default_session_alert_store_cache()
    rebuilt = get_default_session_alert_store()
    assert isinstance(rebuilt, PostgresSessionAlertStore)
    assert rebuilt is not first

    alerts = rebuilt.read_session_alert_events(session_id)

    assert [alert["title"] for alert in alerts] == ["Cache rebuild alert"]

    for store in (first, rebuilt):
        close_store_if_possible(store)
