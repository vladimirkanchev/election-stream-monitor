"""Resolve the runtime-default `SessionStore`.

Callers use this module to obtain the active durable-session backend without
depending on file or PostgreSQL bootstrap details. File remains the default;
PostgreSQL is available through explicit runtime config.
"""

from __future__ import annotations

from functools import lru_cache

from session_store import SessionStore
from session_store_file import DEFAULT_FILE_SESSION_STORE
from session_store_postgres import (
    PostgresSessionStore,
    PostgresSessionStoreBootstrapError,
    bootstrap_postgres_session_store,
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


@lru_cache(maxsize=1)
def get_default_session_store() -> SessionStore:
    """Return the cached default store for the current runtime settings."""
    return _build_default_session_store(get_session_store_runtime_settings())


def clear_default_session_store_cache() -> None:
    """Clear the cached store instance and cached runtime settings."""
    get_default_session_store.cache_clear()
    clear_session_store_runtime_settings_cache()


def _build_default_session_store(settings: SessionStoreRuntimeSettings) -> SessionStore:
    """Resolve validated runtime settings into a concrete store."""
    validate_session_store_runtime_settings(settings)
    if settings.backend == DEFAULT_SESSION_STORE_BACKEND:
        return DEFAULT_FILE_SESSION_STORE
    if settings.backend == "postgres":
        return _build_postgres_default_session_store()
    raise SessionStoreRuntimeConfigurationError(
        f"Unsupported session-store backend: {settings.backend}"
    )


def _build_postgres_default_session_store() -> SessionStore:
    """Build the PostgreSQL store for explicit runtime opt-in."""
    try:
        return PostgresSessionStore(bootstrap_postgres_session_store())
    except PostgresSessionStoreBootstrapError as err:
        raise SessionStoreRuntimeConfigurationError(str(err)) from err
