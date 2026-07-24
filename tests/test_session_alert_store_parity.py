"""Shared file/PostgreSQL parity tests for alert storage.

This file owns the durable alert-store parity matrix below the API/MCP/CLI
boundaries.

The shared suite proves only public behavior that should stay identical across
both backends:

- append order as observed through raw reads
- normalized raw read shape
- filtered and grouped read-model behavior
- empty and unknown-session semantics
- the tolerated malformed-row subset where file corruption has no SQL analogue

It intentionally does not own file-path details, SQL/bootstrap behavior, live
database setup, or backend-specific cleanup concerns. Those stay in the
backend-specific alert-store test files.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import pytest

from session_alert_incidents import build_session_incident_summary, build_session_timeline
from session_alert_store import (
    FileSessionAlertStore,
    SessionAlertsNotFoundError,
    SessionAlertStore,
)
from session_alert_store_postgres import (
    POSTGRES_ALERT_EVENTS_BOUNDED_READ_SQL,
    POSTGRES_ALERT_EVENTS_INSERT_SQL,
    POSTGRES_ALERT_EVENTS_READ_SQL,
    POSTGRES_ALERT_TIMESTAMP_FORMAT,
    PostgresSessionAlertStore,
)
from session_alerts import (
    filter_session_alert_events,
    read_session_alert_events,
    summarize_session_alert_events,
)
from session_models import AlertEvent
from tests.session_alert_test_support import (
    build_alert_event,
    build_incident_summary_payload,
    build_normalized_alert,
    build_persisted_alert,
    configure_session_alert_test,
    write_known_session,
)

ALERT_STORE_PARITY_MATRIX: tuple[str, ...] = (
    "append order through raw reads",
    "normalized raw read shape",
    "filtered raw reads and summaries",
    "grouped timelines and incident summaries",
    "known-empty and unknown-session behavior",
    "tolerated malformed-row subset where file corruption has no SQL equivalent",
)

ALERT_STORE_PARITY_PUBLIC_API: tuple[str, ...] = (
    "SessionAlertStore.append_alert()",
    "SessionAlertStore.read_session_alert_events()",
    "session_alerts.read_session_alert_events()",
    "session_alerts.filter_session_alert_events()",
    "session_alerts.summarize_session_alert_events()",
    "session_alert_incidents.build_session_timeline()",
    "session_alert_incidents.build_session_incident_summary()",
)


class InMemoryPostgresParityCursor:
    """Tiny cursor double for the Postgres alert-store SQL used in parity tests."""

    def __init__(self, connection: "InMemoryPostgresParityConnection") -> None:
        self._connection = connection
        self._rows: list[tuple[object, ...]] = []

    def __enter__(self) -> "InMemoryPostgresParityCursor":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        """Match psycopg cursor context-manager behavior without cleanup."""

    def execute(self, query: str, params: object | None = None) -> object:
        """Handle the insert and read queries used by the concrete Postgres store."""
        if query == POSTGRES_ALERT_EVENTS_INSERT_SQL:
            assert isinstance(params, tuple)
            self._connection.append_inserted_row(params)
            return object()
        if query in {
            POSTGRES_ALERT_EVENTS_READ_SQL,
            POSTGRES_ALERT_EVENTS_BOUNDED_READ_SQL,
        }:
            assert isinstance(params, tuple)
            assert len(params) in {1, 2}
            session_id = params[0]
            assert isinstance(session_id, str)
            self._rows = self._connection.read_rows_for_session(session_id)
            if query == POSTGRES_ALERT_EVENTS_BOUNDED_READ_SQL:
                assert isinstance(params[1], int)
                self._rows = self._rows[: params[1]]
            return object()
        raise AssertionError(f"Unexpected SQL in parity test: {query}")

    def fetchall(self) -> list[object]:
        """Return the stored read result for the current session query."""
        return list(self._rows)


class InMemoryPostgresParityConnection:
    """In-memory Postgres connection double that preserves inserted alert rows."""

    def __init__(self) -> None:
        self._rows: list[tuple[object, ...]] = []
        self.commit_count = 0

    def cursor(self) -> InMemoryPostgresParityCursor:
        return InMemoryPostgresParityCursor(self)

    def commit(self) -> None:
        """Record that one store operation committed successfully."""
        self.commit_count += 1

    def append_inserted_row(self, params: tuple[object, ...]) -> None:
        """Store one inserted alert row in the same shape the read query returns."""
        (
            session_id,
            timestamp_utc,
            detector_id,
            title,
            message,
            severity,
            source_name,
            window_index,
            window_start_sec,
        ) = params
        assert isinstance(session_id, str)
        assert isinstance(timestamp_utc, datetime)
        assert isinstance(detector_id, str)
        assert isinstance(title, str)
        assert isinstance(message, str)
        assert isinstance(severity, str)
        assert isinstance(source_name, str)

        self._rows.append(
            (
                session_id,
                timestamp_utc.strftime(POSTGRES_ALERT_TIMESTAMP_FORMAT),
                detector_id,
                title,
                message,
                severity,
                source_name,
                window_index,
                window_start_sec,
            )
        )

    def read_rows_for_session(self, session_id: str) -> list[tuple[object, ...]]:
        """Return rows for one session in their persisted append order."""
        return [row for row in self._rows if row[0] == session_id]


@dataclass(frozen=True)
class AlertStoreParityBackend:
    """Backend-neutral fixture state for the shared alert-store contract tests."""

    backend: Literal["file", "postgres"]
    monkeypatch: pytest.MonkeyPatch
    tmp_path: Path

    def build_store(
        self,
        *,
        known_session_ids: tuple[str, ...] = (),
        events: tuple[AlertEvent, ...] = (),
        file_alert_rows_by_session: dict[str, list[str]] | None = None,
    ) -> SessionAlertStore:
        """Build one seeded backend while keeping assertions storage-agnostic."""
        if self.backend == "file":
            session_root = configure_session_alert_test(self.monkeypatch, self.tmp_path)
            file_alert_rows_by_session = file_alert_rows_by_session or {}
            for session_id in known_session_ids:
                write_known_session(
                    session_root,
                    session_id,
                    alert_rows=file_alert_rows_by_session.get(session_id),
                )
            store: SessionAlertStore = FileSessionAlertStore()
        else:
            _mark_known_postgres_sessions(self.monkeypatch, *known_session_ids)
            store = _build_postgres_parity_store()

        for event in events:
            store.append_alert(event)
        return store


class KnownSessionExistenceStore:
    """Session-store spy for alert/session existence coordination checks."""

    def __init__(self, *known_session_ids: str) -> None:
        self._known_session_ids = set(known_session_ids)
        self.checked_session_ids: list[str] = []

    def session_exists(self, session_id: str) -> bool:
        """Record the checked session id and return its configured existence."""
        self.checked_session_ids.append(session_id)
        return session_id in self._known_session_ids


def _filtered_parity_events(session_id: str) -> list[AlertEvent]:
    """Return one mixed alert set shared by the filtered raw-read and summary checks."""
    return [
        build_alert_event(
            session_id,
            timestamp_utc="2026-05-19 12:00:00",
            detector_id="video_metrics",
            title="Early metric warning",
            message="Outside the requested time window.",
            severity="warning",
            source_name="segment_0001.ts",
        ),
        build_alert_event(
            session_id,
            timestamp_utc="2026-05-19 12:00:10",
            detector_id="video_blur",
            title="Blur info",
            message="Wrong detector for the filtered read model.",
            severity="info",
            source_name="segment_0002.ts",
        ),
        build_alert_event(
            session_id,
            timestamp_utc="2026-05-19 12:00:20",
            detector_id="video_metrics",
            title="Late metric warning",
            message="Expected filtered match.",
            severity="warning",
            source_name="segment_0003.ts",
        ),
        build_alert_event(
            session_id,
            timestamp_utc="2026-05-19 12:00:25",
            detector_id="video_metrics",
            title="Metric info",
            message="Right detector but wrong severity.",
            severity="info",
            source_name="segment_0004.ts",
        ),
    ]


def _grouped_parity_events(session_id: str) -> list[AlertEvent]:
    """Return one alert set shared by grouped timeline and grouped summary parity."""
    return [
        build_alert_event(
            session_id,
            timestamp_utc="2026-05-19 12:00:00",
            detector_id="video_metrics",
            title="Black screen detected",
            message="First grouped incident row.",
            severity="warning",
            source_name="segment_0001.ts",
        ),
        build_alert_event(
            session_id,
            timestamp_utc="2026-05-19 12:00:20",
            detector_id="video_metrics",
            title="Black screen detected",
            message="Second grouped incident row.",
            severity="warning",
            source_name="segment_0002.ts",
        ),
        build_alert_event(
            session_id,
            timestamp_utc="2026-05-19 12:02:00",
            detector_id="video_blur",
            title="Blur increased",
            message="Second grouped incident.",
            severity="info",
            source_name="segment_0003.ts",
        ),
    ]


def _filtered_grouped_parity_events(session_id: str) -> list[AlertEvent]:
    """Return one alert set shared by the grouped detector/severity filter checks."""
    return [
        build_alert_event(
            session_id,
            timestamp_utc="2026-05-19 12:10:00",
            detector_id="video_metrics",
            title="Black screen detected",
            message="Expected grouped filtered result.",
            severity="warning",
            source_name="segment_0101.ts",
        ),
        build_alert_event(
            session_id,
            timestamp_utc="2026-05-19 12:10:10",
            detector_id="video_metrics",
            title="Black screen detected",
            message="Wrong severity for the grouped filter.",
            severity="info",
            source_name="segment_0102.ts",
        ),
        build_alert_event(
            session_id,
            timestamp_utc="2026-05-19 12:10:20",
            detector_id="video_blur",
            title="Blur increased",
            message="Wrong detector for the grouped filter.",
            severity="warning",
            source_name="segment_0103.ts",
        ),
    ]


def _mark_known_postgres_sessions(
    monkeypatch: pytest.MonkeyPatch,
    *session_ids: str,
) -> None:
    """Patch PostgreSQL alert known-session checks without creating real sessions."""
    known_sessions = set(session_ids)

    def _require_known_session(candidate_session_id: str) -> None:
        if candidate_session_id not in known_sessions:
            raise SessionAlertsNotFoundError(candidate_session_id)

    monkeypatch.setattr(
        "session_alert_store_postgres.require_known_session",
        _require_known_session,
    )


def _build_postgres_parity_store() -> PostgresSessionAlertStore:
    """Build the in-memory Postgres store used across the parity matrix."""
    return PostgresSessionAlertStore(InMemoryPostgresParityConnection())


def _empty_incident_summary(session_id: str) -> dict[str, object]:
    """Return the stable empty grouped-summary envelope used by read-model callers."""
    return build_incident_summary_payload(
        session_id,
        total_alerts=0,
        total_incidents=0,
        counts_by_detector={},
        counts_by_severity={},
        top_incident_categories={},
        first_alert_timestamp_utc=None,
        last_alert_timestamp_utc=None,
        narrative_summary=f"Session {session_id} had no alerts.",
    )


def test_alert_store_parity_contract_surface_stays_public_and_compact() -> None:
    """The shared parity suite should stay anchored to the public alert-store API only."""
    assert ALERT_STORE_PARITY_MATRIX == (
        "append order through raw reads",
        "normalized raw read shape",
        "filtered raw reads and summaries",
        "grouped timelines and incident summaries",
        "known-empty and unknown-session behavior",
        "tolerated malformed-row subset where file corruption has no SQL equivalent",
    )
    assert ALERT_STORE_PARITY_PUBLIC_API == (
        "SessionAlertStore.append_alert()",
        "SessionAlertStore.read_session_alert_events()",
        "session_alerts.read_session_alert_events()",
        "session_alerts.filter_session_alert_events()",
        "session_alerts.summarize_session_alert_events()",
        "session_alert_incidents.build_session_timeline()",
        "session_alert_incidents.build_session_incident_summary()",
    )


@pytest.fixture(
    params=("file", "postgres"),
    ids=("file-store", "postgres-double"),
)
def alert_store_parity_backend(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> AlertStoreParityBackend:
    """Provide one backend-neutral factory for the shared parity matrix."""
    return AlertStoreParityBackend(
        backend=request.param,
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
    )


def _assert_unknown_session_failure(store: SessionAlertStore) -> None:
    """Assert that one store preserves the shared unknown-session read contract."""
    with pytest.raises(SessionAlertsNotFoundError):
        read_session_alert_events("missing-parity-session", store=store)


def _install_active_session_store(
    monkeypatch: pytest.MonkeyPatch,
    *known_session_ids: str,
) -> KnownSessionExistenceStore:
    """Install a session-store spy as the active known-session source."""
    session_store = KnownSessionExistenceStore(*known_session_ids)
    monkeypatch.setattr(
        "session_alert_store.get_default_session_store",
        lambda: session_store,
    )
    return session_store


def test_file_and_postgres_alert_stores_match_raw_read_output_and_append_order(
    alert_store_parity_backend: AlertStoreParityBackend,
) -> None:
    """Raw reads should stay append-ordered and use the shared normalized row shape."""
    session_id = "parity-raw-read"
    store = alert_store_parity_backend.build_store(
        known_session_ids=(session_id,),
        events=(
            build_alert_event(
                session_id,
                timestamp_utc="2026-05-19 12:00:20",
                detector_id="video_metrics",
                title="Persisted first",
                message="Written first even with a later timestamp.",
                severity="warning",
                source_name="segment_0002.ts",
                window_index=7,
                window_start_sec=14.0,
            ),
            build_alert_event(
                session_id,
                timestamp_utc="2026-05-19 12:00:00",
                detector_id="video_metrics",
                title="Persisted second",
                message="Written second even with an earlier timestamp.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
        ),
    )

    alerts = read_session_alert_events(session_id, store=store)

    assert alerts == [
        build_normalized_alert(
            session_id,
            timestamp_utc="2026-05-19 12:00:20",
            detector_id="video_metrics",
            title="Persisted first",
            message="Written first even with a later timestamp.",
            severity="warning",
            source_name="segment_0002.ts",
            window_index=7,
            window_start_sec=14.0,
        ),
        build_normalized_alert(
            session_id,
            timestamp_utc="2026-05-19 12:00:00",
            detector_id="video_metrics",
            title="Persisted second",
            message="Written second even with an earlier timestamp.",
            severity="warning",
            source_name="segment_0001.ts",
        ),
    ]


def test_file_and_postgres_alert_stores_match_known_empty_behavior(
    alert_store_parity_backend: AlertStoreParityBackend,
) -> None:
    """Known sessions without alerts should stay empty across both stores."""
    session_id = "parity-empty-session"
    store = alert_store_parity_backend.build_store(
        known_session_ids=(session_id,),
    )

    alerts = read_session_alert_events(session_id, store=store)

    assert alerts == []


def test_file_and_postgres_alert_stores_match_known_empty_grouped_envelopes(
    alert_store_parity_backend: AlertStoreParityBackend,
) -> None:
    """Known sessions without alerts should keep stable empty timeline and summary shapes."""
    session_id = "parity-empty-grouped-session"
    store = alert_store_parity_backend.build_store(
        known_session_ids=(session_id,),
    )

    assert build_session_timeline(session_id, store=store) == {
        "session_id": session_id,
        "entries": [],
    }
    assert build_session_incident_summary(session_id, store=store) == _empty_incident_summary(
        session_id,
    )


def test_file_and_postgres_alert_stores_match_unknown_session_behavior(
    alert_store_parity_backend: AlertStoreParityBackend,
) -> None:
    """Unknown-session failures should stay aligned across both stores."""
    _assert_unknown_session_failure(alert_store_parity_backend.build_store())


def test_file_and_postgres_alert_services_use_same_known_session_existence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Known empty sessions should stay readable across both alert backends."""
    session_id = "parity-known-empty-via-session-store"
    configure_session_alert_test(monkeypatch, tmp_path)
    session_store = _install_active_session_store(monkeypatch, session_id)
    _mark_known_postgres_sessions(monkeypatch, session_id)

    file_store = FileSessionAlertStore()
    postgres_store = _build_postgres_parity_store()

    assert read_session_alert_events(session_id, store=file_store) == []
    assert read_session_alert_events(session_id, store=postgres_store) == []
    assert session_store.checked_session_ids == [session_id]


