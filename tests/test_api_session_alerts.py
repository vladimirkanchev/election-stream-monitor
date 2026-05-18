"""Focused FastAPI tests for raw alert-route transport behavior.

This file owns route parameter binding, payload shaping, empty-result behavior,
and error mapping for the raw alert list and summary endpoints.
"""

from tests.api_alert_test_support import (
    assert_request_validation_payload,
    build_session_not_found_payload,
    build_validation_error_payload,
)
from session_alerts import SessionAlertsNotFoundError
from tests.api_boundary_test_support import request
from tests.mcp_alert_test_support import call_mcp_tool
from tests.mcp_server_alerts_test_support import assert_mcp_tool_success
from tests.session_alert_test_support import (
    build_alert_summary_payload,
    build_normalized_alert,
    build_persisted_alert,
    configure_session_alert_test,
    write_known_session,
)


def _write_real_alert_session(
    monkeypatch,
    tmp_path,
    *,
    session_id: str,
    alert_rows: list[dict[str, object]],
) -> None:
    """Persist one real session for raw FastAPI and MCP boundary tests."""
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, session_id, alert_rows=alert_rows)


def _empty_alert_list_payload(session_id: str) -> dict[str, object]:
    """Return the stable empty raw-alert list payload for one session."""
    return {
        "session_id": session_id,
        "alerts": [],
    }


def _empty_alert_summary_payload(session_id: str) -> dict[str, object]:
    """Return the stable empty raw-alert summary payload for one session."""
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


def test_get_session_alerts_reads_the_real_file_backed_seam(
    monkeypatch,
    tmp_path,
) -> None:
    """The raw list route should work over persisted alert files without monkeypatched services."""
    _write_real_alert_session(
        monkeypatch,
        tmp_path,
        session_id="session-real-alert-list",
        alert_rows=[
            {
                "session_id": "session-real-alert-list",
                "timestamp_utc": "2026-05-06 10:00:00",
                "detector_id": "video_metrics",
                "title": "Black screen detected",
                "message": "Real persisted alert row.",
                "severity": "warning",
                "source_name": "segment_0001.ts",
            }
        ],
    )

    response = request("GET", "/sessions/session-real-alert-list/alerts")

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "session-real-alert-list",
        "alerts": [
            build_normalized_alert(
                "session-real-alert-list",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Real persisted alert row.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    }


def test_get_session_alert_summary_reads_the_real_file_backed_seam(
    monkeypatch,
    tmp_path,
) -> None:
    """The raw summary route should work over the real persisted alert seam."""
    _write_real_alert_session(
        monkeypatch,
        tmp_path,
        session_id="session-real-alert-summary",
        alert_rows=[
            {
                "session_id": "session-real-alert-summary",
                "timestamp_utc": "2026-05-06 10:00:00",
                "detector_id": "video_metrics",
                "title": "Black screen detected",
                "message": "First persisted alert row.",
                "severity": "warning",
                "source_name": "segment_0001.ts",
            },
            {
                "session_id": "session-real-alert-summary",
                "timestamp_utc": "2026-05-06 10:00:10",
                "detector_id": "video_blur",
                "title": "Blur increased",
                "message": "Second persisted alert row.",
                "severity": "info",
                "source_name": "segment_0002.ts",
            },
        ],
    )

    response = request("GET", "/sessions/session-real-alert-summary/alerts/summary")

    assert response.status_code == 200
    assert response.json() == build_alert_summary_payload(
        "session-real-alert-summary",
        total_alerts=2,
        counts_by_detector={"video_metrics": 1, "video_blur": 1},
        counts_by_severity={"warning": 1, "info": 1},
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:00:10",
    )


def test_raw_alert_boundaries_preserve_optional_window_fields(
    monkeypatch,
    tmp_path,
) -> None:
    """FastAPI and MCP raw readers should preserve normalized optional window fields."""
    _write_real_alert_session(
        monkeypatch,
        tmp_path,
        session_id="session-real-window-fields",
        alert_rows=[
            build_persisted_alert(
                "session-real-window-fields",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Windowed alert",
                message="Carries explicit window fields.",
                severity="warning",
                source_name="segment_0001.ts",
                window_index=3,
                window_start_sec=12.5,
            ),
            build_persisted_alert(
                "session-real-window-fields",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_blur",
                title="Windowless alert",
                message="Normalizes missing optional fields.",
                severity="info",
                source_name="segment_0002.ts",
            ),
        ],
    )
    expected_payload = {
        "session_id": "session-real-window-fields",
        "alerts": [
            build_normalized_alert(
                "session-real-window-fields",
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Windowed alert",
                message="Carries explicit window fields.",
                severity="warning",
                source_name="segment_0001.ts",
                window_index=3,
                window_start_sec=12.5,
            ),
            build_normalized_alert(
                "session-real-window-fields",
                timestamp_utc="2026-05-06 10:00:10",
                detector_id="video_blur",
                title="Windowless alert",
                message="Normalizes missing optional fields.",
                severity="info",
                source_name="segment_0002.ts",
                window_index=None,
                window_start_sec=None,
            ),
        ],
    }

    response = request("GET", "/sessions/session-real-window-fields/alerts")
    result = call_mcp_tool(
        "query_session_alerts",
        {"session_id": "session-real-window-fields"},
    )

    assert response.status_code == 200
    assert response.json() == expected_payload
    assert_mcp_tool_success(result, expected_payload=expected_payload)


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
