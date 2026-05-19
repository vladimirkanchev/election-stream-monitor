"""Parity tests shared by the file-backed and PostgreSQL alert stores.

These tests keep the comparison narrow: both stores get the same validated
events, shared readers go through the same seam, and backend-specific
corruption behavior stays outside the parity matrix.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Literal, TypeVar

import pytest

from session_alert_incidents import (
    AlertTimelinePayload,
    IncidentSummaryPayload,
    build_session_incident_summary,
    build_session_timeline,
)
from session_alert_store import (
    AlertEventPayload,
    FileSessionAlertStore,
    SessionAlertsNotFoundError,
    SessionAlertStore,
)
from session_alert_store_postgres import (
    POSTGRES_ALERT_EVENTS_INSERT_SQL,
    POSTGRES_ALERT_EVENTS_READ_SQL,
    POSTGRES_ALERT_TIMESTAMP_FORMAT,
    PostgresSessionAlertStore,
)
from session_alerts import (
    AlertSummaryPayload,
    read_session_alert_events,
    summarize_session_alert_events,
)
from session_models import AlertEvent
from tests.session_alert_test_support import (
    build_alert_event,
    build_normalized_alert,
    build_persisted_alert,
    configure_session_alert_test,
    write_known_session,
)

ParityResult = TypeVar(
    "ParityResult",
    list[AlertEventPayload],
    AlertSummaryPayload,
    AlertTimelinePayload,
    IncidentSummaryPayload,
)


class InMemoryPostgresParityCursor:
    """Tiny cursor that simulates only the SQL used by the alert store seam."""

    def __init__(self, connection: "InMemoryPostgresParityConnection") -> None:
        self._connection = connection
        self._rows: list[tuple[object, ...]] = []

    def __enter__(self) -> "InMemoryPostgresParityCursor":
        """Return the same cursor inside the context manager block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        """Close the synthetic cursor without extra cleanup work."""

    def execute(self, query: str, params: object | None = None) -> object:
        """Handle the two SQL operations used by the concrete Postgres store."""
        if query == POSTGRES_ALERT_EVENTS_INSERT_SQL:
            assert isinstance(params, tuple)
            self._connection.append_inserted_row(params)
            return object()
        if query == POSTGRES_ALERT_EVENTS_READ_SQL:
            assert isinstance(params, tuple)
            assert len(params) == 1
            session_id = params[0]
            assert isinstance(session_id, str)
            self._rows = self._connection.read_rows_for_session(session_id)
            return object()
        raise AssertionError(f"Unexpected SQL in parity test: {query}")

    def fetchall(self) -> list[object]:
        """Return the stored read result for the current session query."""
        return list(self._rows)


class InMemoryPostgresParityConnection:
    """Minimal in-memory connection for backend parity tests."""

    def __init__(self) -> None:
        self._rows: list[tuple[object, ...]] = []
        self.commit_count = 0

    def cursor(self) -> InMemoryPostgresParityCursor:
        """Return a cursor over the shared in-memory alert-row list."""
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
class StorePair:
    """Stable backend pair used by the shared parity assertions."""

    session_id: str
    file_store: SessionAlertStore
    postgres_store: SessionAlertStore


def _mark_known_postgres_sessions(
    monkeypatch: pytest.MonkeyPatch,
    *session_ids: str,
) -> None:
    """Patch Postgres session existence for alert-only parity tests."""
    known_sessions = set(session_ids)
    monkeypatch.setattr(
        "session_alert_store_postgres.session_exists",
        lambda candidate_session_id: candidate_session_id in known_sessions,
    )


def _build_postgres_parity_store() -> PostgresSessionAlertStore:
    """Build the in-memory Postgres store used across the parity matrix."""
    return PostgresSessionAlertStore(InMemoryPostgresParityConnection())


