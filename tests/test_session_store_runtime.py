"""Focused tests for runtime session-store selection and live-smoke gating.

These checks keep the default file-backed runtime honest while proving that
explicit PostgreSQL mode, live-smoke gating, and runtime fixture setup behave
predictably.
"""

import os
from pathlib import Path

import config
import pytest
from session_models import ResultEvent, SessionMetadata, SessionProgress
from session_store_file import DEFAULT_FILE_SESSION_STORE, FileSessionStore
from session_store_postgres import PostgresSessionStore
from session_store_postgres import PostgresSessionStoreBootstrapError
from session_store_postgres_config import (
    POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV,
    POSTGRES_SESSION_DATABASE_URL_ENV,
    POSTGRES_SESSION_STORE_REAL_SMOKE_ENV,
)
from session_store_runtime import (
    DEFAULT_SESSION_STORE,
    clear_default_session_store_cache,
    get_default_session_store,
)
from session_store_runtime_config import (
    DEFAULT_SESSION_STORE_BACKEND,
    SESSION_STORE_BACKEND_ENV,
    SessionStoreRuntimeSettings,
    get_session_store_runtime_settings,
    validate_session_store_runtime_settings,
)
from tests.api_boundary_sessions_runtime_test_support import (
    live_postgres_runtime_fixture,
)
from tests import session_store_postgres_test_support

VALID_POSTGRES_SESSION_URL = "postgresql://session:secret@db.example/esm"


def _metadata(session_id: str) -> SessionMetadata:
    """Build minimal session metadata for runtime store tests."""
    return SessionMetadata(
        session_id=session_id,
        mode="video_files",
        input_path="/tmp/clip.mp4",
        selected_detectors=["video_metrics"],
        status="running",
    )


def _write_minimal_session_round_trip(store: FileSessionStore, session_id: str) -> None:
    """Exercise one minimal file-backed write path through the runtime store."""
    metadata = _metadata(session_id)
    store.write_metadata(metadata)
    store.write_progress(SessionProgress.initial(session_id=session_id, total_count=1))
    store.append_result(
        ResultEvent(
            session_id=session_id,
            detector_id="video_metrics",
            payload={"window_index": 0},
        )
    )


def _assert_file_mode_round_trip(store: FileSessionStore, session_id: str) -> None:
    """Assert that file-mode writes stay usable through runtime selection."""
    _write_minimal_session_round_trip(store, session_id)
    assert store.read_snapshot(session_id)["session"] == _metadata(session_id).to_dict()


def _assert_file_runtime_settings(settings: SessionStoreRuntimeSettings) -> None:
    """Assert that runtime settings keep the file-backed default."""
    assert settings.backend == DEFAULT_SESSION_STORE_BACKEND


def _set_valid_postgres_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Select PostgreSQL mode with the minimum valid env."""
    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setenv(POSTGRES_SESSION_DATABASE_URL_ENV, VALID_POSTGRES_SESSION_URL)


def _install_unexpected_postgres_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail fast if a file-mode test accidentally invokes Postgres bootstrap."""
    monkeypatch.setattr(
        "session_store_runtime.bootstrap_postgres_session_store",
        lambda: (_ for _ in ()).throw(AssertionError("postgres bootstrap should not run")),
    )


@pytest.fixture(autouse=True)
def _clear_runtime_store_caches() -> None:
    """Keep runtime store selection deterministic across env-driven tests."""
    clear_default_session_store_cache()
    yield
    clear_default_session_store_cache()


def test_default_session_store_is_file_backed_for_current_stage() -> None:
    """Default selection should preserve the current file-backed runtime."""
    default_store = get_default_session_store()

    assert DEFAULT_SESSION_STORE is DEFAULT_FILE_SESSION_STORE
    assert default_store is DEFAULT_FILE_SESSION_STORE
    assert isinstance(default_store, FileSessionStore)


def test_session_store_runtime_settings_default_to_file_backend() -> None:
    """Runtime settings should keep file-backed persistence as the branch default."""
    settings = get_session_store_runtime_settings()

    _assert_file_runtime_settings(settings)