def test_file_and_postgres_alert_services_use_same_unknown_session_existence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Unknown sessions should fail the same way across alert backends."""
    session_id = "parity-unknown-via-session-store"
    configure_session_alert_test(monkeypatch, tmp_path)
    session_store = _install_active_session_store(monkeypatch)
    _mark_known_postgres_sessions(monkeypatch)

    file_store = FileSessionAlertStore()
    postgres_store = _build_postgres_parity_store()

    for store in (file_store, postgres_store):
        with pytest.raises(SessionAlertsNotFoundError, match=session_id):
            read_session_alert_events(session_id, store=store)

    assert session_store.checked_session_ids == [session_id]


def test_file_and_postgres_alert_services_match_known_session_alert_payloads(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Known-session reads should expose the same normalized alert payload."""
    session_id = "parity-known-alerts-via-session-store"
    configure_session_alert_test(monkeypatch, tmp_path)
    session_store = _install_active_session_store(monkeypatch, session_id)
    _mark_known_postgres_sessions(monkeypatch, session_id)
    event = build_alert_event(
        session_id,
        timestamp_utc="2026-05-19 12:00:00",
        detector_id="video_metrics",
        title="Shared alert payload",
        message="Both stores should return this alert through the service seam.",
        severity="warning",
        source_name="segment_0001.ts",
    )
    file_store = FileSessionAlertStore()
    postgres_store = _build_postgres_parity_store()
    file_store.append_alert(event)
    postgres_store.append_alert(event)

    assert read_session_alert_events(
        session_id,
        store=file_store,
    ) == read_session_alert_events(
        session_id,
        store=postgres_store,
    ) == [
        build_normalized_alert(
            session_id,
            timestamp_utc="2026-05-19 12:00:00",
            detector_id="video_metrics",
            title="Shared alert payload",
            message="Both stores should return this alert through the service seam.",
            severity="warning",
            source_name="segment_0001.ts",
        )
    ]
    assert session_store.checked_session_ids == [session_id]


