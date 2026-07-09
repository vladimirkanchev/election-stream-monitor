"""Shared support for opt-in live PostgreSQL runtime smoke tests.

This helper module owns the live runtime fixture: backend selection, real
schema reset, session-output isolation, request access, and cleanup.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import shutil

import config
import httpx
import pytest
from session_alert_store import clear_default_session_alert_store_cache
from session_store_postgres_config import (
    POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV,
    POSTGRES_SESSION_DATABASE_URL_ENV,
    POSTGRES_SESSION_STORE_REAL_SMOKE_ENV,
)
from session_store_runtime import clear_default_session_store_cache
from session_store_runtime_config import SESSION_STORE_BACKEND_ENV
from tests.api_boundary_test_support import request as api_request
from tests.session_store_postgres_test_support import (
    PostgresSessionStoreConnection,
    bootstrap_isolated_postgres_session_store,
    close_postgres_session_store_connection_if_possible,
)

RuntimeRequest = Callable[..., httpx.Response]


@dataclass(frozen=True)
class LivePostgresRuntimeFixture:
    """Compact context for one isolated live PostgreSQL runtime smoke."""

    session_root: Path
    connection: PostgresSessionStoreConnection
    request: RuntimeRequest


def _clear_runtime_backend_caches() -> None:
    """Reset cached runtime-selected stores around live smoke."""
    clear_default_session_alert_store_cache()
    clear_default_session_store_cache()


@contextmanager
def live_postgres_runtime_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[LivePostgresRuntimeFixture]:
    """Yield one isolated live FastAPI-to-worker runtime context."""
    if os.getenv(POSTGRES_SESSION_STORE_REAL_SMOKE_ENV) != "1":
        raise AssertionError(
            "Live PostgreSQL runtime smoke requires POSTGRES_SESSION_STORE_REAL_SMOKE=1."
        )
    database_url = os.getenv(POSTGRES_SESSION_DATABASE_URL_ENV)
    if not database_url:
        raise AssertionError(
            "Live PostgreSQL runtime smoke requires ESM_POSTGRES_SESSION_DATABASE_URL."
        )

    session_root = tmp_path / "runtime-session-output"
    with monkeypatch.context() as runtime_patch:
        runtime_patch.setenv(SESSION_STORE_BACKEND_ENV, "postgres")
        runtime_patch.setenv(POSTGRES_SESSION_AUTO_CREATE_TABLES_ENV, "1")
        runtime_patch.setattr(config, "SESSION_OUTPUT_FOLDER", session_root)

        _clear_runtime_backend_caches()
        connection = bootstrap_isolated_postgres_session_store()
        _clear_runtime_backend_caches()

        try:
            yield LivePostgresRuntimeFixture(
                session_root=session_root,
                connection=connection,
                request=api_request,
            )
        finally:
            _clear_runtime_backend_caches()
            close_postgres_session_store_connection_if_possible(connection)
            if session_root.exists():
                shutil.rmtree(session_root)