def test_default_session_store_stays_file_backed_for_invalid_runtime_backend_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid runtime config should still resolve to the file-backed rollback path."""
    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, "not-a-real-backend")

    settings = get_session_store_runtime_settings()
    default_store = get_default_session_store()

    _assert_file_runtime_settings(settings)
    assert default_store is DEFAULT_FILE_SESSION_STORE


def test_default_session_store_accepts_explicit_file_runtime_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit file mode should resolve to the same stable default store."""
    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, DEFAULT_SESSION_STORE_BACKEND)

    settings = get_session_store_runtime_settings()
    default_store = get_default_session_store()

    _assert_file_runtime_settings(settings)
    assert default_store is DEFAULT_FILE_SESSION_STORE


def test_default_session_store_ignores_stale_postgres_settings_when_backend_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PostgreSQL bootstrap env alone should not switch the default backend."""
    monkeypatch.delenv(SESSION_STORE_BACKEND_ENV, raising=False)
    monkeypatch.setenv(
        POSTGRES_SESSION_DATABASE_URL_ENV,
        "postgresql://stale:stale@localhost:5432/election_stream_monitor",
    )
    monkeypatch.setenv(POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV, "0")

    settings = get_session_store_runtime_settings()
    default_store = get_default_session_store()

    _assert_file_runtime_settings(settings)
    assert default_store is DEFAULT_FILE_SESSION_STORE


def test_default_session_store_ignores_stale_postgres_settings_when_file_backend_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit file mode should keep ignoring unrelated PostgreSQL bootstrap env."""
    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, DEFAULT_SESSION_STORE_BACKEND)
    monkeypatch.setenv(
        POSTGRES_SESSION_DATABASE_URL_ENV,
        "postgresql://stale:stale@localhost:5432/election_stream_monitor",
    )
    monkeypatch.setenv(POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV, "1")

    settings = get_session_store_runtime_settings()
    default_store = get_default_session_store()

    _assert_file_runtime_settings(settings)
    assert default_store is DEFAULT_FILE_SESSION_STORE


def test_default_session_store_keeps_file_mode_usable_with_invalid_postgres_url_when_backend_is_unset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A broken Postgres URL should not poison the default file-backed rollback path."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)
    monkeypatch.delenv(SESSION_STORE_BACKEND_ENV, raising=False)
    monkeypatch.setenv(POSTGRES_SESSION_DATABASE_URL_ENV, "sqlite:///tmp/sessions.db")
    _install_unexpected_postgres_bootstrap(monkeypatch)

    store = get_default_session_store()

    assert isinstance(store, FileSessionStore)
    _assert_file_mode_round_trip(store, "file-mode-invalid-postgres-url")


def test_default_session_store_keeps_file_mode_usable_without_postgres_url_when_file_backend_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Explicit file mode should keep working even when Postgres bootstrap env is absent."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)
    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, DEFAULT_SESSION_STORE_BACKEND)
    monkeypatch.delenv(POSTGRES_SESSION_DATABASE_URL_ENV, raising=False)
    _install_unexpected_postgres_bootstrap(monkeypatch)

    store = get_default_session_store()

    assert isinstance(store, FileSessionStore)
    _assert_file_mode_round_trip(store, "explicit-file-without-postgres-url")


def test_session_store_runtime_settings_accept_explicit_postgres_backend_when_env_is_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime settings should carry Postgres selection and parsed bootstrap config together."""
    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, "  PoStGrEs  ")
    monkeypatch.setenv(POSTGRES_SESSION_DATABASE_URL_ENV, VALID_POSTGRES_SESSION_URL)
    monkeypatch.setenv(POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV, "false")

    settings = get_session_store_runtime_settings()

    assert settings.backend == "postgres"
    assert settings.postgres.database_url == VALID_POSTGRES_SESSION_URL
    assert settings.postgres.auto_create_tables is False


def test_validate_session_store_runtime_settings_allows_file_backend_without_postgres_url(
) -> None:
    """File mode should not require PostgreSQL bootstrap settings."""
    settings = get_session_store_runtime_settings()

    validate_session_store_runtime_settings(settings)


def test_validate_session_store_runtime_settings_requires_postgres_url_only_in_postgres_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing PostgreSQL URL should fail only after explicit Postgres selection."""
    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, "postgres")
    monkeypatch.delenv(POSTGRES_SESSION_DATABASE_URL_ENV, raising=False)

    settings = get_session_store_runtime_settings()

    with pytest.raises(
        RuntimeError,
        match="PostgreSQL session store requires ESM_POSTGRES_SESSION_DATABASE_URL",
    ):
        validate_session_store_runtime_settings(settings)


