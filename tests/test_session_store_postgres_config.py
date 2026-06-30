"""Focused tests for PostgreSQL session-store bootstrap settings.

This file stays at the config seam: env naming, env parsing, validation, and
cache behavior. It does not exercise store reads, writes, or live connections.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from session_store_postgres_config import (
    DEFAULT_POSTGRES_SESSION_AUTO_CREATE_TABLES,
    DEFAULT_POSTGRES_SESSION_DATABASE_URL,
    DEFAULT_POSTGRES_SESSION_STORE_REAL_SMOKE,
    POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV,
    POSTGRES_SESSION_DATABASE_URL_ENV,
    POSTGRES_SESSION_STORE_REAL_SMOKE_ENV,
    PostgresSessionStoreConfigurationError,
    PostgresSessionStoreSettings,
    clear_postgres_session_store_settings_cache,
    get_postgres_session_store_settings,
    should_auto_create_postgres_session_store_tables,
    validate_postgres_session_store_settings,
)

POSTGRES_SESSION_DATABASE_URL = "postgresql://session:secret@db.example/esm"
UPDATED_POSTGRES_SESSION_DATABASE_URL = (
    "postgresql://new-user:new-secret@db.example/esm"
)


@pytest.fixture(autouse=True)
def _clear_postgres_session_store_settings_cache() -> Iterator[None]:
    """Keep cached PostgreSQL session-store settings isolated between env tests."""
    clear_postgres_session_store_settings_cache()
    yield
    clear_postgres_session_store_settings_cache()


def test_postgres_session_store_env_names_match_project_naming_convention() -> None:
    """Session-store PostgreSQL env names should stay aligned with alert-store naming."""
    assert POSTGRES_SESSION_DATABASE_URL_ENV == "ESM_POSTGRES_SESSION_DATABASE_URL"
    assert (
        POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV
        == "ESM_POSTGRES_SESSION_AUTO_CREATE_TABLES"
    )
    assert POSTGRES_SESSION_STORE_REAL_SMOKE_ENV == "POSTGRES_SESSION_STORE_REAL_SMOKE"


def test_get_postgres_session_store_settings_defaults_to_inert_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Postgres session-store settings should stay inert by default."""
    monkeypatch.delenv(POSTGRES_SESSION_DATABASE_URL_ENV, raising=False)
    monkeypatch.delenv(POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV, raising=False)
    monkeypatch.delenv(POSTGRES_SESSION_STORE_REAL_SMOKE_ENV, raising=False)

    settings = get_postgres_session_store_settings()

    assert settings == PostgresSessionStoreSettings(
        database_url=DEFAULT_POSTGRES_SESSION_DATABASE_URL,
        auto_create_tables=DEFAULT_POSTGRES_SESSION_AUTO_CREATE_TABLES,
        real_smoke_enabled=DEFAULT_POSTGRES_SESSION_STORE_REAL_SMOKE,
    )
    assert settings.auto_create_tables is False


def test_get_postgres_session_store_settings_reads_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The settings loader should ingest the PostgreSQL session-store env vars."""
    monkeypatch.setenv(POSTGRES_SESSION_DATABASE_URL_ENV, POSTGRES_SESSION_DATABASE_URL)
    monkeypatch.setenv(POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV, "false")
    monkeypatch.setenv(POSTGRES_SESSION_STORE_REAL_SMOKE_ENV, "1")

    settings = get_postgres_session_store_settings()

    assert settings == PostgresSessionStoreSettings(
        database_url=POSTGRES_SESSION_DATABASE_URL,
        auto_create_tables=False,
        real_smoke_enabled=True,
    )


def test_get_postgres_session_store_settings_supports_explicit_auto_create_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local helpers and explicit tests may opt into schema creation."""
    monkeypatch.setenv(POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV, "1")

    settings = get_postgres_session_store_settings()

    assert settings.auto_create_tables is True
    assert should_auto_create_postgres_session_store_tables(settings) is True


