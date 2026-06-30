"""Focused tests for runtime session-store selection and rollback safety."""

from pathlib import Path

import config
import pytest
from session_models import ResultEvent, SessionMetadata, SessionProgress
from session_store_file import DEFAULT_FILE_SESSION_STORE, FileSessionStore
from session_store_postgres import PostgresSessionStoreBootstrapError
from session_store_postgres_config import (
    POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV,
    POSTGRES_SESSION_DATABASE_URL_ENV,
)
from session_store_runtime import (
    DEFAULT_SESSION_STORE,
    POSTGRES_SESSION_STORE_RUNTIME_NOT_READY_MESSAGE,
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

VALID_POSTGRES_SESSION_URL = "postgresql://session:secret@db.example/esm"


def _metadata(session_id: str) -> SessionMetadata:
    """Build minimal metadata for file-backed default-store tests."""
    return SessionMetadata(
        session_id=session_id,
        mode="video_files",
        input_path="/tmp/clip.mp4",
        selected_detectors=["video_metrics"],
        status="running",
    )


def _assert_file_runtime_settings(settings: SessionStoreRuntimeSettings) -> None:
    """Assert that runtime settings keep the current file-backed default."""
    assert settings.backend == DEFAULT_SESSION_STORE_BACKEND


def _set_valid_postgres_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Select PostgreSQL mode with the minimum valid bootstrap settings."""
    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setenv(POSTGRES_SESSION_DATABASE_URL_ENV, VALID_POSTGRES_SESSION_URL)


@pytest.fixture(autouse=True)
def _clear_runtime_store_caches() -> None:
    """Keep runtime-store selection deterministic across env-driven tests."""
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


def test_default_session_store_only_fails_for_missing_postgres_driver_when_postgres_is_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing psycopg should matter only after explicit PostgreSQL selection."""
    monkeypatch.setenv(
        POSTGRES_SESSION_DATABASE_URL_ENV,
        "postgresql://stale:stale@localhost:5432/election_stream_monitor",
    )
    monkeypatch.delenv(SESSION_STORE_BACKEND_ENV, raising=False)
    monkeypatch.setattr(
        "session_store_runtime.load_postgres_session_store_driver",
        lambda: (_ for _ in ()).throw(AssertionError("postgres driver should not load")),
    )

    default_store = get_default_session_store()
    assert default_store is DEFAULT_FILE_SESSION_STORE

    clear_default_session_store_cache()
    _set_valid_postgres_runtime_env(monkeypatch)
    monkeypatch.setattr(
        "session_store_runtime.load_postgres_session_store_driver",
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


def test_default_session_store_reports_runtime_not_ready_after_driver_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PostgreSQL mode should stay honest until the concrete store is wired in."""
    _set_valid_postgres_runtime_env(monkeypatch)
    monkeypatch.setattr(
        "session_store_runtime.load_postgres_session_store_driver",
        lambda: object(),
    )

    with pytest.raises(
        RuntimeError,
        match=POSTGRES_SESSION_STORE_RUNTIME_NOT_READY_MESSAGE,
    ):
        get_default_session_store()


def test_default_session_store_postgres_mode_does_not_bootstrap_tables_before_adapter_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PostgreSQL selection should fail closed before any schema bootstrap path is implied."""
    _set_valid_postgres_runtime_env(monkeypatch)
    monkeypatch.setenv(POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV, "1")
    seen: list[str] = []

    monkeypatch.setattr(
        "session_store_runtime.load_postgres_session_store_driver",
        lambda: seen.append("load-driver") or object(),
    )

    with pytest.raises(
        RuntimeError,
        match=POSTGRES_SESSION_STORE_RUNTIME_NOT_READY_MESSAGE,
    ):
        get_default_session_store()

    assert seen == ["load-driver"]


def test_default_session_store_preserves_current_file_layout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Default writes should still create the established session files."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)
    store = get_default_session_store()
    metadata = _metadata("session-default-store")

    store.write_metadata(metadata)
    store.write_progress(SessionProgress.initial(session_id=metadata.session_id, total_count=1))
    store.append_result(
        ResultEvent(
            session_id=metadata.session_id,
            detector_id="video_metrics",
            payload={"window_index": 0},
        )
    )

    session_dir = tmp_path / metadata.session_id
    assert (session_dir / "session.json").exists()
    assert (session_dir / "progress.json").exists()
    assert (session_dir / "results.jsonl").exists()
    assert store.read_snapshot(metadata.session_id)["session"] == metadata.to_dict()
