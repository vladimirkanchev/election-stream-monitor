"""Focused FastAPI adapter tests for grouped alert timeline and incident routes.

This file owns the HTTP boundary for the incident-oriented service layer:

- grouped timeline responses
- grouped incident summary responses
- stable empty-result envelopes for grouped incident reads
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
from session_alerts import SessionAlertsNotFoundError
from tests.api_boundary_test_support import request
from tests.session_alert_test_support import (
    build_incident_summary_payload,
    build_timeline_entry,
    configure_session_alert_test,
    write_known_session,
)


def _empty_timeline_payload(session_id: str) -> dict[str, object]:
    """Return the stable empty grouped-timeline payload for one session.

    Keeping the timeline empty envelope explicit helps reviewers see that the
    transport contract stays stable even when grouping produced no incidents.
    """
    return {
        "session_id": session_id,
        "entries": [],
    }


def _empty_incident_summary_payload(session_id: str) -> dict[str, object]:
    """Return the stable empty grouped incident-summary payload for one session.

    The grouped summary route extends the raw summary shape, so this helper
    keeps the contract tests centered on route behavior rather than on
    re-spelling the summary payload in every empty-result case.
    """
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
        return build_incident_summary_payload(
            session_id,
            total_alerts=1,
            total_incidents=1,
            counts_by_detector={"video_metrics": 1},
            counts_by_severity={"warning": 1},
            top_incident_categories={"Black screen detected": 1},
            first_alert_timestamp_utc="2026-05-06 10:00:10",
            last_alert_timestamp_utc="2026-05-06 10:00:10",
            narrative_summary="Session session-123 had 1 grouped incidents across 1 alerts.",
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