def test_get_postgres_session_store_settings_keeps_cached_values_until_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap cache should stay stable until callers clear it explicitly."""
    monkeypatch.setenv(POSTGRES_SESSION_DATABASE_URL_ENV, POSTGRES_SESSION_DATABASE_URL)
    first = get_postgres_session_store_settings()

    monkeypatch.setenv(
        POSTGRES_SESSION_DATABASE_URL_ENV,
        UPDATED_POSTGRES_SESSION_DATABASE_URL,
    )
    cached = get_postgres_session_store_settings()
    clear_postgres_session_store_settings_cache()
    refreshed = get_postgres_session_store_settings()

    assert cached == first
    assert refreshed == PostgresSessionStoreSettings(
        database_url=UPDATED_POSTGRES_SESSION_DATABASE_URL,
        auto_create_tables=False,
        real_smoke_enabled=False,
    )


def test_get_postgres_session_store_settings_normalizes_blank_database_url_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank database URLs should stay inert so PostgreSQL mode remains explicit."""
    monkeypatch.setenv(POSTGRES_SESSION_DATABASE_URL_ENV, "   ")

    settings = get_postgres_session_store_settings()

    assert settings.database_url is None


def test_get_postgres_session_store_settings_parses_mixed_case_boolean_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Boolean bootstrap settings should tolerate mixed-case input."""
    monkeypatch.setenv(POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV, "FaLsE")
    monkeypatch.setenv(POSTGRES_SESSION_STORE_REAL_SMOKE_ENV, "TrUe")

    settings = get_postgres_session_store_settings()

    assert settings.auto_create_tables is False
    assert settings.real_smoke_enabled is True


def test_get_postgres_session_store_settings_falls_back_on_invalid_boolean_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid boolean env values should fall back to the default bootstrap mode."""
    monkeypatch.setenv(POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV, "not-a-bool")
    monkeypatch.setenv(POSTGRES_SESSION_STORE_REAL_SMOKE_ENV, "maybe")

    settings = get_postgres_session_store_settings()

    assert settings.auto_create_tables is False
    assert settings.real_smoke_enabled is False


def test_validate_postgres_session_store_settings_requires_database_url() -> None:
    """Bootstrap validation should fail early when no database URL is configured."""
    with pytest.raises(
        PostgresSessionStoreConfigurationError,
        match=(
            "PostgreSQL session store requires "
            f"{POSTGRES_SESSION_DATABASE_URL_ENV}"
        ),
    ):
        validate_postgres_session_store_settings(
            PostgresSessionStoreSettings(
                database_url=None,
                auto_create_tables=True,
                real_smoke_enabled=False,
            )
        )


def test_validate_postgres_session_store_settings_rejects_non_postgres_scheme() -> None:
    """Bootstrap validation should reject non-PostgreSQL URLs."""
    with pytest.raises(
        PostgresSessionStoreConfigurationError,
        match="must use a postgres or postgresql URL",
    ):
        validate_postgres_session_store_settings(
            PostgresSessionStoreSettings(
                database_url="sqlite:///tmp/sessions.db",
                auto_create_tables=True,
                real_smoke_enabled=False,
            )
        )


def test_validate_postgres_session_store_settings_accepts_normalized_scheme_whitespace() -> None:
    """Bootstrap validation should tolerate surrounding whitespace and mixed-case schemes."""
    validate_postgres_session_store_settings(
        PostgresSessionStoreSettings(
            database_url=f"  {POSTGRES_SESSION_DATABASE_URL.upper()}  ",
            auto_create_tables=True,
            real_smoke_enabled=False,
        )
    )


def test_should_auto_create_postgres_session_store_tables_defaults_to_false() -> None:
    """Runtime bootstrap should refuse implicit table creation by default."""
    settings = PostgresSessionStoreSettings(
        database_url=POSTGRES_SESSION_DATABASE_URL,
        auto_create_tables=False,
        real_smoke_enabled=False,
    )

    assert should_auto_create_postgres_session_store_tables(settings) is False