def test_validate_session_store_runtime_settings_rejects_bad_postgres_url_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Helpful validation should reject a Postgres backend with the wrong URL scheme."""
    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setenv(POSTGRES_SESSION_DATABASE_URL_ENV, "sqlite:///tmp/sessions.db")

    settings = get_session_store_runtime_settings()

    with pytest.raises(
        RuntimeError,
        match=(
            "ESM_POSTGRES_SESSION_DATABASE_URL must use a postgres or "
            "postgresql URL"
        ),
    ):
        validate_session_store_runtime_settings(settings)


@pytest.mark.parametrize(
    ("real_smoke_value", "database_url", "backend_value", "expected_enabled"),
    [
        (None, None, None, False),
        ("0", VALID_POSTGRES_SESSION_URL, "postgres", False),
        ("1", None, "postgres", False),
        ("1", "", "postgres", False),
        ("1", VALID_POSTGRES_SESSION_URL, None, False),
        ("1", VALID_POSTGRES_SESSION_URL, "file", False),
        ("1", VALID_POSTGRES_SESSION_URL, " PoStGrEs ", True),
    ],
)
def test_real_postgres_session_runtime_smoke_gate_requires_db_env_and_postgres_backend(
    monkeypatch: pytest.MonkeyPatch,
    real_smoke_value: str | None,
    database_url: str | None,
    backend_value: str | None,
    expected_enabled: bool,
) -> None:
    """Live runtime smoke should stay off until DB env and Postgres mode agree."""
    if real_smoke_value is None:
        monkeypatch.delenv(POSTGRES_SESSION_STORE_REAL_SMOKE_ENV, raising=False)
    else:
        monkeypatch.setenv(POSTGRES_SESSION_STORE_REAL_SMOKE_ENV, real_smoke_value)

    if database_url is None:
        monkeypatch.delenv(POSTGRES_SESSION_DATABASE_URL_ENV, raising=False)
    else:
        monkeypatch.setenv(POSTGRES_SESSION_DATABASE_URL_ENV, database_url)

    if backend_value is None:
        monkeypatch.delenv(SESSION_STORE_BACKEND_ENV, raising=False)
    else:
        monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, backend_value)

    assert (
        session_store_postgres_test_support.is_real_postgres_session_runtime_smoke_enabled()
        is expected_enabled
    )


def test_live_postgres_runtime_fixture_scopes_env_reset_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The live runtime fixture should isolate env, schema reset, and cleanup."""
    original_session_root = config.SESSION_OUTPUT_FOLDER
    closed_connections: list[str] = []

    class FakeConnection:
        def close(self) -> None:
            closed_connections.append("closed")

    monkeypatch.setenv(POSTGRES_SESSION_STORE_REAL_SMOKE_ENV, "1")
    monkeypatch.setenv(POSTGRES_SESSION_DATABASE_URL_ENV, VALID_POSTGRES_SESSION_URL)
    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, "file")
    monkeypatch.setenv(POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV, "0")
    original_backend = os.getenv(SESSION_STORE_BACKEND_ENV)
    original_auto_create = os.getenv(POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV)
    monkeypatch.setattr(
        "tests.api_boundary_sessions_runtime_test_support.bootstrap_isolated_postgres_session_store",
        lambda: FakeConnection(),
    )

    with live_postgres_runtime_fixture(monkeypatch, tmp_path) as runtime_fixture:
        assert os.getenv(SESSION_STORE_BACKEND_ENV) == "postgres"
        assert os.getenv(POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV) == "1"
        assert config.SESSION_OUTPUT_FOLDER == runtime_fixture.session_root
        assert runtime_fixture.request is not None
        runtime_fixture.session_root.mkdir(parents=True, exist_ok=True)
        (runtime_fixture.session_root / "probe.txt").write_text("runtime", encoding="utf-8")

    assert os.getenv(SESSION_STORE_BACKEND_ENV) == original_backend
    assert os.getenv(POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV) == original_auto_create
    assert config.SESSION_OUTPUT_FOLDER == original_session_root
    assert not (tmp_path / "runtime-session-output").exists()
    assert closed_connections == ["closed"]


