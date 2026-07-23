"""Shared helpers for alert-store, runtime-selection, and boundary tests.

This module owns small reusable seams that keep alert-store tests explicit
without repeating session bootstrap, runtime-selection setup, or normalized
alert payload literals. Live PostgreSQL helpers require explicit opt-in and
are limited to disposable-database smoke tests.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import os
from pathlib import Path
from typing import cast
from uuid import uuid4

import config
import pytest
from session_alert_report import SessionAlertReport, build_session_alert_report
from session_alert_incidents import AlertTimelineEntryPayload, IncidentSummaryPayload
from session_alerts import AlertSummaryPayload
from session_alert_store import (
    AlertReadLimitExceededError,
    AlertEventPayload,
    SessionAlertStore,
    clear_default_session_alert_store_cache,
    get_default_session_alert_store,
)
from session_alert_store_postgres import (
    PostgresAlertStoreConnection,
    PostgresSessionAlertStore,
    connect_postgres_alert_store,
    reset_postgres_alert_store_schema,
)
from session_alert_store_postgres_config import (
    POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV,
    POSTGRES_ALERT_DATABASE_URL_ENV,
)
from session_alert_store_runtime_config import ALERT_STORE_BACKEND_ENV
from session_models import AlertEvent, EventSeverity

AlertPayload = dict[str, object]
AlertLogRow = AlertPayload | str
SessionRootBuilder = Callable[[pytest.MonkeyPatch, Path], Path]
REAL_POSTGRES_ALERT_STORE_SMOKE_ENV = "POSTGRES_ALERT_STORE_REAL_SMOKE"


def is_real_postgres_alert_store_smoke_enabled(
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Return whether live-smoke opt-in, PostgreSQL selection, and a URL are set."""
    values = os.environ if environ is None else environ
    return (
        values.get(REAL_POSTGRES_ALERT_STORE_SMOKE_ENV) == "1"
        and values.get(ALERT_STORE_BACKEND_ENV, "").strip().lower() == "postgres"
        and bool(values.get(POSTGRES_ALERT_DATABASE_URL_ENV, "").strip())
    )


REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED = is_real_postgres_alert_store_smoke_enabled()


def build_snapshot_alert_report(snapshot: dict[str, object]) -> SessionAlertReport:
    """Return the shared compact report shape used by demo and assertion code."""
    return build_session_alert_report(snapshot)


class StaticAlertStore(SessionAlertStore):
    """Read-only test store that serves one stable alert history."""

    def __init__(self, session_id: str, alerts: list[AlertEventPayload]) -> None:
        self._session_id = session_id
        self._alerts = alerts

    def append_alert(self, event: AlertEvent) -> None:  # pragma: no cover - defensive only
        raise AssertionError("append_alert should not be called in read-only seam tests")

    def read_session_alert_events(
        self,
        session_id: str,
        *,
        max_rows: int | None = None,
    ) -> list[AlertEventPayload]:
        assert session_id == self._session_id
        if max_rows is not None and len(self._alerts) > max_rows:
            raise AlertReadLimitExceededError(max_rows)
        return self._alerts


class FailingReadAlertStore(SessionAlertStore):
    """Read-path failure seam for tests that need deterministic backend errors."""

    def __init__(self, session_id: str, message: str) -> None:
        self._session_id = session_id
        self._message = message

    def append_alert(self, event: AlertEvent) -> None:  # pragma: no cover - defensive only
        raise AssertionError("append_alert should not be called in this read-path test")

    def read_session_alert_events(
        self,
        session_id: str,
        *,
        max_rows: int | None = None,
    ) -> list[AlertEventPayload]:
        assert session_id == self._session_id
        raise RuntimeError(self._message)


