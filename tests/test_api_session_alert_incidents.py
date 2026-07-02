"""FastAPI boundary tests for grouped alert routes.

This file owns grouped timeline and incident-summary route behavior, including
payload shaping, filter binding, runtime-selected backend wiring, and the
small opt-in live Postgres smokes for the grouped HTTP surface.
"""

from collections.abc import Iterator
from typing import cast

import pytest

from session_alert_store import (
    AlertEventPayload,
    clear_default_session_alert_store_cache,
)
from session_alerts import SessionAlertsNotFoundError
from session_models import AlertEvent
from tests.api_alert_test_support import (
    assert_request_validation_payload,
    build_internal_error_payload,
    build_session_not_found_payload,
    build_validation_error_payload,
)
from tests.api_boundary_test_support import request
from tests.mcp_alert_test_support import call_mcp_tool
from tests.mcp_server_incidents_test_support import assert_mcp_tool_success
from tests.session_alert_test_support import (
    AlertLogRow,
    FailingReadAlertStore,
    REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    StaticAlertStore,
    build_alert_event,
    build_live_runtime_postgres_store,
    build_normalized_alert,
    build_unique_session_id,
    close_store_if_possible,
    build_persisted_alert,
    build_incident_summary_payload,
    build_timeline_entry,
    configure_session_alert_test,
    install_runtime_postgres_bootstrap_failure,
    select_runtime_postgres_store,
    write_alert_log,
    write_known_session,
)


@pytest.fixture(autouse=True)
def _clear_default_alert_store_cache() -> Iterator[None]:
    """Keep runtime-selected default-store caching isolated in grouped route tests."""
    clear_default_session_alert_store_cache()
    yield
    clear_default_session_alert_store_cache()


