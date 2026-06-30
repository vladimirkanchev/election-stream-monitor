"""Configuration seam for the PostgreSQL-backed session store.

This module owns the PostgreSQL-specific env surface for session persistence.
Runtime backend selection lives elsewhere, so this file stays focused on
bootstrap settings and keeps the project default file-backed.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os


POSTGRES_SESSION_DATABASE_URL_ENV = "ESM_POSTGRES_SESSION_DATABASE_URL"
POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV = "ESM_POSTGRES_SESSION_AUTO_CREATE_TABLES"
POSTGRES_SESSION_STORE_REAL_SMOKE_ENV = "POSTGRES_SESSION_STORE_REAL_SMOKE"

DEFAULT_POSTGRES_SESSION_DATABASE_URL: str | None = None
DEFAULT_POSTGRES_SESSION_AUTO_CREATE_TABLES = False
DEFAULT_POSTGRES_SESSION_STORE_REAL_SMOKE = False
POSTGRES_SESSION_URL_SCHEMES = frozenset({"postgres", "postgresql"})


class PostgresSessionStoreConfigurationError(RuntimeError):
    """Raised when PostgreSQL bootstrap settings are unusable."""


@dataclass(frozen=True)
class PostgresSessionStoreSettings:
    """Structured env-backed settings for PostgreSQL session-store bootstrap."""

    database_url: str | None
    auto_create_tables: bool
    real_smoke_enabled: bool


def _parse_bool_env(name: str, default: bool) -> bool:
    """Parse one optional boolean env var."""
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
    """Parse one optional string env var and normalize blank values to `None`."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip()
    return normalized or None


@lru_cache(maxsize=1)
def get_postgres_session_store_settings() -> PostgresSessionStoreSettings:
    """Return cached PostgreSQL session-store bootstrap settings."""
    return PostgresSessionStoreSettings(
        database_url=_parse_optional_string_env(
            POSTGRES_SESSION_DATABASE_URL_ENV,
            DEFAULT_POSTGRES_SESSION_DATABASE_URL,
        ),
        auto_create_tables=_parse_bool_env(
            POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV,
            DEFAULT_POSTGRES_SESSION_AUTO_CREATE_TABLES,
        ),
        real_smoke_enabled=_parse_bool_env(
            POSTGRES_SESSION_STORE_REAL_SMOKE_ENV,
            DEFAULT_POSTGRES_SESSION_STORE_REAL_SMOKE,
        ),
    )


def clear_postgres_session_store_settings_cache() -> None:
    """Clear cached PostgreSQL session-store bootstrap settings."""
    get_postgres_session_store_settings.cache_clear()


def validate_postgres_session_store_settings(
    settings: PostgresSessionStoreSettings,
) -> None:
    """Validate PostgreSQL bootstrap settings before driver or connection work."""
    if settings.database_url is None:
        raise PostgresSessionStoreConfigurationError(
            f"PostgreSQL session store requires {POSTGRES_SESSION_DATABASE_URL_ENV}"
        )

    scheme, _, _ = settings.database_url.partition("://")
    normalized_scheme = scheme.strip().lower()
    if normalized_scheme not in POSTGRES_SESSION_URL_SCHEMES:
        raise PostgresSessionStoreConfigurationError(
            f"{POSTGRES_SESSION_DATABASE_URL_ENV} must use a postgres or postgresql URL"
        )


def should_auto_create_postgres_session_store_tables(
    settings: PostgresSessionStoreSettings,
) -> bool:
    """Return whether schema creation is explicitly enabled."""
    return settings.auto_create_tables
