"""Configuration seam for the PostgreSQL-backed alert store.

This module owns only the narrow bootstrap settings for the Postgres alert
backend. Runtime backend selection stays elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os


POSTGRES_ALERT_DATABASE_URL_ENV = "ESM_POSTGRES_ALERT_DATABASE_URL"
POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV = "ESM_POSTGRES_ALERT_AUTO_CREATE_TABLES"
DEFAULT_POSTGRES_ALERT_DATABASE_URL: str | None = None
DEFAULT_POSTGRES_ALERT_AUTO_CREATE_TABLES = True
POSTGRES_ALERT_URL_SCHEMES = frozenset({"postgres", "postgresql"})


class PostgresAlertStoreConfigurationError(RuntimeError):
    """Raised when PostgreSQL alert-store settings are unusable for bootstrap."""


@dataclass(frozen=True)
class PostgresAlertStoreSettings:
    """Structured configuration for PostgreSQL alert-store bootstrap."""

    database_url: str | None
    auto_create_tables: bool


def _parse_bool_env(name: str, default: bool) -> bool:
    """Parse one optional boolean environment override."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_optional_string_env(name: str, default: str | None) -> str | None:
    """Parse one optional string environment override and normalize blanks."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip()
    return normalized or None


@lru_cache(maxsize=1)
def get_postgres_alert_store_settings() -> PostgresAlertStoreSettings:
    """Return cached PostgreSQL alert-store settings."""
    return PostgresAlertStoreSettings(
        database_url=_parse_optional_string_env(
            POSTGRES_ALERT_DATABASE_URL_ENV,
            DEFAULT_POSTGRES_ALERT_DATABASE_URL,
        ),
        auto_create_tables=_parse_bool_env(
            POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV,
            DEFAULT_POSTGRES_ALERT_AUTO_CREATE_TABLES,
        ),
    )


def clear_postgres_alert_store_settings_cache() -> None:
    """Clear the cached PostgreSQL alert-store settings."""
    get_postgres_alert_store_settings.cache_clear()


def validate_postgres_alert_store_settings(
    settings: PostgresAlertStoreSettings,
) -> None:
    """Validate one PostgreSQL alert-store settings object for bootstrap."""
    if settings.database_url is None:
        raise PostgresAlertStoreConfigurationError(
            f"PostgreSQL alert store requires {POSTGRES_ALERT_DATABASE_URL_ENV}"
        )

    scheme, _, _ = settings.database_url.partition("://")
    normalized_scheme = scheme.strip().lower()
    if normalized_scheme not in POSTGRES_ALERT_URL_SCHEMES:
        raise PostgresAlertStoreConfigurationError(
            f"{POSTGRES_ALERT_DATABASE_URL_ENV} must use a postgres or postgresql URL"
        )
