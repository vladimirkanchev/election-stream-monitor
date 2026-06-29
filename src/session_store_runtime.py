"""Resolve the default runtime `SessionStore`.

This module keeps backend selection in one place so service, runner, and CLI
code can depend on the durable-session contract without learning storage
details. At the current project stage the default remains file-backed.
"""

from __future__ import annotations

from functools import lru_cache

from session_store import SessionStore
from session_store_file import DEFAULT_FILE_SESSION_STORE
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
    """Return the cached default store for the active runtime settings."""
    return _build_default_session_store(get_session_store_runtime_settings())


def clear_default_session_store_cache() -> None:
    """Clear cached store selection and cached runtime settings together."""
    get_default_session_store.cache_clear()
    clear_session_store_runtime_settings_cache()


def _build_default_session_store(settings: SessionStoreRuntimeSettings) -> SessionStore:
    """Resolve one validated runtime settings object into a concrete store."""
    validate_session_store_runtime_settings(settings)
    if settings.backend == DEFAULT_SESSION_STORE_BACKEND:
        return DEFAULT_FILE_SESSION_STORE
    raise SessionStoreRuntimeConfigurationError(
        f"Unsupported session-store backend: {settings.backend}"
    )