def _build_store_pair(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    session_id: str,
    events: list[AlertEvent],
) -> StorePair:
    """Seed both backends with the same known session and alert history."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, session_id)
    _mark_known_postgres_sessions(monkeypatch, session_id)

    file_store = FileSessionAlertStore()
    postgres_store = _build_postgres_parity_store()
    for event in events:
        file_store.append_alert(event)
        postgres_store.append_alert(event)

    return StorePair(
        session_id=session_id,
        file_store=file_store,
        postgres_store=postgres_store,
    )


def _assert_store_pair_parity(
    pair: StorePair,
    read: Callable[[SessionAlertStore], ParityResult],
) -> ParityResult:
    """Assert that both stores produce the same result through one seam reader."""
    file_result = read(pair.file_store)
    postgres_result = read(pair.postgres_store)
    assert postgres_result == file_result
    return file_result


def _assert_unknown_session_failure(store: SessionAlertStore) -> None:
    """Assert that one store preserves the shared unknown-session read contract."""
    with pytest.raises(SessionAlertsNotFoundError):
        read_session_alert_events("missing-parity-session", store=store)


def test_file_and_postgres_alert_stores_match_raw_read_output_and_append_order(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Raw reads should stay append-ordered and backend-equivalent."""
    pair = _build_store_pair(
        monkeypatch,
        tmp_path,
        session_id="parity-raw-read",
        events=[
            build_alert_event(
                "parity-raw-read",
                timestamp_utc="2026-05-19 12:00:20",
                detector_id="video_metrics",
                title="Persisted first",
                message="Written first even with a later timestamp.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_alert_event(
                "parity-raw-read",
                timestamp_utc="2026-05-19 12:00:00",
                detector_id="video_metrics",
                title="Persisted second",
                message="Written second even with an earlier timestamp.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
        ],
    )

    alerts = _assert_store_pair_parity(
        pair,
        lambda store: read_session_alert_events(pair.session_id, store=store),
    )

    assert [alert["title"] for alert in alerts] == [
        "Persisted first",
        "Persisted second",
    ]


def test_file_and_postgres_alert_stores_match_known_empty_behavior(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Known sessions without alerts should stay empty across both stores."""
    pair = _build_store_pair(
        monkeypatch,
        tmp_path,
        session_id="parity-empty-session",
        events=[],
    )

    alerts = _assert_store_pair_parity(
        pair,
        lambda store: read_session_alert_events(pair.session_id, store=store),
    )

    assert alerts == []


def test_file_and_postgres_alert_stores_match_unknown_session_behavior(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Unknown-session failures should stay aligned across both stores."""
    configure_session_alert_test(monkeypatch, tmp_path)
    _mark_known_postgres_sessions(monkeypatch)

    file_store = FileSessionAlertStore()
    postgres_store = _build_postgres_parity_store()

    _assert_unknown_session_failure(file_store)
    _assert_unknown_session_failure(postgres_store)


def test_file_and_postgres_alert_stores_match_filtered_summary_behavior(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Filtered raw summaries should stay identical across both store backends."""
    pair = _build_store_pair(
        monkeypatch,
        tmp_path,
        session_id="parity-summary",
        events=[
            build_alert_event(
                "parity-summary",
                timestamp_utc="2026-05-19 12:00:00",
                detector_id="video_metrics",
                title="Early metric warning",
                message="Outside the requested time window.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_alert_event(
                "parity-summary",
                timestamp_utc="2026-05-19 12:00:10",
                detector_id="video_blur",
                title="Blur info",
                message="Wrong detector for the filtered summary.",
                severity="info",
                source_name="segment_0002.ts",
            ),
            build_alert_event(
                "parity-summary",
                timestamp_utc="2026-05-19 12:00:20",
                detector_id="video_metrics",
                title="Late metric warning",
                message="Expected filtered match.",
                severity="warning",
                source_name="segment_0003.ts",
            ),
        ],
    )

    summary = _assert_store_pair_parity(
        pair,
        lambda store: summarize_session_alert_events(
            pair.session_id,
            detector_id="video_metrics",
            severity="warning",
            start_time_utc="2026-05-19 12:00:05",
            end_time_utc="2026-05-19 12:00:25",
            store=store,
        ),
    )

    assert summary == {
        "session_id": "parity-summary",
        "total_alerts": 1,
        "counts_by_detector": {"video_metrics": 1},
        "counts_by_severity": {"warning": 1},
        "first_alert_timestamp_utc": "2026-05-19 12:00:20",
        "last_alert_timestamp_utc": "2026-05-19 12:00:20",
    }


def test_file_and_postgres_alert_stores_match_grouped_timeline_behavior(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Grouped timeline behavior should stay stable across both stores."""
    pair = _build_store_pair(
        monkeypatch,
        tmp_path,
        session_id="parity-timeline",
        events=[
            build_alert_event(
                "parity-timeline",
                timestamp_utc="2026-05-19 12:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First alert in the incident.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_alert_event(
                "parity-timeline",
                timestamp_utc="2026-05-19 12:00:20",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Second alert in the incident.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_alert_event(
                "parity-timeline",
                timestamp_utc="2026-05-19 12:02:00",
                detector_id="video_blur",
                title="Blur increased",
                message="New incident after the grouping gap.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ],
    )

    timeline = _assert_store_pair_parity(
        pair,
        lambda store: build_session_timeline(pair.session_id, store=store),
    )

    assert timeline["entries"] == [
        {
            "start_time_utc": "2026-05-19 12:00:00",
            "end_time_utc": "2026-05-19 12:00:20",
            "detector_id": "video_metrics",
            "severity": "warning",
            "title": "Black screen detected",
            "alert_count": 2,
            "source_names": ["segment_0001.ts", "segment_0002.ts"],
            "sample_message": "First alert in the incident.",
        },
        {
            "start_time_utc": "2026-05-19 12:02:00",
            "end_time_utc": "2026-05-19 12:02:00",
            "detector_id": "video_blur",
            "severity": "info",
            "title": "Blur increased",
            "alert_count": 1,
            "source_names": ["segment_0003.ts"],
            "sample_message": "New incident after the grouping gap.",
        },
    ]


def test_file_and_postgres_alert_stores_match_grouped_incident_summary_behavior(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Grouped incident summaries should stay backend-equivalent."""
    pair = _build_store_pair(
        monkeypatch,
        tmp_path,
        session_id="parity-incident-summary",
        events=[
            build_alert_event(
                "parity-incident-summary",
                timestamp_utc="2026-05-19 12:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First grouped incident.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_alert_event(
                "parity-incident-summary",
                timestamp_utc="2026-05-19 12:00:10",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Still the first grouped incident.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_alert_event(
                "parity-incident-summary",
                timestamp_utc="2026-05-19 12:02:00",
                detector_id="video_blur",
                title="Blur increased",
                message="Second grouped incident.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ],
    )

    summary = _assert_store_pair_parity(
        pair,
        lambda store: build_session_incident_summary(pair.session_id, store=store),
    )

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


def test_file_malformed_rows_match_postgres_clean_subset_where_corruption_has_no_equivalent(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """File-only malformed rows should collapse to the same valid subset result."""
    session_id = "parity-malformed-subset"
    timestamp_utc = "2026-05-19 12:00:00"
    detector_id = "video_metrics"
    title = "Valid persisted row"
    message = "This row should survive malformed neighbors."
    severity: Literal["warning"] = "warning"
    source_name = "segment_0001.ts"
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        session_id,
        alert_rows=[
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
        ],
    )
    _mark_known_postgres_sessions(monkeypatch, session_id)

    file_store = FileSessionAlertStore()
    postgres_store = _build_postgres_parity_store()
    expected_valid_alert = build_normalized_alert(
        session_id,
        timestamp_utc=timestamp_utc,
        detector_id=detector_id,
        title=title,
        message=message,
        severity=severity,
        source_name=source_name,
    )
    postgres_store.append_alert(
        build_alert_event(
            session_id,
            timestamp_utc=timestamp_utc,
            detector_id=detector_id,
            title=title,
            message=message,
            severity=severity,
            source_name=source_name,
        )
    )

    assert read_session_alert_events(
        session_id,
        store=file_store,
    ) == read_session_alert_events(
        session_id,
        store=postgres_store,
    ) == [expected_valid_alert]

    assert summarize_session_alert_events(
        session_id,
        store=file_store,
    ) == summarize_session_alert_events(
        session_id,
        store=postgres_store,
    )


def test_file_and_postgres_alert_stores_keep_multiple_sessions_isolated(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Session-scoped reads and summaries should stay isolated across both backends."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "parity-session-a")
    write_known_session(session_root, "parity-session-b")
    _mark_known_postgres_sessions(monkeypatch, "parity-session-a", "parity-session-b")

    file_store = FileSessionAlertStore()
    postgres_store = _build_postgres_parity_store()
    for event in [
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
    ]:
        file_store.append_alert(event)
        postgres_store.append_alert(event)

    for session_id, expected_title in [
        ("parity-session-a", "Session A alert"),
        ("parity-session-b", "Session B alert"),
    ]:
        assert read_session_alert_events(session_id, store=file_store) == read_session_alert_events(
            session_id,
            store=postgres_store,
        )
        assert summarize_session_alert_events(
            session_id,
            store=file_store,
        ) == summarize_session_alert_events(
            session_id,
            store=postgres_store,
        )
        assert read_session_alert_events(session_id, store=file_store)[0]["title"] == expected_title