def test_file_and_postgres_alert_stores_match_filtered_summary_behavior(
    alert_store_parity_backend: AlertStoreParityBackend,
) -> None:
    """Filtered raw summaries should stay identical across both store backends."""
    session_id = "parity-summary"
    store = alert_store_parity_backend.build_store(
        known_session_ids=(session_id,),
        events=tuple(_filtered_parity_events(session_id)),
    )

    summary = summarize_session_alert_events(
        session_id,
        detector_id="video_metrics",
        severity="warning",
        start_time_utc="2026-05-19 12:00:05",
        end_time_utc="2026-05-19 12:00:25",
        store=store,
    )

    assert summary == {
        "session_id": session_id,
        "total_alerts": 1,
        "counts_by_detector": {"video_metrics": 1},
        "counts_by_severity": {"warning": 1},
        "first_alert_timestamp_utc": "2026-05-19 12:00:20",
        "last_alert_timestamp_utc": "2026-05-19 12:00:20",
    }


def test_file_and_postgres_alert_stores_match_filtered_raw_read_behavior(
    alert_store_parity_backend: AlertStoreParityBackend,
) -> None:
    """Filtered raw reads should stay identical across both store backends."""
    session_id = "parity-filtered-read"
    store = alert_store_parity_backend.build_store(
        known_session_ids=(session_id,),
        events=tuple(_filtered_parity_events(session_id)),
    )

    filtered_alerts = filter_session_alert_events(
        session_id,
        detector_id="video_metrics",
        severity="warning",
        start_time_utc="2026-05-19 12:00:05",
        end_time_utc="2026-05-19 12:00:25",
        store=store,
    )

    assert filtered_alerts == [
        build_normalized_alert(
            session_id,
            timestamp_utc="2026-05-19 12:00:20",
            detector_id="video_metrics",
            title="Late metric warning",
            message="Expected filtered match.",
            severity="warning",
            source_name="segment_0003.ts",
        )
    ]


