"""Focused tests for the runtime-selected default alert store.

These tests keep the runtime story narrow: `file` stays the default, `postgres`
is opt-in, and existing callers still go through the same default-store seam.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from tests.session_alert_test_support import (
    REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    close_store_if_possible,
    configure_session_alert_test,
    write_known_session,
)

from session_alert_store import (
    DEFAULT_SESSION_ALERT_STORE,
    FileSessionAlertStore,
    clear_default_session_alert_store_cache,
    get_default_session_alert_store,
)
from session_alert_store_postgres import PostgresSessionAlertStore
from session_alert_store_postgres_config import (
    POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV,
)
from session_alert_store_runtime_config import ALERT_STORE_BACKEND_ENV
from session_alerts import read_session_alert_events
from session_models import AlertEvent


class RecordingRuntimeAlertStore:
    """Small fake store used to prove runtime-selected backend routing."""

    def __init__(self) -> None:
        self.read_session_ids: list[str] = []
        self.appended_events: list[AlertEvent] = []

    def append_alert(self, event: AlertEvent) -> None:
        """Record one alert append through the runtime-selected default store."""
        self.appended_events.append(event)

    def read_session_alert_events(self, session_id: str) -> list[dict[str, object]]:
        """Record one read through the runtime-selected default store."""
        self.read_session_ids.append(session_id)
        return []


def _select_postgres_runtime_backend(
    monkeypatch: pytest.MonkeyPatch,
    *,
    store: RecordingRuntimeAlertStore | None = None,
) -> RecordingRuntimeAlertStore:
    """Select Postgres mode and patch the default-store builder for one test."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    runtime_store = store or RecordingRuntimeAlertStore()
    monkeypatch.setattr(
        "session_alert_store._build_postgres_default_session_alert_store",
        lambda: runtime_store,
    )
    return runtime_store


@pytest.fixture(autouse=True)
def _clear_default_alert_store_cache() -> Iterator[None]:
    """Keep cached default-store selection isolated between runtime tests."""
    clear_default_session_alert_store_cache()
    yield
    clear_default_session_alert_store_cache()


def test_get_default_session_alert_store_defaults_to_file_backend(
    monkeypatch,
) -> None:
    """The default alert store should stay file-backed unless explicitly changed."""
    monkeypatch.delenv(ALERT_STORE_BACKEND_ENV, raising=False)

    store = get_default_session_alert_store()

    assert isinstance(store, FileSessionAlertStore)


def test_get_default_session_alert_store_builds_postgres_backend_when_selected(
    monkeypatch,
) -> None:
    """The runtime selector should build the Postgres store only when requested."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    built_stores: list[RecordingRuntimeAlertStore] = []

    def fake_build_postgres_default_session_alert_store() -> RecordingRuntimeAlertStore:
        store = RecordingRuntimeAlertStore()
        built_stores.append(store)
        return store

    monkeypatch.setattr(
        "session_alert_store._build_postgres_default_session_alert_store",
        fake_build_postgres_default_session_alert_store,
    )

    first = get_default_session_alert_store()
    second = get_default_session_alert_store()

    assert first is second
    assert built_stores == [first]


def test_get_default_session_alert_store_normalizes_runtime_backend_env_whitespace_and_case(
    monkeypatch,
) -> None:
    """Whitespace and mixed-case backend env values should still select Postgres mode."""
    built_stores: list[RecordingRuntimeAlertStore] = []
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "  PoStGrEs  ")

    def fake_build_postgres_default_session_alert_store() -> RecordingRuntimeAlertStore:
        store = RecordingRuntimeAlertStore()
        built_stores.append(store)
        return store

    monkeypatch.setattr(
        "session_alert_store._build_postgres_default_session_alert_store",
        fake_build_postgres_default_session_alert_store,
    )

    store = get_default_session_alert_store()

    assert store is built_stores[0]


def test_get_default_session_alert_store_raises_when_postgres_bootstrap_fails(
    monkeypatch,
) -> None:
    """Explicit Postgres mode should fail clearly instead of silently falling back."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")

    def fake_build_postgres_default_session_alert_store() -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "session_alert_store._build_postgres_default_session_alert_store",
        fake_build_postgres_default_session_alert_store,
    )

    with pytest.raises(RuntimeError, match="boom"):
        get_default_session_alert_store()


