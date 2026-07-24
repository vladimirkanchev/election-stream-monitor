"""Focused API and MCP tests for request, response, and store-work bounds."""

from collections.abc import Iterator

import pytest
from api.app import app
from api_boundary_config import MAX_HTTP_REQUEST_BODY_BYTES
from session_alert_store import AlertReadLimitExceededError

from tests.api_boundary_env_test_support import (
    reset_boundary_test_state,
    restore_boundary_test_state,
    snapshot_boundary_env,
)
from tests.api_boundary_test_support import request
from tests.mcp_alert_test_support import call_mcp_tool


@pytest.fixture(autouse=True)
def _isolate_boundary_settings() -> Iterator[None]:
    original_values = snapshot_boundary_env()
    reset_boundary_test_state()
    yield
    restore_boundary_test_state(original_values)


def _alert(session_id: str, index: int) -> dict[str, object]:
    return {
        "session_id": session_id,
        "timestamp_utc": f"2026-07-23 10:{index // 60:02d}:{index % 60:02d}",
        "detector_id": "video_metrics",
        "title": f"Alert {index}",
        "message": f"Message {index}",
        "severity": "warning",
        "source_name": f"segment_{index:04d}.ts",
    }


def _timeline_entry(index: int) -> dict[str, object]:
    timestamp = f"2026-07-23 10:{index // 60:02d}:{index % 60:02d}"
    return {
        "start_time_utc": timestamp,
        "end_time_utc": timestamp,
        "detector_id": "video_metrics",
        "severity": "warning",
        "title": f"Incident {index}",
        "alert_count": 1,
        "source_names": [f"segment_{index:04d}.ts"],
        "sample_message": f"Message {index}",
    }


def test_raw_alert_route_applies_default_and_explicit_pages(monkeypatch) -> None:
    session_id = "session-paged-alerts"
    alerts = [_alert(session_id, index) for index in range(260)]
    monkeypatch.setattr(
        "api.routers.alerts.filter_session_alert_events",
        lambda session_id, **filters: alerts,
    )

    default_response = request("GET", f"/sessions/{session_id}/alerts")
    page_response = request(
        "GET",
        f"/sessions/{session_id}/alerts?offset=100&limit=20",
    )
    maximum_page_response = request(
        "GET",
        f"/sessions/{session_id}/alerts?limit=250",
    )

    assert default_response.status_code == 200
    assert [item["title"] for item in default_response.json()["alerts"]] == [
        f"Alert {index}" for index in range(100)
    ]
    assert [item["title"] for item in page_response.json()["alerts"]] == [
        f"Alert {index}" for index in range(100, 120)
    ]
    assert len(maximum_page_response.json()["alerts"]) == 250


@pytest.mark.parametrize("query", ["limit=0", "limit=251", "offset=-1"])
def test_alert_read_pages_reject_values_outside_the_public_bounds(query: str) -> None:
    response = request("GET", f"/sessions/session-invalid-page/alerts?{query}")

    assert response.status_code == 422
    assert response.json()["error_code"] == "validation_failed"


def test_alert_routes_expose_the_shared_storage_read_ceiling(monkeypatch) -> None:
    """HTTP should report an oversized shared alert read without partial output."""
    monkeypatch.setattr(
        "api.routers.alerts.filter_session_alert_events",
        lambda *_, **__: (_ for _ in ()).throw(AlertReadLimitExceededError(2)),
    )

    response = request("GET", "/sessions/session-read-ceiling/alerts")

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Alert query exceeds the supported storage read limit",
        "error_code": "alert_query_limit_exceeded",
        "status_reason": "alert_query_limit_exceeded",
        "status_detail": "Maximum stored alert rows per query is 2.",
    }


@pytest.mark.parametrize(
    ("path", "field_name"),
    [
        (f"/sessions/{'x' * 129}/alerts", "session_id"),
        ("/sessions/%20%20/alerts", "session_id"),
        ("/sessions/session-input-bounds/alerts?detector_id=%20%20", "detector_id"),
        (
            f"/sessions/session-input-bounds/alerts?start_time_utc={'x' * 65}",
            "start_time_utc",
        ),
    ],
)
def test_alert_routes_reject_blank_or_oversized_identifier_filters(
    path: str,
    field_name: str,
) -> None:
    """Alert routes should reject abusive identifiers and filters before service reads."""
    response = request("GET", path)

    assert response.status_code == 422
    assert response.json()["error_code"] == "validation_failed"
    assert field_name in response.json()["status_detail"]


@pytest.mark.parametrize(
    "arguments",
    [
        {"session_id": "   "},
        {"session_id": "x" * 129},
        {"session_id": "session-input-bounds", "detector_id": "x" * 129},
        {
            "session_id": "session-input-bounds",
            "start_time_utc": "x" * 65,
        },
    ],
)
def test_mcp_tool_rejects_invalid_identifier_filters_before_reading_alerts(
    monkeypatch,
    arguments: dict[str, object],
) -> None:
    """MCP schema bounds must reject abusive filters before service reads."""
    service_called = False

    def fail_if_called(*_: object, **__: object) -> list[object]:
        nonlocal service_called
        service_called = True
        return []

    monkeypatch.setattr(
        "esm_mcp.alert_tools.filter_session_alert_events",
        fail_if_called,
    )

    result = call_mcp_tool("query_session_alerts", arguments)

    assert result.isError is True
    assert service_called is False