def configure_session_alert_test(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point one test at an isolated temporary session-output root."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)
    return tmp_path


def select_runtime_postgres_store(
    monkeypatch: pytest.MonkeyPatch,
    store: SessionAlertStore,
) -> None:
    """Force the default alert-store seam through a Postgres-selected store."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setattr(
        "session_alert_store._build_postgres_default_session_alert_store",
        lambda: store,
    )
    clear_default_session_alert_store_cache()


def install_runtime_postgres_bootstrap_failure(
    monkeypatch: pytest.MonkeyPatch,
    *,
    message: str = "postgres bootstrap failed",
) -> None:
    """Force the runtime-selected Postgres bootstrap path to fail deterministically."""
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setattr(
        "session_alert_store._build_postgres_default_session_alert_store",
        lambda: (_ for _ in ()).throw(RuntimeError(message)),
    )
    clear_default_session_alert_store_cache()


def install_runtime_postgres_session_alerts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    session_id: str,
    alerts: list[AlertEventPayload],
) -> None:
    """Seed one known session and route its alert reads through the Postgres seam."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, session_id)
    select_runtime_postgres_store(monkeypatch, StaticAlertStore(session_id, alerts))


def build_live_runtime_postgres_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    session_id: str,
    session_root_builder: SessionRootBuilder | None = None,
) -> PostgresSessionAlertStore:
    """Seed known session metadata, then select the live PostgreSQL alert store."""
    build_session_root = session_root_builder or configure_session_alert_test
    session_root = build_session_root(monkeypatch, tmp_path)
    write_known_session(session_root, session_id)
    return select_live_runtime_postgres_alert_store(monkeypatch)


def select_live_runtime_postgres_alert_store(
    monkeypatch: pytest.MonkeyPatch,
) -> PostgresSessionAlertStore:
    """Select and return the real PostgreSQL alert store for an opt-in test.

    The caller supplies the smoke flag and disposable database URL. This helper
    aligns runtime selection, bootstrap intent, and default-store cache state.
    """
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setenv(POSTGRES_ALERT_AUTO_CREATE_TABLES_ENV, "1")
    clear_default_session_alert_store_cache()
    store = get_default_session_alert_store()
    assert isinstance(store, PostgresSessionAlertStore)
    return store


def close_store_if_possible(store: object) -> None:
    """Close a live test store or its wrapped connection when available."""
    close = getattr(store, "close", None)
    if callable(close):
        close()
        return
    connection = getattr(store, "_connection", None)
    close = getattr(connection, "close", None)
    if callable(close):
        close()


def build_isolated_postgres_alert_store() -> tuple[
    PostgresAlertStoreConnection,
    PostgresSessionAlertStore,
]:
    """Build a live-smoke store after destructively resetting a disposable database."""
    connection = connect_postgres_alert_store()
    try:
        reset_postgres_alert_store_schema(connection)
    except Exception:
        close_store_if_possible(connection)
        raise
    return connection, PostgresSessionAlertStore(connection)


def build_unique_session_id(prefix: str) -> str:
    """Build a unique session id for live runtime or database smoke tests."""
    return f"{prefix}-{uuid4().hex}"


def build_persisted_alert(
    session_id: str,
    *,
    timestamp_utc: str,
    detector_id: str,
    title: str,
    message: str,
    severity: str,
    source_name: str,
    window_index: int | None = None,
    window_start_sec: float | None = None,
) -> AlertPayload:
    """Build one alert row in its persisted JSONL shape."""
    alert: AlertPayload = {
        "session_id": session_id,
        "timestamp_utc": timestamp_utc,
        "detector_id": detector_id,
        "title": title,
        "message": message,
        "severity": severity,
        "source_name": source_name,
    }
    if window_index is not None:
        alert["window_index"] = window_index
    if window_start_sec is not None:
        alert["window_start_sec"] = window_start_sec
    return alert


def build_normalized_alert(
    session_id: str,
    *,
    timestamp_utc: str,
    detector_id: str,
    title: str,
    message: str,
    severity: str,
    source_name: str,
    window_index: int | None = None,
    window_start_sec: float | None = None,
) -> AlertEventPayload:
    """Build one alert row in the normalized read/query shape."""
    alert = build_persisted_alert(
        session_id,
        timestamp_utc=timestamp_utc,
        detector_id=detector_id,
        title=title,
        message=message,
        severity=severity,
        source_name=source_name,
        window_index=window_index,
        window_start_sec=window_start_sec,
    )
    alert.setdefault("window_index", None)
    alert.setdefault("window_start_sec", None)
    return cast(AlertEventPayload, alert)


