"""Resolve the active runtime `SessionStore`.

Current runtime contract:

- `file` remains the default session-store backend
- explicit `postgres` selection builds a PostgreSQL-backed store
- parent reads, cancel writes, and detached workers use the same selected
  backend for one runtime
- explicit PostgreSQL bootstrap failures stay visible instead of degrading
  silently to file mode
"""

from __future__ import annotations

from functools import lru_cache

from postgres_diagnostics import redact_postgres_diagnostic
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
    """Return the cached store for the active runtime backend."""
    return _build_default_session_store(get_session_store_runtime_settings())


def clear_default_session_store_cache() -> None:
    """Clear cached store resolution and the runtime settings behind it."""
    get_default_session_store.cache_clear()
    clear_session_store_runtime_settings_cache()


def _build_default_session_store(settings: SessionStoreRuntimeSettings) -> SessionStore:
    """Resolve validated settings to the file default or explicit PostgreSQL store."""
    validate_session_store_runtime_settings(settings)
    if settings.backend == DEFAULT_SESSION_STORE_BACKEND:
        return DEFAULT_FILE_SESSION_STORE
    if settings.backend == "postgres":
        return _build_postgres_default_session_store()
    raise SessionStoreRuntimeConfigurationError(
        f"Unsupported session-store backend: {settings.backend}"
    )


def _build_postgres_default_session_store() -> SessionStore:
    """Build the explicit PostgreSQL store without hidden fallback."""
    try:
        return PostgresSessionStore(bootstrap_postgres_session_store())
    except PostgresSessionStoreBootstrapError as err:
        detail = redact_postgres_diagnostic(str(err))

    raise SessionStoreRuntimeConfigurationError(detail)