def test_timeline_route_pages_grouped_entries_without_changing_order(monkeypatch) -> None:
    session_id = "session-paged-timeline"
    entries = [_timeline_entry(index) for index in range(105)]
    monkeypatch.setattr(
        "api.routers.alerts.build_session_timeline",
        lambda session_id, **filters: {"session_id": session_id, "entries": entries},
    )

    response = request(
        "GET",
        f"/sessions/{session_id}/alerts/timeline?offset=100&limit=5",
    )

    assert response.status_code == 200
    assert [item["title"] for item in response.json()["entries"]] == [
        f"Incident {index}" for index in range(100, 105)
    ]


def test_mcp_raw_and_timeline_tools_use_the_same_page_contract(monkeypatch) -> None:
    session_id = "session-mcp-paged-reads"
    alerts = [_alert(session_id, index) for index in range(6)]
    entries = [_timeline_entry(index) for index in range(6)]
    monkeypatch.setattr(
        "esm_mcp.alert_tools.filter_session_alert_events",
        lambda session_id, **filters: alerts,
    )
    monkeypatch.setattr(
        "esm_mcp.alert_tools.build_session_timeline",
        lambda session_id, **filters: {"session_id": session_id, "entries": entries},
    )

    alert_result = call_mcp_tool(
        "query_session_alerts",
        {"session_id": session_id, "offset": 2, "limit": 2},
    )
    timeline_result = call_mcp_tool(
        "query_session_alert_timeline",
        {"session_id": session_id, "offset": 2, "limit": 2},
    )

    assert alert_result.isError is False
    assert [item["title"] for item in alert_result.structuredContent["alerts"]] == [
        "Alert 2",
        "Alert 3",
    ]
    assert timeline_result.isError is False
    assert [item["title"] for item in timeline_result.structuredContent["entries"]] == [
        "Incident 2",
        "Incident 3",
    ]


def test_mcp_raw_alert_tool_applies_default_and_maximum_pages(monkeypatch) -> None:
    """MCP raw-alert pages should match the FastAPI collection contract."""
    session_id = "session-mcp-page-bounds"
    alerts = [_alert(session_id, index) for index in range(260)]
    monkeypatch.setattr(
        "esm_mcp.alert_tools.filter_session_alert_events",
        lambda session_id, **filters: alerts,
    )

    default_result = call_mcp_tool("query_session_alerts", {"session_id": session_id})
    maximum_result = call_mcp_tool(
        "query_session_alerts",
        {"session_id": session_id, "limit": 250},
    )

    assert default_result.isError is False
    assert [item["title"] for item in default_result.structuredContent["alerts"]] == [
        f"Alert {index}" for index in range(100)
    ]
    assert maximum_result.isError is False
    assert len(maximum_result.structuredContent["alerts"]) == 250


@pytest.mark.parametrize(
    "arguments",
    [
        {"session_id": "session-invalid-page", "limit": 0},
        {"session_id": "session-invalid-page", "limit": 251},
        {"session_id": "session-invalid-page", "offset": -1},
    ],
)
def test_mcp_raw_alert_tool_rejects_values_outside_page_bounds(
    arguments: dict[str, object],
) -> None:
    """MCP should reject invalid pages before invoking the alert read service."""
    result = call_mcp_tool("query_session_alerts", arguments)

    assert result.isError is True


def test_session_snapshot_rejects_a_response_above_the_serialized_limit(monkeypatch) -> None:
    session_id = "session-large-snapshot"
    monkeypatch.setattr("api.routers.sessions.MAX_SESSION_SNAPSHOT_RESPONSE_BYTES", 256)
    monkeypatch.setattr(
        "api.routers.sessions.read_session_snapshot_or_none",
        lambda session_id: {
            "session": {
                "session_id": session_id,
                "mode": "video_files",
                "input_path": "/tmp/input.mp4",
                "selected_detectors": ["video_metrics"],
                "status": "running",
            },
            "progress": None,
            "alerts": [],
            "results": [
                {
                    "session_id": session_id,
                    "detector_id": "video_metrics",
                    "payload": {"detail": "x" * 512},
                }
            ],
            "latest_result": None,
        },
    )

    response = request("GET", f"/sessions/{session_id}")

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Session snapshot exceeds the supported response size",
        "error_code": "response_limit_exceeded",
        "status_reason": "response_limit_exceeded",
        "status_detail": "Maximum serialized response size is 256 bytes.",
    }


@pytest.mark.parametrize("path", ["/sessions", "/playback/resolve"])
def test_body_bearing_routes_reject_requests_above_the_shared_size_limit(
    path: str,
) -> None:
    """The shared body guard should reject oversized commands before route parsing."""

    response = request(
        "POST",
        path,
        headers={"content-type": "application/json"},
        content=b"{" + b" " * MAX_HTTP_REQUEST_BODY_BYTES,
    )

    assert response.status_code == 413
    assert response.json() == {
        "detail": "Request body exceeds the supported size",
        "error_code": "request_body_too_large",
        "status_reason": "request_body_too_large",
        "status_detail": (
            f"Maximum request body size is {MAX_HTTP_REQUEST_BODY_BYTES} bytes."
        ),
    }


def test_request_body_at_the_shared_size_limit_reaches_route_validation() -> None:
    """The limit is inclusive so exactly-sized commands remain route-owned input."""

    response = request(
        "POST",
        "/sessions",
        headers={"content-type": "application/json"},
        content=b"{}" + b" " * (MAX_HTTP_REQUEST_BODY_BYTES - 2),
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "validation_failed"


def test_body_bearing_routes_advertise_the_shared_413_contract() -> None:
    """OpenAPI should expose the body-size failure to HTTP API clients."""

    paths = app.openapi()["paths"]

    assert paths["/sessions"]["post"]["responses"]["413"]["description"] == (
        "Request body too large"
    )
    assert paths["/playback/resolve"]["post"]["responses"]["413"]["description"] == (
        "Request body too large"
    )
