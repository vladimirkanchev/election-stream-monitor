"""Focused FastAPI adapter tests for raw session alert query endpoints.

These tests stay intentionally thin. They verify that the raw alert routes:

- bind the expected query parameters
- preserve response payload shape
- keep empty-result envelopes stable for list and summary responses
- map service-layer errors into the stable API contract
- keep request validation aligned across the raw list and raw summary routes

Router-scoped auth and rate-limit policy lives in the split alerts-router
policy files:

- ``test_api_alert_route_auth_policy.py``
- ``test_api_alert_route_rate_limit_policy.py``
- ``test_api_alert_route_contracts.py``

That keeps this file a transport adapter spec rather than a policy catalog.
Reviewers should be able to read it route-by-route without also carrying the
auth and throttling story in their heads.
"""

from tests.api_alert_test_support import (
    assert_request_validation_payload,
    build_session_not_found_payload,
    build_validation_error_payload,
)
from session_alerts import SessionAlertsNotFoundError
from tests.api_boundary_test_support import request
from tests.session_alert_test_support import build_alert_summary_payload


def _empty_alert_list_payload(session_id: str) -> dict[str, object]:
    """Return the stable empty raw-alert list payload for one session.

    Keeping the empty envelope in one helper makes the newer contract tests
    read as route-boundary behavior instead of repeated payload literals.
    """
    return {
        "session_id": session_id,
        "alerts": [],
    }


def _empty_alert_summary_payload(session_id: str) -> dict[str, object]:
    """Return the stable empty raw-alert summary payload for one session.

    The summary route must preserve the same key set for empty and non-empty
    results so clients do not need a special parsing branch for no-alert
    sessions.
    """
    return build_alert_summary_payload(
        session_id,
        total_alerts=0,
        counts_by_detector={},
        counts_by_severity={},
        first_alert_timestamp_utc=None,
        last_alert_timestamp_utc=None,
    )


# Happy-path adapter behavior


