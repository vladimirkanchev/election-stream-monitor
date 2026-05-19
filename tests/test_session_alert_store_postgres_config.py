"""Focused tests for PostgreSQL alert-store settings.

This file stays at the Postgres bootstrap config seam: env ingestion, caching,
and direct URL validation.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from session_alert_store_postgres_config import (
    POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV,
    POSTGRES_ALERT_DATABASE_URL_ENV,
    PostgresAlertStoreConfigurationError,
    PostgresAlertStoreSettings,
    clear_postgres_alert_store_settings_cache,
    get_postgres_alert_store_settings,
    validate_postgres_alert_store_settings,
)


@pytest.fixture(autouse=True)
def _clear_postgres_alert_store_settings_cache() -> Iterator[None]:
    """Keep cached Postgres alert-store settings isolated between env tests."""
    clear_postgres_alert_store_settings_cache()
    yield
    clear_postgres_alert_store_settings_cache()


def test_get_postgres_alert_store_settings_defaults_to_no_database_url(
    monkeypatch,
) -> None:
    """The Postgres alert-store settings should stay inert by default."""
    monkeypatch.delenv(POSTGRES_ALERT_DATABASE_URL_ENV, raising=False)
    monkeypatch.delenv(POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV, raising=False)

    settings = get_postgres_alert_store_settings()

    assert settings.database_url is None
    assert settings.auto_create_tables is True


def test_get_postgres_alert_store_settings_reads_env_overrides(monkeypatch) -> None:
    """The settings loader should ingest the Postgres bootstrap env vars."""
    monkeypatch.setenv(
        POSTGRES_ALERT_DATABASE_URL_ENV,
        "postgresql://alerts:secret@db.example/esm",
    )
    monkeypatch.setenv(POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV, "false")

    settings = get_postgres_alert_store_settings()

    assert settings == PostgresAlertStoreSettings(
        database_url="postgresql://alerts:secret@db.example/esm",
        auto_create_tables=False,
    )


def test_validate_postgres_alert_store_settings_requires_database_url() -> None:
    """Bootstrap validation should fail early when no database URL is configured."""
    with pytest.raises(
        PostgresAlertStoreConfigurationError,
        match=(
            "PostgreSQL alert store requires "
            f"{POSTGRES_ALERT_DATABASE_URL_ENV}"
        ),
    ):
        validate_postgres_alert_store_settings(
            PostgresAlertStoreSettings(
                database_url=None,
                auto_create_tables=True,
            )
        )


def test_validate_postgres_alert_store_settings_rejects_non_postgres_scheme() -> None:
    """Bootstrap validation should reject non-PostgreSQL URLs."""
    with pytest.raises(
        PostgresAlertStoreConfigurationError,
        match="must use a postgres or postgresql URL",
    ):
        validate_postgres_alert_store_settings(
            PostgresAlertStoreSettings(
                database_url="sqlite:///tmp/alerts.db",
                auto_create_tables=True,
            )
        )


def test_get_postgres_alert_store_settings_normalizes_blank_database_url_to_none(
    monkeypatch,
) -> None:
    """Blank database URLs should stay inert so Postgres mode must be explicit."""
    monkeypatch.setenv(POSTGRES_ALERT_DATABASE_URL_ENV, "   ")

    settings = get_postgres_alert_store_settings()

    assert settings.database_url is None


def test_get_postgres_alert_store_settings_parses_mixed_case_boolean_override(
    monkeypatch,
) -> None:
    """Boolean bootstrap settings should tolerate mixed-case operator input."""
    monkeypatch.setenv(POSTGRES_ALERT_DATABASE_URL_ENV, "postgresql://alerts:secret@db.example/esm")
    monkeypatch.setenv(POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV, "FaLsE")

    settings = get_postgres_alert_store_settings()

    assert settings.auto_create_tables is False


def test_get_postgres_alert_store_settings_falls_back_on_invalid_boolean_override(
    monkeypatch,
) -> None:
    """Invalid boolean env values should fall back to the default bootstrap mode."""
    monkeypatch.setenv(POSTGRES_ALERT_DATABASE_URL_ENV, "postgresql://alerts:secret@db.example/esm")
    monkeypatch.setenv(POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV, "not-a-bool")

    settings = get_postgres_alert_store_settings()

    assert settings.auto_create_tables is True