def test_live_postgres_runtime_fixture_requires_real_smoke_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The live runtime fixture should fail clearly when opt-in gating is absent."""
    monkeypatch.delenv(POSTGRES_SESSION_STORE_REAL_SMOKE_ENV, raising=False)
    monkeypatch.setenv(POSTGRES_SESSION_DATABASE_URL_ENV, VALID_POSTGRES_SESSION_URL)

    with pytest.raises(
        AssertionError,
        match="POSTGRES_SESSION_STORE_REAL_SMOKE=1",
    ):
        with live_postgres_runtime_fixture(monkeypatch, tmp_path):
            pass


def test_default_session_store_only_fails_for_missing_postgres_driver_when_postgres_is_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing psycopg should matter only after explicit PostgreSQL selection."""
    monkeypatch.setenv(
        POSTGRES_SESSION_DATABASE_URL_ENV,
        "postgresql://stale:stale@localhost:5432/election_stream_monitor",
    )
    monkeypatch.delenv(SESSION_STORE_BACKEND_ENV, raising=False)
    _install_unexpected_postgres_bootstrap(monkeypatch)

    default_store = get_default_session_store()
    assert default_store is DEFAULT_FILE_SESSION_STORE

    clear_default_session_store_cache()
    _set_valid_postgres_runtime_env(monkeypatch)
    monkeypatch.setattr(
        "session_store_runtime.bootstrap_postgres_session_store",
        lambda: (_ for _ in ()).throw(
            PostgresSessionStoreBootstrapError(
                "Install psycopg to use the PostgreSQL session-store backend"
            )
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="Install psycopg to use the PostgreSQL session-store backend",
    ):
        get_default_session_store()


def test_default_session_store_builds_postgres_backend_when_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit PostgreSQL mode should build one concrete store and cache it."""
    _set_valid_postgres_runtime_env(monkeypatch)
    built_connections: list[object] = []

    def fake_bootstrap_postgres_session_store() -> object:
        connection = object()
        built_connections.append(connection)
        return connection

    monkeypatch.setattr(
        "session_store_runtime.bootstrap_postgres_session_store",
        fake_bootstrap_postgres_session_store,
    )

    first = get_default_session_store()
    second = get_default_session_store()

    assert isinstance(first, PostgresSessionStore)
    assert first is second
    assert first.connection is built_connections[0]
    assert built_connections == [built_connections[0]]


def test_default_session_store_builds_postgres_backend_when_runtime_env_has_whitespace_and_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whitespace and mixed-case backend env should still select PostgreSQL mode."""
    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, "  PoStGrEs  ")
    monkeypatch.setenv(POSTGRES_SESSION_DATABASE_URL_ENV, VALID_POSTGRES_SESSION_URL)
    built_connection = object()

    monkeypatch.setattr(
        "session_store_runtime.bootstrap_postgres_session_store",
        lambda: built_connection,
    )

    store = get_default_session_store()

    assert isinstance(store, PostgresSessionStore)
    assert store.connection is built_connection


def test_default_session_store_passes_explicit_postgres_bootstrap_through_to_store_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit PostgreSQL mode should use the bootstrap seam rather than file fallback."""
    _set_valid_postgres_runtime_env(monkeypatch)
    monkeypatch.setenv(POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV, "1")
    seen: list[str] = []

    monkeypatch.setattr(
        "session_store_runtime.bootstrap_postgres_session_store",
        lambda: seen.append("bootstrap") or object(),
    )

    store = get_default_session_store()

    assert isinstance(store, PostgresSessionStore)
    assert seen == ["bootstrap"]


def test_default_session_store_raises_when_postgres_bootstrap_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit PostgreSQL mode should fail clearly instead of silently falling back."""
    _set_valid_postgres_runtime_env(monkeypatch)
    monkeypatch.setattr(
        "session_store_runtime.bootstrap_postgres_session_store",
        lambda: (_ for _ in ()).throw(
            PostgresSessionStoreBootstrapError("postgres bootstrap failed")
        ),
    )

    with pytest.raises(RuntimeError, match="postgres bootstrap failed"):
        get_default_session_store()


