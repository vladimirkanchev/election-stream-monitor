"""Focused FastAPI adapter tests for session alert query endpoints."""

from tests.api_boundary_test_support import request


def _session_not_found_payload(session_id: str) -> dict[str, str]:
    """Return the expected API error payload for one missing session id."""
    return {
        "detail": "Session not found",
        "error_code": "session_not_found",
        "status_reason": "session_not_found",
        "status_detail": f"No persisted session snapshot found for session_id={session_id}",
    }


def _validation_error_payload(detail: str) -> dict[str, str]:
    """Return the expected API error payload for one validation failure."""
    return {
        "detail": detail,
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": detail,
    }


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
                "window_index": 1,
                "window_start_sec": 2.0,
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
    assert response.json() == {
        "session_id": "session-123",
        "alerts": [
            {
                "session_id": "session-123",
                "timestamp_utc": "2026-05-06 10:00:10",
                "detector_id": "video_metrics",
                "title": "Black screen detected",
                "message": "Black segment.",
                "severity": "warning",
                "source_name": "segment_0001.ts",
                "window_index": 1,
                "window_start_sec": 2.0,
            }
        ],
    }


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
            "total_alerts": 3,
            "counts_by_detector": {"video_metrics": 2, "video_blur": 1},
            "counts_by_severity": {"warning": 2, "info": 1},
            "first_alert_timestamp_utc": "2026-05-06 10:00:00",
            "last_alert_timestamp_utc": "2026-05-06 10:00:20",
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
        "total_alerts": 3,
        "counts_by_detector": {"video_metrics": 2, "video_blur": 1},
        "counts_by_severity": {"warning": 2, "info": 1},
        "first_alert_timestamp_utc": "2026-05-06 10:00:00",
        "last_alert_timestamp_utc": "2026-05-06 10:00:20",
    }


def test_get_session_alerts_maps_missing_session_to_404(monkeypatch) -> None:
    """Service-level unknown-session errors should map to the API not-found contract."""
    from api.routers.alerts import SessionAlertsNotFoundError

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
    assert response.json() == _session_not_found_payload("missing-session")


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
    assert response.json() == _validation_error_payload(
        "start_time_utc must be earlier than or equal to end_time_utc"
    )


def test_get_session_alerts_rejects_invalid_severity_query_value() -> None:
    """FastAPI request validation should reject unsupported severity values early."""
    response = request("GET", "/sessions/session-123/alerts?severity=critical")

    assert response.status_code == 422
    payload = response.json()
    assert payload["detail"] == "Request validation failed"
    assert payload["error_code"] == "validation_failed"
    assert payload["status_reason"] == "validation_failed"
    assert "severity" in payload["status_detail"]


def test_get_session_alert_summary_rejects_invalid_severity_query_value() -> None:
    """The summary route should enforce the same severity contract as the list route."""
    response = request("GET", "/sessions/session-123/alerts/summary?severity=critical")

    assert response.status_code == 422
    payload = response.json()
    assert payload["detail"] == "Request validation failed"
    assert payload["error_code"] == "validation_failed"
    assert payload["status_reason"] == "validation_failed"
    assert "severity" in payload["status_detail"]
