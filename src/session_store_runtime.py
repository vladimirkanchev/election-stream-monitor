"""Resolve the default runtime `SessionStore`.

This module is the runtime entry point for session-store selection. Callers use
it to get the active durable-session backend without taking a dependency on
file or PostgreSQL bootstrap details. The current default remains file-backed.
"""

from __future__ import annotations

from functools import lru_cache

from session_store import SessionStore
from session_store_file import DEFAULT_FILE_SESSION_STORE
from session_store_postgres import (
    PostgresSessionStoreBootstrapError,
    load_postgres_session_store_driver,
)
from session_store_runtime_config import (
    DEFAULT_SESSION_STORE_BACKEND,
    SessionStoreRuntimeConfigurationError,
    SessionStoreRuntimeSettings,
    clear_session_store_runtime_settings_cache,
    get_session_store_runtime_settings,
    validate_session_store_runtime_settings,
)

DEFAULT_SESSION_STORE: SessionStore = DEFAULT_FILE_SESSION_STORE
POSTGRES_SESSION_STORE_RUNTIME_NOT_READY_MESSAGE = (
    "PostgreSQL session-store backend is configured but not wired into the runtime yet"
)


@lru_cache(maxsize=1)
def get_default_session_store() -> SessionStore:
    """Return the cached default store for the current runtime settings."""
    return _build_default_session_store(get_session_store_runtime_settings())


def clear_default_session_store_cache() -> None:
    """Clear cached store selection together with cached runtime settings."""
    get_default_session_store.cache_clear()
    clear_session_store_runtime_settings_cache()


def _build_default_session_store(settings: SessionStoreRuntimeSettings) -> SessionStore:
    """Resolve validated runtime settings into a concrete store instance."""
    validate_session_store_runtime_settings(settings)
    if settings.backend == DEFAULT_SESSION_STORE_BACKEND:
        return DEFAULT_FILE_SESSION_STORE
    if settings.backend == "postgres":
        return _build_postgres_default_session_store()
    raise SessionStoreRuntimeConfigurationError(
        f"Unsupported session-store backend: {settings.backend}"
    )


def _build_postgres_default_session_store() -> SessionStore:
    """Validate PostgreSQL readiness without pretending the runtime adapter exists."""
    try:
        load_postgres_session_store_driver()
    except PostgresSessionStoreBootstrapError as err:
        raise SessionStoreRuntimeConfigurationError(str(err)) from err
    raise SessionStoreRuntimeConfigurationError(
        POSTGRES_SESSION_STORE_RUNTIME_NOT_READY_MESSAGE
    )