def test_default_session_store_cache_requires_explicit_clear_before_backend_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime backend changes should not silently replace the cached default store."""
    monkeypatch.delenv(SESSION_STORE_BACKEND_ENV, raising=False)
    first = get_default_session_store()

    switched_connection = object()
    _set_valid_postgres_runtime_env(monkeypatch)
    monkeypatch.setattr(
        "session_store_runtime.bootstrap_postgres_session_store",
        lambda: switched_connection,
    )

    still_cached = get_default_session_store()
    clear_default_session_store_cache()
    rebuilt = get_default_session_store()

    assert still_cached is first
    assert isinstance(rebuilt, PostgresSessionStore)
    assert rebuilt.connection is switched_connection


def test_clear_default_session_store_cache_also_refreshes_cached_runtime_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clearing the default store cache should also drop cached runtime settings."""
    monkeypatch.delenv(SESSION_STORE_BACKEND_ENV, raising=False)
    cached_file_settings = get_session_store_runtime_settings()

    switched_connection = object()
    _set_valid_postgres_runtime_env(monkeypatch)
    monkeypatch.setattr(
        "session_store_runtime.bootstrap_postgres_session_store",
        lambda: switched_connection,
    )

    still_cached_settings = get_session_store_runtime_settings()
    clear_default_session_store_cache()
    refreshed_settings = get_session_store_runtime_settings()
    rebuilt_store = get_default_session_store()

    assert cached_file_settings.backend == "file"
    assert still_cached_settings is cached_file_settings
    assert refreshed_settings.backend == "postgres"
    assert isinstance(rebuilt_store, PostgresSessionStore)
    assert rebuilt_store.connection is switched_connection


def test_default_session_store_cache_recovers_cleanly_after_failed_postgres_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed PostgreSQL bootstrap should not poison later explicit rebuilds."""
    _set_valid_postgres_runtime_env(monkeypatch)
    monkeypatch.setattr(
        "session_store_runtime.bootstrap_postgres_session_store",
        lambda: (_ for _ in ()).throw(
            PostgresSessionStoreBootstrapError("postgres bootstrap failed")
        ),
    )

    with pytest.raises(RuntimeError, match="postgres bootstrap failed"):
        get_default_session_store()

    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, "file")
    clear_default_session_store_cache()

    rebuilt = get_default_session_store()

    assert isinstance(rebuilt, FileSessionStore)


def test_default_session_store_cache_supports_file_to_postgres_to_file_switch_with_explicit_clears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One process should rebuild the default store cleanly across explicit switches."""
    monkeypatch.delenv(SESSION_STORE_BACKEND_ENV, raising=False)
    file_store = get_default_session_store()
    assert isinstance(file_store, FileSessionStore)

    switched_connection = object()
    _set_valid_postgres_runtime_env(monkeypatch)
    monkeypatch.setattr(
        "session_store_runtime.bootstrap_postgres_session_store",
        lambda: switched_connection,
    )
    clear_default_session_store_cache()
    postgres_store = get_default_session_store()

    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, "file")
    clear_default_session_store_cache()
    rebuilt_file_store = get_default_session_store()

    assert isinstance(postgres_store, PostgresSessionStore)
    assert postgres_store.connection is switched_connection
    assert isinstance(rebuilt_file_store, FileSessionStore)
    assert rebuilt_file_store is file_store


def test_default_session_store_preserves_current_file_layout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Default writes should still create the established session files."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)
    store = get_default_session_store()
    metadata = _metadata("session-default-store")

    _assert_file_mode_round_trip(store, metadata.session_id)

    session_dir = tmp_path / metadata.session_id
    assert (session_dir / "session.json").exists()
    assert (session_dir / "progress.json").exists()
    assert (session_dir / "results.jsonl").exists()