def test_file_and_postgres_alert_stores_match_grouped_timeline_behavior(
    alert_store_parity_backend: AlertStoreParityBackend,
) -> None:
    """Grouped timeline behavior should stay stable across both stores."""
    session_id = "parity-timeline"
    store = alert_store_parity_backend.build_store(
        known_session_ids=(session_id,),
        events=tuple(_grouped_parity_events(session_id)),
    )

    timeline = build_session_timeline(session_id, store=store)

    assert timeline["entries"] == [
        {
            "start_time_utc": "2026-05-19 12:00:00",
            "end_time_utc": "2026-05-19 12:00:20",
            "detector_id": "video_metrics",
            "severity": "warning",
            "title": "Black screen detected",
            "alert_count": 2,
            "source_names": ["segment_0001.ts", "segment_0002.ts"],
            "sample_message": "First grouped incident row.",
        },
        {
            "start_time_utc": "2026-05-19 12:02:00",
            "end_time_utc": "2026-05-19 12:02:00",
            "detector_id": "video_blur",
            "severity": "info",
            "title": "Blur increased",
            "alert_count": 1,
            "source_names": ["segment_0003.ts"],
            "sample_message": "Second grouped incident.",
        },
    ]


def test_file_and_postgres_alert_stores_match_grouped_incident_summary_behavior(
    alert_store_parity_backend: AlertStoreParityBackend,
) -> None:
    """Grouped incident summaries should stay backend-equivalent."""
    session_id = "parity-incident-summary"
    store = alert_store_parity_backend.build_store(
        known_session_ids=(session_id,),
        events=tuple(_grouped_parity_events(session_id)),
    )

    summary = build_session_incident_summary(session_id, store=store)

    assert summary["total_alerts"] == 3
    assert summary["total_incidents"] == 2
    assert summary["counts_by_detector"] == {
        "video_metrics": 2,
        "video_blur": 1,
    }
    assert summary["counts_by_severity"] == {
        "warning": 2,
        "info": 1,
    }
    assert summary["top_incident_categories"] == {
        "Black screen detected": 1,
        "Blur increased": 1,
    }


