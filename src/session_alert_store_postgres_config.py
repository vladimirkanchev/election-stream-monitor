"""Bootstrap configuration for the PostgreSQL-backed alert store.

This module stays narrow on purpose: it parses and validates the PostgreSQL
URL and auto-create flag that matter only after explicit
`ESM_ALERT_STORE_BACKEND=postgres` selection. Its current auto-create default
is a rollout setting for that opt-in path, not a migration policy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

POSTGRES_ALERT_DATABASE_URL_ENV = "ESM_POSTGRES_ALERT_DATABASE_URL"
POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV = "ESM_POSTGRES_ALERT_AUTO_CREATE_TABLES"
DEFAULT_POSTGRES_ALERT_DATABASE_URL: str | None = None
DEFAULT_POSTGRES_ALERT_AUTO_CREATE_TABLES = True
POSTGRES_ALERT_URL_SCHEMES = frozenset({"postgres", "postgresql"})


class PostgresAlertStoreConfigurationError(RuntimeError):
    """Raised when PostgreSQL alert-store settings are unusable for bootstrap."""


@dataclass(frozen=True)
class PostgresAlertStoreSettings:
    """Structured settings for the explicitly selected alert-store bootstrap path."""

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
    """Return cached settings for the explicit PostgreSQL alert-store bootstrap."""
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
    """Validate explicit PostgreSQL alert-store bootstrap settings."""
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
