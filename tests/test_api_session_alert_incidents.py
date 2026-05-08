"""Focused FastAPI adapter tests for grouped alert timeline and incident routes.

This file owns the HTTP boundary for the incident-oriented service layer:

- grouped timeline responses
- grouped incident summary responses
- empty-state transport behavior
- not-found and validation mapping for incident routes
- request-validation behavior specific to timeline and incident-summary routes

Router-scoped auth and rate-limit policy lives in the split alerts-router
policy files:

- ``test_api_alert_route_auth_policy.py``
- ``test_api_alert_route_rate_limit_policy.py``
- ``test_api_alert_route_contracts.py``

That keeps this file focused on transport adaptation over the grouped-incident
services. Reviewers should be able to read it route-by-route without also
carrying the auth and throttling story in their heads.
"""

from tests.api_alert_test_support import (
    assert_request_validation_payload,
    build_session_not_found_payload,
    build_validation_error_payload,
)
from tests.api_boundary_test_support import request
from tests.session_alert_test_support import (
    assert_narrative_contains,
    build_incident_summary_payload,
    build_timeline_entry,
    configure_session_alert_test,
    write_known_session,
)
from session_alerts import SessionAlertsNotFoundError


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
                    alert_count=2,
                    source_names=["segment_0001.ts", "segment_0002.ts"],
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
                alert_count=2,
                source_names=["segment_0001.ts", "segment_0002.ts"],
                sample_message="Black segment.",
            )
        ],
    }


def test_get_session_alert_timeline_returns_empty_entries_for_known_empty_session(
    monkeypatch,
) -> None:
    """Known sessions with no incidents should keep the empty timeline contract."""

    def fake_build_session_timeline(
        session_id: str,
        **_: object,
    ) -> dict[str, object]:
        assert session_id == "session-empty"
        return {
            "session_id": session_id,
            "entries": [],
        }

    monkeypatch.setattr(
        "api.routers.alerts.build_session_timeline",
        fake_build_session_timeline,
    )

    response = request("GET", "/sessions/session-empty/alerts/timeline")

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "session-empty",
        "entries": [],
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
        return build_incident_summary_payload(
            session_id,
            total_alerts=3,
            total_incidents=2,
            counts_by_detector={"video_metrics": 2, "video_blur": 1},
            counts_by_severity={"warning": 2, "info": 1},
            top_incident_categories={
                "Black screen detected": 1,
                "Blur increased": 1,
            },
            first_alert_timestamp_utc="2026-05-06 10:00:00",
            last_alert_timestamp_utc="2026-05-06 10:02:00",
            narrative_summary=(
                "Session session-123 had 2 grouped incidents across 3 alerts, "
                "mostly from video_metrics, led by blur increased, with 2 warning "
                "alerts and 1 info alerts."
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
        total_alerts=3,
        total_incidents=2,
        counts_by_detector={"video_metrics": 2, "video_blur": 1},
        counts_by_severity={"warning": 2, "info": 1},
        top_incident_categories={
            "Black screen detected": 1,
            "Blur increased": 1,
        },
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:02:00",
        narrative_summary=payload["narrative_summary"],
    )
    assert_narrative_contains(
        payload["narrative_summary"],
        "session-123",
        "2 grouped incidents",
        "3 alerts",
        "video_metrics",
        "blur increased",
        "2 warning alerts",
        "1 info alerts",
    )


def test_get_session_alert_incident_summary_returns_empty_state_for_known_empty_session(
    monkeypatch,
) -> None:
    """Known sessions without grouped incidents should keep a stable zero-value summary."""

    def fake_build_session_incident_summary(
        session_id: str,
        **_: object,
    ) -> dict[str, object]:
        assert session_id == "session-empty"
        return build_incident_summary_payload(
            session_id,
            total_alerts=0,
            total_incidents=0,
            counts_by_detector={},
            counts_by_severity={},
            top_incident_categories={},
            first_alert_timestamp_utc=None,
            last_alert_timestamp_utc=None,
            narrative_summary="Session session-empty had no alerts.",
        )

    monkeypatch.setattr(
        "api.routers.alerts.build_session_incident_summary",
        fake_build_session_incident_summary,
    )

    response = request("GET", "/sessions/session-empty/alerts/incident-summary")

    assert response.status_code == 200
    assert response.json() == build_incident_summary_payload(
        "session-empty",
        total_alerts=0,
        total_incidents=0,
        counts_by_detector={},
        counts_by_severity={},
        top_incident_categories={},
        first_alert_timestamp_utc=None,
        last_alert_timestamp_utc=None,
        narrative_summary="Session session-empty had no alerts.",
    )


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