def _write_real_grouped_alert_session(
    monkeypatch,
    tmp_path,
    *,
    session_id: str,
    alert_rows: list[AlertLogRow],
) -> None:
    """Persist one real grouped-alert session for the shared boundary checks."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, session_id, alert_rows=alert_rows)


def _expected_incident_summary_with_runtime_narrative(
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
) -> dict[str, object]:
    """Build one grouped summary while preserving the runtime narrative sentence."""
    return cast(
        dict[str, object],
        build_incident_summary_payload(
            session_id,
            total_alerts=total_alerts,
            total_incidents=total_incidents,
            counts_by_detector=counts_by_detector,
            counts_by_severity=counts_by_severity,
            top_incident_categories=top_incident_categories,
            first_alert_timestamp_utc=first_alert_timestamp_utc,
            last_alert_timestamp_utc=last_alert_timestamp_utc,
            narrative_summary=narrative_summary,
        ),
    )


def _empty_timeline_payload(session_id: str) -> dict[str, object]:
    """Return the stable empty grouped-timeline payload for one session."""
    return {
        "session_id": session_id,
        "entries": [],
    }


def _empty_incident_summary_payload(session_id: str) -> dict[str, object]:
    """Return the stable empty grouped incident-summary payload for one session."""
    return cast(
        dict[str, object],
        build_incident_summary_payload(
            session_id,
            total_alerts=0,
            total_incidents=0,
            counts_by_detector={},
            counts_by_severity={},
            top_incident_categories={},
            first_alert_timestamp_utc=None,
            last_alert_timestamp_utc=None,
            narrative_summary=f"Session {session_id} had no alerts.",
        ),
    )


def _runtime_grouped_postgres_alerts(session_id: str) -> list[AlertEventPayload]:
    """Return one stable grouped-alert set for runtime-selected grouped-route checks."""
    return [
        build_normalized_alert(
            session_id,
            timestamp_utc="2026-05-19 19:10:00",
            detector_id="video_metrics",
            title="Black screen detected",
            message="First grouped runtime alert.",
            severity="warning",
            source_name="segment_0001.ts",
        ),
        build_normalized_alert(
            session_id,
            timestamp_utc="2026-05-19 19:10:20",
            detector_id="video_metrics",
            title="Black screen detected",
            message="Second grouped runtime alert.",
            severity="warning",
            source_name="segment_0002.ts",
        ),
    ]


def _runtime_filtered_grouped_postgres_alerts(
    session_id: str,
) -> list[AlertEventPayload]:
    """Return one grouped alert set with exactly one detector/severity filter match."""
    return [
        build_normalized_alert(
            session_id,
            timestamp_utc="2026-05-19 19:20:00",
            detector_id="video_metrics",
            title="Black screen detected",
            message="Expected grouped filtered result.",
            severity="warning",
            source_name="segment_0101.ts",
        ),
        build_normalized_alert(
            session_id,
            timestamp_utc="2026-05-19 19:20:10",
            detector_id="video_metrics",
            title="Black screen detected",
            message="Wrong severity for the grouped filter.",
            severity="info",
            source_name="segment_0102.ts",
        ),
        build_normalized_alert(
            session_id,
            timestamp_utc="2026-05-19 19:20:20",
            detector_id="video_blur",
            title="Blur increased",
            message="Wrong detector for the grouped filter.",
            severity="warning",
            source_name="segment_0103.ts",
        ),
    ]


def _runtime_filtered_grouped_postgres_events(session_id: str) -> list[AlertEvent]:
    """Return live grouped alert events for the filtered Postgres route smoke."""
    return [
        build_alert_event(
            session_id,
            timestamp_utc="2026-05-19 19:20:00",
            detector_id="video_metrics",
            title="Black screen detected",
            message="Expected grouped filtered result.",
            severity="warning",
            source_name="segment_0101.ts",
        ),
        build_alert_event(
            session_id,
            timestamp_utc="2026-05-19 19:20:10",
            detector_id="video_metrics",
            title="Black screen detected",
            message="Wrong severity for the grouped filter.",
            severity="info",
            source_name="segment_0102.ts",
        ),
        build_alert_event(
            session_id,
            timestamp_utc="2026-05-19 19:20:20",
            detector_id="video_blur",
            title="Blur increased",
            message="Wrong detector for the grouped filter.",
            severity="warning",
            source_name="segment_0103.ts",
        ),
    ]


def _single_incident_timeline_payload(
    session_id: str,
    *,
    start_time_utc: str,
    end_time_utc: str,
    source_names: list[str],
    sample_message: str,
    alert_count: int = 2,
) -> dict[str, object]:
    """Return one grouped timeline payload for a single merged incident."""
    return {
        "session_id": session_id,
        "entries": [
            build_timeline_entry(
                start_time_utc=start_time_utc,
                end_time_utc=end_time_utc,
                detector_id="video_metrics",
                severity="warning",
                title="Black screen detected",
                alert_count=alert_count,
                source_names=source_names,
                sample_message=sample_message,
            )
        ],
    }


def _single_incident_summary_with_runtime_narrative(
    session_id: str,
    *,
    first_alert_timestamp_utc: str,
    last_alert_timestamp_utc: str,
    narrative_summary: str,
) -> dict[str, object]:
    """Return one grouped summary payload for a single merged incident."""
    return _expected_incident_summary_with_runtime_narrative(
        session_id,
        total_alerts=2,
        total_incidents=1,
        counts_by_detector={"video_metrics": 2},
        counts_by_severity={"warning": 2},
        top_incident_categories={"Black screen detected": 1},
        first_alert_timestamp_utc=first_alert_timestamp_utc,
        last_alert_timestamp_utc=last_alert_timestamp_utc,
        narrative_summary=narrative_summary,
    )


def _single_filtered_incident_timeline_payload(session_id: str) -> dict[str, object]:
    """Return one grouped timeline payload for the filtered single-alert incident."""
    return _single_incident_timeline_payload(
        session_id,
        start_time_utc="2026-05-19 19:20:00",
        end_time_utc="2026-05-19 19:20:00",
        source_names=["segment_0101.ts"],
        sample_message="Expected grouped filtered result.",
        alert_count=1,
    )


def _single_filtered_incident_summary_with_runtime_narrative(
    session_id: str,
    *,
    narrative_summary: str,
) -> dict[str, object]:
    """Return one grouped summary payload for a filtered single-alert incident."""
    return _expected_incident_summary_with_runtime_narrative(
        session_id,
        total_alerts=1,
        total_incidents=1,
        counts_by_detector={"video_metrics": 1},
        counts_by_severity={"warning": 1},
        top_incident_categories={"Black screen detected": 1},
        first_alert_timestamp_utc="2026-05-19 19:20:00",
        last_alert_timestamp_utc="2026-05-19 19:20:00",
        narrative_summary=narrative_summary,
    )


# Happy-path adapter behavior


def test_get_session_alert_timeline_returns_grouped_response(monkeypatch) -> None:
    """The timeline route should stay a thin adapter over the shared incident service."""

    def fake_build_session_timeline(
        session_id: str,
        *,
        detector_id: str | None = None,
        severity: str | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> dict[str, object]:
        assert session_id == "session-123"
        assert detector_id == "video_metrics"
        assert severity == "warning"
        assert start_time_utc == "2026-05-06 10:00:00"
        assert end_time_utc == "2026-05-06 10:05:00"
        return {
            "session_id": session_id,
            "entries": [
                build_timeline_entry(
                    start_time_utc="2026-05-06 10:00:10",
                    end_time_utc="2026-05-06 10:00:30",
                    detector_id="video_metrics",
                    severity="warning",
                    title="Black screen detected",
                    alert_count=1,
                    source_names=["segment_0001.ts"],
                    sample_message="Black segment.",
                )
            ],
        }

    monkeypatch.setattr(
        "api.routers.alerts.build_session_timeline",
        fake_build_session_timeline,
    )

    response = request(
        "GET",
        (
            "/sessions/session-123/alerts/timeline"
            "?detector_id=video_metrics"
            "&severity=warning"
            "&start_time_utc=2026-05-06%2010:00:00"
            "&end_time_utc=2026-05-06%2010:05:00"
        ),
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "session-123",
        "entries": [
            build_timeline_entry(
                start_time_utc="2026-05-06 10:00:10",
                end_time_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                severity="warning",
                title="Black screen detected",
                alert_count=1,
                source_names=["segment_0001.ts"],
                sample_message="Black segment.",
            )
        ],
    }


def test_get_session_alert_incident_summary_returns_grouped_summary(monkeypatch) -> None:
    """The incident-summary route should forward filters and preserve structured output."""

    def fake_build_session_incident_summary(
        session_id: str,
        *,
        detector_id: str | None = None,
        severity: str | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> dict[str, object]:
        assert session_id == "session-123"
        assert detector_id == "video_metrics"
        assert severity == "warning"
        assert start_time_utc == "2026-05-06 10:00:00"
        assert end_time_utc == "2026-05-06 10:05:00"
        return cast(
            dict[str, object],
            build_incident_summary_payload(
                session_id,
                total_alerts=1,
                total_incidents=1,
                counts_by_detector={"video_metrics": 1},
                counts_by_severity={"warning": 1},
                top_incident_categories={"Black screen detected": 1},
                first_alert_timestamp_utc="2026-05-06 10:00:10",
                last_alert_timestamp_utc="2026-05-06 10:00:10",
                narrative_summary="Session session-123 had 1 grouped incidents across 1 alerts.",
            ),
        )

    monkeypatch.setattr(
        "api.routers.alerts.build_session_incident_summary",
        fake_build_session_incident_summary,
    )

    response = request(
        "GET",
        (
            "/sessions/session-123/alerts/incident-summary"
            "?detector_id=video_metrics"
            "&severity=warning"
            "&start_time_utc=2026-05-06%2010:00:00"
            "&end_time_utc=2026-05-06%2010:05:00"
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == build_incident_summary_payload(
        "session-123",
        total_alerts=1,
        total_incidents=1,
        counts_by_detector={"video_metrics": 1},
        counts_by_severity={"warning": 1},
        top_incident_categories={"Black screen detected": 1},
        first_alert_timestamp_utc="2026-05-06 10:00:10",
        last_alert_timestamp_utc="2026-05-06 10:00:10",
        narrative_summary=payload["narrative_summary"],
    )


def test_get_session_alert_timeline_returns_stable_empty_payload(monkeypatch) -> None:
    """The grouped timeline route should preserve its top-level keys when no incidents exist."""

    def fake_build_session_timeline(
        session_id: str,
        **_: object,
    ) -> dict[str, object]:
        assert session_id == "empty-session"
        return _empty_timeline_payload(session_id)

    monkeypatch.setattr(
        "api.routers.alerts.build_session_timeline",
        fake_build_session_timeline,
    )

    response = request("GET", "/sessions/empty-session/alerts/timeline")

    assert response.status_code == 200
    assert response.json() == _empty_timeline_payload("empty-session")


def test_get_session_alert_incident_summary_returns_stable_empty_payload(
    monkeypatch,
) -> None:
    """The grouped incident summary route should keep all summary keys for empty results."""

    def fake_build_session_incident_summary(
        session_id: str,
        **_: object,
    ) -> dict[str, object]:
        assert session_id == "empty-session"
        return _empty_incident_summary_payload(session_id)

    monkeypatch.setattr(
        "api.routers.alerts.build_session_incident_summary",
        fake_build_session_incident_summary,
    )

    response = request("GET", "/sessions/empty-session/alerts/incident-summary")

    assert response.status_code == 200
    assert response.json() == _empty_incident_summary_payload("empty-session")


def test_get_session_alert_timeline_reads_the_real_file_backed_seam(
    monkeypatch,
    tmp_path,
) -> None:
    """The grouped timeline route should work over real persisted alert files."""
    _write_real_grouped_alert_session(
        monkeypatch,
        tmp_path,
        session_id="session-real-timeline",
        alert_rows=[
            build_persisted_alert(
                "session-real-timeline",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First grouped row.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-real-timeline",
                timestamp_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Second grouped row in the same incident.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
        ],
    )

    response = request("GET", "/sessions/session-real-timeline/alerts/timeline")

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "session-real-timeline",
        "entries": [
            build_timeline_entry(
                start_time_utc="2026-05-06 10:00:00",
                end_time_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                severity="warning",
                title="Black screen detected",
                alert_count=2,
                source_names=["segment_0001.ts", "segment_0002.ts"],
                sample_message="First grouped row.",
            )
        ],
    }


def test_get_session_alert_incident_summary_reads_the_real_file_backed_seam(
    monkeypatch,
    tmp_path,
) -> None:
    """The grouped summary route should work over the real persisted alert seam."""
    _write_real_grouped_alert_session(
        monkeypatch,
        tmp_path,
        session_id="session-real-incident-summary",
        alert_rows=[
            build_persisted_alert(
                "session-real-incident-summary",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First grouped row.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            build_persisted_alert(
                "session-real-incident-summary",
                timestamp_utc="2026-05-06 10:00:30",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Second grouped row in the same incident.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
            build_persisted_alert(
                "session-real-incident-summary",
                timestamp_utc="2026-05-06 10:02:00",
                detector_id="video_blur",
                title="Blur increased",
                message="Separate grouped incident.",
                severity="info",
                source_name="segment_0003.ts",
            ),
        ],
    )

    response = request(
        "GET",
        "/sessions/session-real-incident-summary/alerts/incident-summary",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == _expected_incident_summary_with_runtime_narrative(
        "session-real-incident-summary",
        total_alerts=3,
        total_incidents=2,
        counts_by_detector={"video_metrics": 2, "video_blur": 1},
        counts_by_severity={"warning": 2, "info": 1},
        top_incident_categories={"Black screen detected": 1, "Blur increased": 1},
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:02:00",
        narrative_summary=payload["narrative_summary"],
    )


@pytest.mark.parametrize(
    "route_path",
    [
        "/sessions/missing-real-grouped-alert-session/alerts/timeline",
        "/sessions/missing-real-grouped-alert-session/alerts/incident-summary",
    ],
)
def test_grouped_alert_routes_return_404_for_real_missing_sessions(
    monkeypatch,
    tmp_path,
    route_path: str,
) -> None:
    """Grouped alert routes should map real missing sessions to the public 404 shape."""
    configure_session_alert_test(monkeypatch, tmp_path)

    response = request("GET", route_path)

    assert response.status_code == 404
    assert response.json() == build_session_not_found_payload(
        "missing-real-grouped-alert-session"
    )


@pytest.mark.parametrize(
    ("session_id", "route_path", "expected_kind"),
    [
        (
            "session-runtime-postgres-api-incidents",
            "/sessions/session-runtime-postgres-api-incidents/alerts/incident-summary",
            "incident-summary",
        ),
        (
            "session-runtime-postgres-api-timeline",
            "/sessions/session-runtime-postgres-api-timeline/alerts/timeline",
            "timeline",
        ),
    ],
)
def test_grouped_fastapi_routes_use_runtime_selected_postgres_backend(
    monkeypatch,
    session_id: str,
    route_path: str,
    expected_kind: str,
) -> None:
    """Grouped FastAPI routes should honor runtime-selected Postgres without caller churn."""
    select_runtime_postgres_store(
        monkeypatch,
        StaticAlertStore(session_id, _runtime_grouped_postgres_alerts(session_id)),
    )

    response = request("GET", route_path)

    assert response.status_code == 200
    payload = response.json()

    if expected_kind == "incident-summary":
        assert payload == _single_incident_summary_with_runtime_narrative(
            session_id,
            first_alert_timestamp_utc="2026-05-19 19:10:00",
            last_alert_timestamp_utc="2026-05-19 19:10:20",
            narrative_summary=payload["narrative_summary"],
        )
        return

    assert payload == _single_incident_timeline_payload(
        session_id,
        start_time_utc="2026-05-19 19:10:00",
        end_time_utc="2026-05-19 19:10:20",
        source_names=["segment_0001.ts", "segment_0002.ts"],
        sample_message="First grouped runtime alert.",
    )


@pytest.mark.parametrize(
    ("session_id", "route_path", "expected_kind"),
    [
        (
            "session-runtime-postgres-api-filtered-incidents",
            (
                "/sessions/session-runtime-postgres-api-filtered-incidents/"
                "alerts/incident-summary?detector_id=video_metrics&severity=warning"
            ),
            "incident-summary",
        ),
        (
            "session-runtime-postgres-api-filtered-timeline",
            (
                "/sessions/session-runtime-postgres-api-filtered-timeline/"
                "alerts/timeline?detector_id=video_metrics&severity=warning"
            ),
            "timeline",
        ),
    ],
)
def test_grouped_fastapi_routes_preserve_filtered_results_in_runtime_selected_postgres_mode(
    monkeypatch,
    session_id: str,
    route_path: str,
    expected_kind: str,
) -> None:
    """Grouped FastAPI routes should keep filtered results stable in Postgres mode."""
    select_runtime_postgres_store(
        monkeypatch,
        StaticAlertStore(session_id, _runtime_filtered_grouped_postgres_alerts(session_id)),
    )

    response = request("GET", route_path)

    assert response.status_code == 200
    payload = response.json()
    if expected_kind == "incident-summary":
        assert payload == _single_filtered_incident_summary_with_runtime_narrative(
            session_id,
            narrative_summary=payload["narrative_summary"],
        )
        return

    assert payload == _single_filtered_incident_timeline_payload(session_id)


@pytest.mark.parametrize(
    ("session_id", "route_path"),
    [
        (
            "session-runtime-postgres-grouped-read-error",
            "/sessions/session-runtime-postgres-grouped-read-error/alerts/timeline",
        ),
        (
            "session-runtime-postgres-grouped-summary-read-error",
            (
                "/sessions/session-runtime-postgres-grouped-summary-read-error/"
                "alerts/incident-summary"
            ),
        ),
    ],
)
def test_grouped_fastapi_routes_return_internal_error_when_runtime_postgres_read_fails_after_startup(
    monkeypatch,
    session_id: str,
    route_path: str,
) -> None:
    """Grouped FastAPI routes should surface post-startup Postgres read failures clearly."""
    select_runtime_postgres_store(
        monkeypatch,
        FailingReadAlertStore(
            session_id,
            "database grouped read failed",
        ),
    )

    response = request("GET", route_path)

    assert response.status_code == 500
    assert response.json() == build_internal_error_payload(
        "database grouped read failed"
    )


@pytest.mark.parametrize(
    "route_path",
    [
        "/sessions/session-runtime-postgres-grouped-bootstrap-error/alerts/timeline",
        (
            "/sessions/session-runtime-postgres-grouped-bootstrap-error/"
            "alerts/incident-summary"
        ),
    ],
)
def test_grouped_fastapi_routes_keep_the_same_bootstrap_failure_envelope(
    monkeypatch,
    route_path: str,
) -> None:
    """Grouped FastAPI routes should share the same bootstrap-failure 500 envelope."""
    install_runtime_postgres_bootstrap_failure(monkeypatch)

    response = request("GET", route_path)

    assert response.status_code == 500
    assert response.json() == build_internal_error_payload("postgres bootstrap failed")


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL grouped alert-route smoke test is opt-in.",
)
def test_live_runtime_postgres_grouped_routes_follow_actual_startup_path(
    monkeypatch,
    tmp_path,
) -> None:
    """Representative opt-in public-surface smoke for runtime-selected Postgres routes."""
    session_id = build_unique_session_id("session-runtime-postgres-api-incidents-live")
    store = build_live_runtime_postgres_store(
        monkeypatch,
        tmp_path,
        session_id=session_id,
    )
    try:
        store.append_alert(
            build_alert_event(
                session_id,
                timestamp_utc="2026-05-19 21:10:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="First live grouped alert.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        )
        store.append_alert(
            build_alert_event(
                session_id,
                timestamp_utc="2026-05-19 21:10:20",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Second live grouped alert.",
                severity="warning",
                source_name="segment_0002.ts",
            )
        )

        timeline_response = request("GET", f"/sessions/{session_id}/alerts/timeline")
        summary_response = request(
            "GET",
            f"/sessions/{session_id}/alerts/incident-summary",
        )
    finally:
        close_store_if_possible(store)

    assert timeline_response.status_code == 200
    assert timeline_response.json() == _single_incident_timeline_payload(
        session_id,
        start_time_utc="2026-05-19 21:10:00",
        end_time_utc="2026-05-19 21:10:20",
        source_names=["segment_0001.ts", "segment_0002.ts"],
        sample_message="First live grouped alert.",
    )
    assert summary_response.status_code == 200
    payload = summary_response.json()
    assert payload == _single_incident_summary_with_runtime_narrative(
        session_id,
        first_alert_timestamp_utc="2026-05-19 21:10:00",
        last_alert_timestamp_utc="2026-05-19 21:10:20",
        narrative_summary=payload["narrative_summary"],
    )


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL grouped alert-route smoke test is opt-in.",
)
def test_live_runtime_postgres_grouped_routes_handle_optional_window_fields(
    monkeypatch,
    tmp_path,
) -> None:
    """Grouped live Postgres reads should stay stable when alert rows mix optional window fields."""
    session_id = build_unique_session_id(
        "session-runtime-postgres-windowed-incidents-live"
    )
    store = build_live_runtime_postgres_store(
        monkeypatch,
        tmp_path,
        session_id=session_id,
    )
    try:
        store.append_alert(
            build_alert_event(
                session_id,
                timestamp_utc="2026-05-19 21:12:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Windowed grouped alert.",
                severity="warning",
                source_name="segment_0001.ts",
                window_index=2,
                window_start_sec=10.5,
            )
        )
        store.append_alert(
            build_alert_event(
                session_id,
                timestamp_utc="2026-05-19 21:12:20",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Windowless grouped alert.",
                severity="warning",
                source_name="segment_0002.ts",
                window_index=None,
                window_start_sec=None,
            )
        )

        timeline_response = request("GET", f"/sessions/{session_id}/alerts/timeline")
        summary_response = request(
            "GET",
            f"/sessions/{session_id}/alerts/incident-summary",
        )
    finally:
        close_store_if_possible(store)

    assert timeline_response.status_code == 200
    assert timeline_response.json() == _single_incident_timeline_payload(
        session_id,
        start_time_utc="2026-05-19 21:12:00",
        end_time_utc="2026-05-19 21:12:20",
        source_names=["segment_0001.ts", "segment_0002.ts"],
        sample_message="Windowed grouped alert.",
    )
    assert summary_response.status_code == 200
    payload = summary_response.json()
    assert payload == _single_incident_summary_with_runtime_narrative(
        session_id,
        first_alert_timestamp_utc="2026-05-19 21:12:00",
        last_alert_timestamp_utc="2026-05-19 21:12:20",
        narrative_summary=payload["narrative_summary"],
    )


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL grouped filtered route smoke test is opt-in.",
)
def test_live_runtime_postgres_grouped_routes_preserve_filtered_results(
    monkeypatch,
    tmp_path,
) -> None:
    """Live Postgres grouped FastAPI routes should keep detector/severity filters stable."""
    session_id = build_unique_session_id("session-runtime-postgres-api-filtered-live")
    store = build_live_runtime_postgres_store(
        monkeypatch,
        tmp_path,
        session_id=session_id,
    )
    try:
        for event in _runtime_filtered_grouped_postgres_events(session_id):
            store.append_alert(event)

        timeline_response = request(
            "GET",
            (
                f"/sessions/{session_id}/alerts/timeline"
                "?detector_id=video_metrics&severity=warning"
            ),
        )
        summary_response = request(
            "GET",
            (
                f"/sessions/{session_id}/alerts/incident-summary"
                "?detector_id=video_metrics&severity=warning"
            ),
        )
    finally:
        close_store_if_possible(store)

    assert timeline_response.status_code == 200
    assert timeline_response.json() == _single_filtered_incident_timeline_payload(
        session_id
    )
    assert summary_response.status_code == 200
    payload = summary_response.json()
    assert payload == _single_filtered_incident_summary_with_runtime_narrative(
        session_id,
        narrative_summary=payload["narrative_summary"],
    )


def test_grouped_alert_boundaries_skip_malformed_persisted_rows(
    monkeypatch,
    tmp_path,
) -> None:
    """FastAPI and MCP grouped readers should ignore malformed persisted rows the same way."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    session_dir = write_known_session(session_root, "session-malformed-grouped")
    write_alert_log(
        session_dir,
        [
            build_persisted_alert(
                "session-malformed-grouped",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Valid grouped row.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
            "{bad json",
            build_persisted_alert(
                "session-malformed-grouped",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="",
                title="Invalid detector row",
                message="Should be ignored by grouped readers.",
                severity="warning",
                source_name="segment_0002.ts",
            ),
        ],
    )
    expected_timeline = {
        "session_id": "session-malformed-grouped",
        "entries": [
            build_timeline_entry(
                start_time_utc="2026-05-06 10:00:00",
                end_time_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                severity="warning",
                title="Black screen detected",
                alert_count=1,
                source_names=["segment_0001.ts"],
                sample_message="Valid grouped row.",
            )
        ],
    }

    timeline_response = request("GET", "/sessions/session-malformed-grouped/alerts/timeline")
    summary_response = request(
        "GET",
        "/sessions/session-malformed-grouped/alerts/incident-summary",
    )
    timeline_result = call_mcp_tool(
        "query_session_alert_timeline",
        {"session_id": "session-malformed-grouped"},
    )
    summary_result = call_mcp_tool(
        "summarize_session_alert_incidents",
        {"session_id": "session-malformed-grouped"},
    )

    assert timeline_response.status_code == 200
    assert timeline_response.json() == expected_timeline
    assert_mcp_tool_success(timeline_result, expected_payload=expected_timeline)

    summary_payload = summary_response.json()
    expected_summary = _expected_incident_summary_with_runtime_narrative(
        "session-malformed-grouped",
        total_alerts=1,
        total_incidents=1,
        counts_by_detector={"video_metrics": 1},
        counts_by_severity={"warning": 1},
        top_incident_categories={"Black screen detected": 1},
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:00:00",
        narrative_summary=summary_payload["narrative_summary"],
    )
    assert summary_response.status_code == 200
    assert summary_payload == expected_summary
    assert_mcp_tool_success(
        summary_result,
        expected_payload=_expected_incident_summary_with_runtime_narrative(
            "session-malformed-grouped",
            total_alerts=1,
            total_incidents=1,
            counts_by_detector={"video_metrics": 1},
            counts_by_severity={"warning": 1},
            top_incident_categories={"Black screen detected": 1},
            first_alert_timestamp_utc="2026-05-06 10:00:00",
            last_alert_timestamp_utc="2026-05-06 10:00:00",
            narrative_summary=summary_result.structuredContent["narrative_summary"],
        ),
    )


def test_get_session_alert_incident_summary_accepts_severity_only_filter_with_empty_result(
    monkeypatch,
) -> None:
    """Severity-only filters should forward cleanly without changing the empty grouped envelope."""

    def fake_build_session_incident_summary(
        session_id: str,
        *,
        detector_id: str | None = None,
        severity: str | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> dict[str, object]:
        assert session_id == "session-123"
        assert detector_id is None
        assert severity == "warning"
        assert start_time_utc is None
        assert end_time_utc is None
        return _empty_incident_summary_payload(session_id)

    monkeypatch.setattr(
        "api.routers.alerts.build_session_incident_summary",
        fake_build_session_incident_summary,
    )

    response = request(
        "GET",
        "/sessions/session-123/alerts/incident-summary?severity=warning",
    )

    assert response.status_code == 200
    assert response.json() == _empty_incident_summary_payload("session-123")


def test_get_session_alert_timeline_accepts_detector_only_filter_with_empty_result(
    monkeypatch,
) -> None:
    """Detector-only filters should forward cleanly without changing the empty timeline envelope."""

    def fake_build_session_timeline(
        session_id: str,
        *,
        detector_id: str | None = None,
        severity: str | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> dict[str, object]:
        assert session_id == "session-123"
        assert detector_id == "video_metrics"
        assert severity is None
        assert start_time_utc is None
        assert end_time_utc is None
        return _empty_timeline_payload(session_id)

    monkeypatch.setattr(
        "api.routers.alerts.build_session_timeline",
        fake_build_session_timeline,
    )

    response = request(
        "GET",
        "/sessions/session-123/alerts/timeline?detector_id=video_metrics",
    )

    assert response.status_code == 200
    assert response.json() == _empty_timeline_payload("session-123")


# Service-error mapping


def test_get_session_alert_timeline_maps_missing_session_to_404(monkeypatch) -> None:
    """The timeline route should reuse the shared API not-found contract."""

    def fake_build_session_timeline(
        session_id: str,
        **_: object,
    ) -> dict[str, object]:
        raise SessionAlertsNotFoundError(session_id)

    monkeypatch.setattr(
        "api.routers.alerts.build_session_timeline",
        fake_build_session_timeline,
    )

    response = request("GET", "/sessions/missing-session/alerts/timeline")

    assert response.status_code == 404
    assert response.json() == build_session_not_found_payload("missing-session")


def test_get_session_alert_incident_summary_maps_service_validation_to_400(
    monkeypatch,
) -> None:
    """Incident-summary validation errors should surface as domain-style 400 responses."""

    def fake_build_session_incident_summary(
        session_id: str,
        **_: object,
    ) -> dict[str, object]:
        raise ValueError("start_time_utc must be earlier than or equal to end_time_utc")

    monkeypatch.setattr(
        "api.routers.alerts.build_session_incident_summary",
        fake_build_session_incident_summary,
    )

    response = request(
        "GET",
        (
            "/sessions/session-123/alerts/incident-summary"
            "?start_time_utc=2026-05-06%2010:10:00"
            "&end_time_utc=2026-05-06%2010:00:00"
        ),
    )

    assert response.status_code == 400
    assert response.json() == build_validation_error_payload(
        "start_time_utc must be earlier than or equal to end_time_utc"
    )


# Request validation


def test_get_session_alert_timeline_rejects_invalid_timestamp_format(
    monkeypatch,
    tmp_path,
) -> None:
    """Malformed timestamp filters should surface as domain-style 400 responses."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, "session-123")

    response = request(
        "GET",
        "/sessions/session-123/alerts/timeline?start_time_utc=not-a-time",
    )

    assert response.status_code == 400
    assert response.json() == build_validation_error_payload(
        "start_time_utc must use UTC timestamp format '%Y-%m-%d %H:%M:%S'"
    )


def test_get_session_alert_timeline_rejects_invalid_severity_query_value() -> None:
    """Timeline should enforce the same narrow severity contract as the older routes."""
    response = request("GET", "/sessions/session-123/alerts/timeline?severity=critical")

    assert response.status_code == 422
    assert_request_validation_payload(response.json(), field_name="severity")


def test_get_session_alert_incident_summary_rejects_invalid_severity_query_value() -> None:
    """Incident-summary should reject unsupported severity values at the request boundary."""
    response = request(
        "GET",
        "/sessions/session-123/alerts/incident-summary?severity=critical",
    )

    assert response.status_code == 422
    assert_request_validation_payload(response.json(), field_name="severity")