def test_file_and_postgres_alert_stores_match_time_bounded_grouped_timeline_behavior(
    alert_store_parity_backend: AlertStoreParityBackend,
) -> None:
    """Time-bounded grouped timelines should stay identical across both backends."""
    session_id = "parity-time-bounded-timeline"
    store = alert_store_parity_backend.build_store(
        known_session_ids=(session_id,),
        events=tuple(_grouped_parity_events(session_id)),
    )

    timeline = build_session_timeline(
        session_id,
        start_time_utc="2026-05-19 12:00:10",
        end_time_utc="2026-05-19 12:01:00",
        store=store,
    )

    assert timeline["entries"] == [
        {
            "start_time_utc": "2026-05-19 12:00:20",
            "end_time_utc": "2026-05-19 12:00:20",
            "detector_id": "video_metrics",
            "severity": "warning",
            "title": "Black screen detected",
            "alert_count": 1,
            "source_names": ["segment_0002.ts"],
            "sample_message": "Second grouped incident row.",
        }
    ]


def test_file_and_postgres_alert_stores_match_time_bounded_grouped_incident_summary_behavior(
    alert_store_parity_backend: AlertStoreParityBackend,
) -> None:
    """Time-bounded grouped summaries should stay identical across both backends."""
    session_id = "parity-time-bounded-incident-summary"
    store = alert_store_parity_backend.build_store(
        known_session_ids=(session_id,),
        events=tuple(_grouped_parity_events(session_id)),
    )

    summary = build_session_incident_summary(
        session_id,
        start_time_utc="2026-05-19 12:00:10",
        end_time_utc="2026-05-19 12:01:00",
        store=store,
    )

    assert summary["total_alerts"] == 1
    assert summary["total_incidents"] == 1
    assert summary["counts_by_detector"] == {"video_metrics": 1}
    assert summary["counts_by_severity"] == {"warning": 1}
    assert summary["top_incident_categories"] == {"Black screen detected": 1}
    assert summary["first_alert_timestamp_utc"] == "2026-05-19 12:00:20"
    assert summary["last_alert_timestamp_utc"] == "2026-05-19 12:00:20"


