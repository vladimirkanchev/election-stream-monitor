"""Focused response-bound tests for collection-oriented API and MCP reads."""

from collections.abc import Iterator

import pytest

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
