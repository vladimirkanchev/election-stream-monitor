"""Parse and validate runtime settings for default session-store selection.

This module owns the small runtime config surface for choosing the active
session-store backend. It keeps the current rollout explicit: `file` is still
the default, `postgres` is recognized, and PostgreSQL settings are checked only
when that backend is selected.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from typing import Literal, cast

from session_store_postgres_config import (
    PostgresSessionStoreSettings,
    get_postgres_session_store_settings,
    validate_postgres_session_store_settings,
)

SessionStoreBackend = Literal["file", "postgres"]
DEFAULT_SESSION_STORE_BACKEND: SessionStoreBackend = "file"
SESSION_STORE_BACKEND_ENV = "ESM_SESSION_STORE_BACKEND"
SUPPORTED_SESSION_STORE_BACKENDS: tuple[SessionStoreBackend, ...] = ("file", "postgres")
UNSUPPORTED_SESSION_STORE_BACKEND_MESSAGE = (
    f"{SESSION_STORE_BACKEND_ENV} must be one of: file, postgres"
)


class SessionStoreRuntimeConfigurationError(RuntimeError):
    """Raised when runtime session-store configuration is not usable."""


@dataclass(frozen=True)
class SessionStoreRuntimeSettings:
    """Normalized settings used to choose the default runtime store."""

    backend: SessionStoreBackend
    postgres: PostgresSessionStoreSettings


def _parse_backend_env(name: str, default: SessionStoreBackend) -> SessionStoreBackend:
    """Read one backend env var and fall back to the default on invalid input."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in SUPPORTED_SESSION_STORE_BACKENDS:
        return cast(SessionStoreBackend, normalized)
    return default


@lru_cache(maxsize=1)
def get_session_store_runtime_settings() -> SessionStoreRuntimeSettings:
    """Return cached runtime settings for default store selection."""
    return SessionStoreRuntimeSettings(
        backend=_parse_backend_env(
            SESSION_STORE_BACKEND_ENV,
            DEFAULT_SESSION_STORE_BACKEND,
        ),
        postgres=get_postgres_session_store_settings(),
    )


def clear_session_store_runtime_settings_cache() -> None:
    """Clear cached runtime settings and dependent PostgreSQL config."""
    get_session_store_runtime_settings.cache_clear()
    from session_store_postgres_config import (
        clear_postgres_session_store_settings_cache,
    )

    clear_postgres_session_store_settings_cache()


def validate_session_store_runtime_settings(
    settings: SessionStoreRuntimeSettings,
) -> None:
    """Validate backend selection and any backend-specific runtime requirements."""
    if settings.backend not in SUPPORTED_SESSION_STORE_BACKENDS:
        raise SessionStoreRuntimeConfigurationError(
            UNSUPPORTED_SESSION_STORE_BACKEND_MESSAGE
        )
    if settings.backend == "postgres":
        validate_postgres_session_store_settings(settings.postgres)