def test_file_and_postgres_alert_stores_match_filtered_grouped_timeline_behavior(
    alert_store_parity_backend: AlertStoreParityBackend,
) -> None:
    """Filtered grouped timelines should stay identical across both backends."""
    session_id = "parity-filtered-timeline"
    store = alert_store_parity_backend.build_store(
        known_session_ids=(session_id,),
        events=tuple(_filtered_grouped_parity_events(session_id)),
    )

    timeline = build_session_timeline(
        session_id,
        detector_id="video_metrics",
        severity="warning",
        store=store,
    )

    assert timeline["entries"] == [
        {
            "start_time_utc": "2026-05-19 12:10:00",
            "end_time_utc": "2026-05-19 12:10:00",
            "detector_id": "video_metrics",
            "severity": "warning",
            "title": "Black screen detected",
            "alert_count": 1,
            "source_names": ["segment_0101.ts"],
            "sample_message": "Expected grouped filtered result.",
        }
    ]


def test_file_and_postgres_alert_stores_match_filtered_grouped_incident_summary_behavior(
    alert_store_parity_backend: AlertStoreParityBackend,
) -> None:
    """Filtered grouped summaries should stay identical across both backends."""
    session_id = "parity-filtered-incident-summary"
    store = alert_store_parity_backend.build_store(
        known_session_ids=(session_id,),
        events=tuple(_filtered_grouped_parity_events(session_id)),
    )

    summary = build_session_incident_summary(
        session_id,
        detector_id="video_metrics",
        severity="warning",
        store=store,
    )

    assert summary["total_alerts"] == 1
    assert summary["total_incidents"] == 1
    assert summary["counts_by_detector"] == {"video_metrics": 1}
    assert summary["counts_by_severity"] == {"warning": 1}
    assert summary["top_incident_categories"] == {"Black screen detected": 1}
    assert summary["first_alert_timestamp_utc"] == "2026-05-19 12:10:00"
    assert summary["last_alert_timestamp_utc"] == "2026-05-19 12:10:00"