def test_default_alert_service_entrypoint_uses_runtime_selected_backend(
    monkeypatch,
) -> None:
    """The raw alert service should honor runtime backend selection without caller churn."""
    store = _select_postgres_runtime_backend(monkeypatch)

    assert read_session_alert_events("runtime-selected-session") == []
    assert store.read_session_ids == ["runtime-selected-session"]


def test_default_alert_store_proxy_uses_runtime_selected_backend_for_writes(
    monkeypatch,
) -> None:
    """The default seam proxy should keep the compatibility write path stable."""
    store = _select_postgres_runtime_backend(monkeypatch)

    event = AlertEvent(
        session_id="runtime-store-write",
        timestamp_utc="2026-05-19 18:00:00",
        detector_id="video_metrics",
        title="Black screen detected",
        message="Delegated through the runtime-selected store backend.",
        severity="warning",
        source_name="segment_0001.ts",
    )

    DEFAULT_SESSION_ALERT_STORE.append_alert(event)

    assert store.appended_events == [event]


def test_default_alert_store_cache_requires_explicit_clear_before_backend_switch(
    monkeypatch,
) -> None:
    """Runtime backend changes should not silently replace the cached default store."""
    monkeypatch.delenv(ALERT_STORE_BACKEND_ENV, raising=False)
    first = get_default_session_alert_store()

    switched_store = RecordingRuntimeAlertStore()
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setattr(
        "session_alert_store._build_postgres_default_session_alert_store",
        lambda: switched_store,
    )

    still_cached = get_default_session_alert_store()
    clear_default_session_alert_store_cache()
    rebuilt = get_default_session_alert_store()

    assert still_cached is first
    assert rebuilt is switched_store


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL runtime-store smoke test is opt-in.",
)
def test_real_postgres_default_alert_store_cache_reuses_then_rebuilds_store(
    monkeypatch,
) -> None:
    """The runtime cache should reuse one live Postgres store until it is explicitly cleared."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setenv(POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV, "1")

    first = get_default_session_alert_store()
    second = get_default_session_alert_store()
    assert isinstance(first, PostgresSessionAlertStore)
    assert first is second

    clear_default_session_alert_store_cache()
    rebuilt = get_default_session_alert_store()
    assert isinstance(rebuilt, PostgresSessionAlertStore)
    assert rebuilt is not first

    for store in (first, rebuilt):
        close_store_if_possible(store)


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL runtime-store smoke test is opt-in.",
)
def test_real_postgres_default_alert_store_rebuild_reads_existing_rows_after_cache_clear(
    monkeypatch,
    tmp_path,
) -> None:
    """Clearing the runtime cache should rebuild the live Postgres store without losing reads."""

    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setenv(POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV, "1")

    session_id = "runtime-store-cache-rebuild-live"
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, session_id)

    first = get_default_session_alert_store()
    assert isinstance(first, PostgresSessionAlertStore)
    DEFAULT_SESSION_ALERT_STORE.append_alert(
        AlertEvent(
            session_id=session_id,
            timestamp_utc="2026-05-19 22:00:00",
            detector_id="video_metrics",
            title="Cache rebuild alert",
            message="Persisted before clearing the runtime cache.",
            severity="warning",
            source_name="segment_0001.ts",
        )
    )

    clear_default_session_alert_store_cache()
    rebuilt = get_default_session_alert_store()
    assert isinstance(rebuilt, PostgresSessionAlertStore)
    assert rebuilt is not first

    alerts = rebuilt.read_session_alert_events(session_id)

    assert [alert["title"] for alert in alerts] == ["Cache rebuild alert"]

    for store in (first, rebuilt):
        close_store_if_possible(store)