def test_get_session_alerts_returns_filtered_response(monkeypatch) -> None:
    """The HTTP list route should forward filters and preserve response shape."""

    def fake_filter_session_alert_events(
        session_id: str,
        *,
        detector_id: str | None = None,
        severity: str | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> list[dict[str, object]]:
        assert session_id == "session-123"
        assert detector_id == "video_metrics"
        assert severity == "warning"
        assert start_time_utc == "2026-05-06 10:00:00"
        assert end_time_utc == "2026-05-06 10:05:00"
        return [
            {
                "session_id": session_id,
                "timestamp_utc": "2026-05-06 10:00:10",
                "detector_id": "video_metrics",
                "title": "Black screen detected",
                "message": "Black segment.",
                "severity": "warning",
                "source_name": "segment_0001.ts",
            }
        ]

    monkeypatch.setattr(
        "api.routers.alerts.filter_session_alert_events",
        fake_filter_session_alert_events,
    )

    response = request(
        "GET",
        (
            "/sessions/session-123/alerts"
            "?detector_id=video_metrics"
            "&severity=warning"
            "&start_time_utc=2026-05-06%2010:00:00"
            "&end_time_utc=2026-05-06%2010:05:00"
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "session-123"
    assert len(payload["alerts"]) == 1
    assert payload["alerts"][0]["session_id"] == "session-123"
    assert payload["alerts"][0]["timestamp_utc"] == "2026-05-06 10:00:10"
    assert payload["alerts"][0]["detector_id"] == "video_metrics"
    assert payload["alerts"][0]["title"] == "Black screen detected"
    assert payload["alerts"][0]["message"] == "Black segment."
    assert payload["alerts"][0]["severity"] == "warning"
    assert payload["alerts"][0]["source_name"] == "segment_0001.ts"


def test_get_session_alert_summary_returns_deterministic_payload(monkeypatch) -> None:
    """The HTTP summary route should stay a thin adapter over the service seam."""

    def fake_summarize_session_alert_events(
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
            "total_alerts": 1,
            "counts_by_detector": {"video_metrics": 1},
            "counts_by_severity": {"warning": 1},
            "first_alert_timestamp_utc": "2026-05-06 10:00:10",
            "last_alert_timestamp_utc": "2026-05-06 10:00:10",
        }

    monkeypatch.setattr(
        "api.routers.alerts.summarize_session_alert_events",
        fake_summarize_session_alert_events,
    )

    response = request(
        "GET",
        (
            "/sessions/session-123/alerts/summary"
            "?detector_id=video_metrics"
            "&severity=warning"
            "&start_time_utc=2026-05-06%2010:00:00"
            "&end_time_utc=2026-05-06%2010:05:00"
        ),
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "session-123",
        "total_alerts": 1,
        "counts_by_detector": {"video_metrics": 1},
        "counts_by_severity": {"warning": 1},
        "first_alert_timestamp_utc": "2026-05-06 10:00:10",
        "last_alert_timestamp_utc": "2026-05-06 10:00:10",
    }


def test_get_session_alerts_returns_stable_empty_payload(monkeypatch) -> None:
    """The raw list route should keep the same top-level shape when no alerts exist."""

    def fake_filter_session_alert_events(
        session_id: str,
        **_: object,
    ) -> list[dict[str, object]]:
        assert session_id == "empty-session"
        return []

    monkeypatch.setattr(
        "api.routers.alerts.filter_session_alert_events",
        fake_filter_session_alert_events,
    )

    response = request("GET", "/sessions/empty-session/alerts")

    assert response.status_code == 200
    assert response.json() == _empty_alert_list_payload("empty-session")


def test_get_session_alert_summary_returns_stable_empty_payload(monkeypatch) -> None:
    """The raw summary route should preserve all summary keys for an empty session."""

    def fake_summarize_session_alert_events(
        session_id: str,
        **_: object,
    ) -> dict[str, object]:
        assert session_id == "empty-session"
        return _empty_alert_summary_payload(session_id)

    monkeypatch.setattr(
        "api.routers.alerts.summarize_session_alert_events",
        fake_summarize_session_alert_events,
    )

    response = request("GET", "/sessions/empty-session/alerts/summary")

    assert response.status_code == 200
    assert response.json() == _empty_alert_summary_payload("empty-session")


def test_get_session_alerts_accepts_detector_only_filter_with_empty_result(
    monkeypatch,
) -> None:
    """Detector-only filters should forward cleanly without changing the empty envelope."""

    def fake_filter_session_alert_events(
        session_id: str,
        *,
        detector_id: str | None = None,
        severity: str | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> list[dict[str, object]]:
        assert session_id == "session-123"
        assert detector_id == "video_metrics"
        assert severity is None
        assert start_time_utc is None
        assert end_time_utc is None
        return []

    monkeypatch.setattr(
        "api.routers.alerts.filter_session_alert_events",
        fake_filter_session_alert_events,
    )

    response = request(
        "GET",
        "/sessions/session-123/alerts?detector_id=video_metrics",
    )

    assert response.status_code == 200
    assert response.json() == _empty_alert_list_payload("session-123")


def test_get_session_alert_summary_accepts_severity_only_filter_with_empty_result(
    monkeypatch,
) -> None:
    """Severity-only filters should forward cleanly without changing the empty summary envelope."""

    def fake_summarize_session_alert_events(
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
        return _empty_alert_summary_payload(session_id)

    monkeypatch.setattr(
        "api.routers.alerts.summarize_session_alert_events",
        fake_summarize_session_alert_events,
    )

    response = request(
        "GET",
        "/sessions/session-123/alerts/summary?severity=warning",
    )

    assert response.status_code == 200
    assert response.json() == _empty_alert_summary_payload("session-123")


# Service-error mapping


def test_get_session_alerts_maps_missing_session_to_404(monkeypatch) -> None:
    """Service-level unknown-session errors should map to the API not-found contract."""

    def fake_filter_session_alert_events(
        session_id: str,
        **_: object,
    ) -> list[dict[str, object]]:
        raise SessionAlertsNotFoundError(session_id)

    monkeypatch.setattr(
        "api.routers.alerts.filter_session_alert_events",
        fake_filter_session_alert_events,
    )

    response = request("GET", "/sessions/missing-session/alerts")

    assert response.status_code == 404
    assert response.json() == build_session_not_found_payload("missing-session")


def test_get_session_alert_summary_maps_service_validation_to_400(monkeypatch) -> None:
    """Service validation errors should surface as domain-style 400 responses."""

    def fake_summarize_session_alert_events(
        session_id: str,
        **_: object,
    ) -> dict[str, object]:
        raise ValueError("start_time_utc must be earlier than or equal to end_time_utc")

    monkeypatch.setattr(
        "api.routers.alerts.summarize_session_alert_events",
        fake_summarize_session_alert_events,
    )

    response = request(
        "GET",
        (
            "/sessions/session-123/alerts/summary"
            "?start_time_utc=2026-05-06%2010:10:00"
            "&end_time_utc=2026-05-06%2010:00:00"
        ),
    )

    assert response.status_code == 400
    assert response.json() == build_validation_error_payload(
        "start_time_utc must be earlier than or equal to end_time_utc"
    )


def test_get_session_alert_summary_maps_missing_session_to_404(monkeypatch) -> None:
    """The raw summary route should keep the same not-found contract as the list route."""

    def fake_summarize_session_alert_events(
        session_id: str,
        **_: object,
    ) -> dict[str, object]:
        raise SessionAlertsNotFoundError(session_id)

    monkeypatch.setattr(
        "api.routers.alerts.summarize_session_alert_events",
        fake_summarize_session_alert_events,
    )

    response = request("GET", "/sessions/missing-session/alerts/summary")

    assert response.status_code == 404
    assert response.json() == build_session_not_found_payload("missing-session")


# Request validation


def test_get_session_alerts_rejects_invalid_severity_query_value() -> None:
    """FastAPI request validation should reject unsupported severity values early."""

    response = request("GET", "/sessions/session-123/alerts?severity=critical")

    assert response.status_code == 422
    assert_request_validation_payload(response.json(), field_name="severity")


def test_get_session_alert_summary_rejects_invalid_severity_query_value() -> None:
    """The summary route should enforce the same severity contract as the list route."""
    response = request("GET", "/sessions/session-123/alerts/summary?severity=critical")

    assert response.status_code == 422
    assert_request_validation_payload(response.json(), field_name="severity")