def build_alert_event(
    session_id: str,
    *,
    timestamp_utc: str,
    detector_id: str,
    title: str,
    message: str,
    severity: EventSeverity,
    source_name: str,
    window_index: int | None = None,
    window_start_sec: float | None = None,
) -> AlertEvent:
    """Build one concrete alert event for store and service seam tests."""
    return AlertEvent(
        session_id=session_id,
        timestamp_utc=timestamp_utc,
        detector_id=detector_id,
        title=title,
        message=message,
        severity=severity,
        source_name=source_name,
        window_index=window_index,
        window_start_sec=window_start_sec,
    )


def build_timeline_entry(
    *,
    start_time_utc: str,
    end_time_utc: str,
    detector_id: str,
    severity: EventSeverity,
    title: str,
    alert_count: int,
    source_names: list[str],
    sample_message: str,
) -> AlertTimelineEntryPayload:
    """Build one grouped timeline entry in the shared response shape."""
    return {
        "start_time_utc": start_time_utc,
        "end_time_utc": end_time_utc,
        "detector_id": detector_id,
        "severity": severity,
        "title": title,
        "alert_count": alert_count,
        "source_names": source_names,
        "sample_message": sample_message,
    }


def build_alert_summary_payload(
    session_id: str,
    *,
    total_alerts: int,
    counts_by_detector: dict[str, int],
    counts_by_severity: dict[str, int],
    first_alert_timestamp_utc: str | None,
    last_alert_timestamp_utc: str | None,
) -> AlertSummaryPayload:
    """Build the stable raw alert-summary payload."""
    return {
        "session_id": session_id,
        "total_alerts": total_alerts,
        "counts_by_detector": counts_by_detector,
        "counts_by_severity": counts_by_severity,
        "first_alert_timestamp_utc": first_alert_timestamp_utc,
        "last_alert_timestamp_utc": last_alert_timestamp_utc,
    }


def build_incident_summary_payload(
    session_id: str,
    *,
    total_alerts: int,
    total_incidents: int,
    counts_by_detector: dict[str, int],
    counts_by_severity: dict[str, int],
    top_incident_categories: dict[str, int],
    first_alert_timestamp_utc: str | None,
    last_alert_timestamp_utc: str | None,
    narrative_summary: str,
) -> IncidentSummaryPayload:
    """Build the grouped incident-summary payload."""
    return {
        **build_alert_summary_payload(
            session_id,
            total_alerts=total_alerts,
            counts_by_detector=counts_by_detector,
            counts_by_severity=counts_by_severity,
            first_alert_timestamp_utc=first_alert_timestamp_utc,
            last_alert_timestamp_utc=last_alert_timestamp_utc,
        ),
        "total_incidents": total_incidents,
        "top_incident_categories": top_incident_categories,
        "narrative_summary": narrative_summary,
    }


def assert_narrative_contains(narrative: str | None, *parts: str) -> None:
    """Assert that a narrative summary still carries the important facts."""
    assert narrative is not None
    for part in parts:
        assert part in narrative


def write_known_session(
    session_root: Path,
    session_id: str,
    *,
    alert_rows: list[AlertLogRow] | None = None,
) -> Path:
    """Create the minimal known session used by the alert seam tests."""
    session_dir = session_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "session.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "mode": "video_segments",
                "input_path": "/tmp/input",
                "selected_detectors": ["video_metrics"],
                "status": "running",
            }
        ),
        encoding="utf-8",
    )
    if alert_rows is not None:
        write_alert_log(session_dir, alert_rows)
    return session_dir


def write_alert_log(session_dir: Path, rows: list[AlertLogRow]) -> None:
    """Write one alert log from payload rows or intentionally invalid strings."""
    encoded_rows = [
        row if isinstance(row, str) else json.dumps(row)
        for row in rows
    ]
    (session_dir / "alerts.jsonl").write_text(
        "\n".join(encoded_rows),
        encoding="utf-8",
    )