def test_file_and_postgres_alert_stores_match_empty_filtered_incident_results(
    alert_store_parity_backend: AlertStoreParityBackend,
) -> None:
    """Known sessions with non-matching grouped filters should degrade to stable empty values."""
    session_id = "parity-empty-filtered-incidents"
    store = alert_store_parity_backend.build_store(
        known_session_ids=(session_id,),
        events=tuple(_grouped_parity_events(session_id)),
    )

    assert build_session_timeline(
        session_id,
        detector_id="unknown_detector",
        store=store,
    ) == {
        "session_id": session_id,
        "entries": [],
    }
    assert build_session_incident_summary(
        session_id,
        detector_id="unknown_detector",
        store=store,
    ) == _empty_incident_summary(
        session_id,
    )


def test_file_malformed_rows_match_postgres_clean_subset_where_corruption_has_no_equivalent(
    alert_store_parity_backend: AlertStoreParityBackend,
) -> None:
    """File-only malformed rows should collapse to the same valid subset result."""
    session_id = "parity-malformed-subset"
    timestamp_utc = "2026-05-19 12:00:00"
    detector_id = "video_metrics"
    title = "Valid persisted row"
    message = "This row should survive malformed neighbors."
    severity: Literal["warning"] = "warning"
    source_name = "segment_0001.ts"
    valid_event = build_alert_event(
        session_id,
        timestamp_utc=timestamp_utc,
        detector_id=detector_id,
        title=title,
        message=message,
        severity=severity,
        source_name=source_name,
    )
    if alert_store_parity_backend.backend == "file":
        store = alert_store_parity_backend.build_store(
            known_session_ids=(session_id,),
            file_alert_rows_by_session={
                session_id: [
                    build_persisted_alert(
                        session_id,
                        timestamp_utc=timestamp_utc,
                        detector_id=detector_id,
                        title=title,
                        message=message,
                        severity=severity,
                        source_name=source_name,
                    ),
                    "{bad json",
                    build_persisted_alert(
                        session_id,
                        timestamp_utc="2026-05-19 12:00:10",
                        detector_id="",
                        title="Malformed row",
                        message="Missing detector_id makes this row invalid.",
                        severity="warning",
                        source_name="segment_0002.ts",
                    ),
                ]
            },
        )
    else:
        store = alert_store_parity_backend.build_store(
            known_session_ids=(session_id,),
            events=(valid_event,),
        )

    expected_valid_alert = build_normalized_alert(
        session_id,
        timestamp_utc=timestamp_utc,
        detector_id=detector_id,
        title=title,
        message=message,
        severity=severity,
        source_name=source_name,
    )

    assert read_session_alert_events(session_id, store=store) == [expected_valid_alert]
    assert summarize_session_alert_events(session_id, store=store) == {
        "session_id": session_id,
        "total_alerts": 1,
        "counts_by_detector": {detector_id: 1},
        "counts_by_severity": {severity: 1},
        "first_alert_timestamp_utc": timestamp_utc,
        "last_alert_timestamp_utc": timestamp_utc,
    }


def test_file_and_postgres_alert_stores_keep_multiple_sessions_isolated(
    alert_store_parity_backend: AlertStoreParityBackend,
) -> None:
    """Session-scoped reads and summaries should stay isolated across both backends."""
    store = alert_store_parity_backend.build_store(
        known_session_ids=("parity-session-a", "parity-session-b"),
        events=(
            build_alert_event(
                "parity-session-a",
                timestamp_utc="2026-05-19 21:00:00",
                detector_id="video_metrics",
                title="Session A alert",
                message="Only session A should see this.",
                severity="warning",
                source_name="segment_a.ts",
            ),
            build_alert_event(
                "parity-session-b",
                timestamp_utc="2026-05-19 21:00:10",
                detector_id="video_blur",
                title="Session B alert",
                message="Only session B should see this.",
                severity="info",
                source_name="segment_b.ts",
            ),
        ),
    )

    for session_id, expected_title in [
        ("parity-session-a", "Session A alert"),
        ("parity-session-b", "Session B alert"),
    ]:
        assert (
            read_session_alert_events(session_id, store=store)[0]["title"]
            == expected_title
        )
        assert summarize_session_alert_events(session_id, store=store)["total_alerts"] == 1


def test_file_and_postgres_alert_stores_keep_filtered_queries_scoped_to_one_session(
    alert_store_parity_backend: AlertStoreParityBackend,
) -> None:
    """Session-scoped filtered reads and grouped queries should ignore other sessions."""
    session_a = "parity-filtered-session-a"
    session_b = "parity-filtered-session-b"
    store = alert_store_parity_backend.build_store(
        known_session_ids=(session_a, session_b),
        events=(
            build_alert_event(
                session_a,
                timestamp_utc="2026-05-19 22:00:00",
                detector_id="video_metrics",
                title="Session A target incident",
                message="The only warning-level metrics alert for session A.",
                severity="warning",
                source_name="segment_a_0001.ts",
            ),
            build_alert_event(
                session_a,
                timestamp_utc="2026-05-19 22:00:10",
                detector_id="video_metrics",
                title="Session A non-target incident",
                message="Same detector but filtered out by severity.",
                severity="info",
                source_name="segment_a_0002.ts",
            ),
            build_alert_event(
                session_b,
                timestamp_utc="2026-05-19 22:01:00",
                detector_id="video_metrics",
                title="Session B target incident",
                message="Should stay visible only in session B queries.",
                severity="warning",
                source_name="segment_b_0001.ts",
            ),
            build_alert_event(
                session_b,
                timestamp_utc="2026-05-19 22:01:20",
                detector_id="video_blur",
                title="Session B blur incident",
                message="Separate incident category for session B.",
                severity="warning",
                source_name="segment_b_0002.ts",
            ),
        ),
    )

    filtered_alerts = filter_session_alert_events(
        session_a,
        detector_id="video_metrics",
        severity="warning",
        store=store,
    )
    session_b_timeline = build_session_timeline(
        session_b,
        detector_id="video_metrics",
        severity="warning",
        store=store,
    )

    assert filtered_alerts == [
        build_normalized_alert(
            session_a,
            timestamp_utc="2026-05-19 22:00:00",
            detector_id="video_metrics",
            title="Session A target incident",
            message="The only warning-level metrics alert for session A.",
            severity="warning",
            source_name="segment_a_0001.ts",
        )
    ]
    assert session_b_timeline["entries"] == [
        {
            "start_time_utc": "2026-05-19 22:01:00",
            "end_time_utc": "2026-05-19 22:01:00",
            "detector_id": "video_metrics",
            "severity": "warning",
            "title": "Session B target incident",
            "alert_count": 1,
            "source_names": ["segment_b_0001.ts"],
            "sample_message": "Should stay visible only in session B queries.",
        }
    ]
