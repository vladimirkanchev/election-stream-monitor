"""Focused tests for the current FastAPI-versus-stdio MCP boundary split.

This file owns only the cross-surface behavior for the current project stage:

- enabling FastAPI auth and rate limiting must not affect stdio MCP tools
- one small smoke run should prove the protected HTTP route and the local MCP
  tool can still operate over the same persisted alert data

Raw MCP alert-tool behavior stays in ``test_mcp_server_alerts.py`` so that
file can remain a straightforward tool-adapter spec. This split keeps the
cross-surface transport story explicit instead of hiding it inside raw tool
behavior tests.
"""

from pathlib import Path

from tests.api_alert_test_support import (
    install_api_auth_settings,
    install_api_rate_limit_settings,
    reset_alert_route_rate_limit_state,
)
from tests.api_boundary_test_support import request
from tests.mcp_alert_test_support import call_mcp_tool
from tests.session_alert_test_support import (
    build_normalized_alert,
    build_persisted_alert,
    configure_session_alert_test,
    write_known_session,
)


def _write_single_alert_session(monkeypatch, tmp_path: Path, session_id: str) -> None:
    """Create one persisted session with one alert for cross-surface boundary tests.

    The cross-surface tests intentionally use the same tiny persisted fixture
    for both FastAPI and MCP so any mismatch is easier to attribute to the
    boundary behavior rather than to differing test data.
    """
    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        session_id,
        alert_rows=[
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment.",
                severity="warning",
                source_name="segment_0001.ts",
            ),
        ],
    )


def _single_alert_payload(session_id: str) -> dict[str, object]:
    """Build the normalized alert payload shared by the current cross-surface tests."""
    return {
        "session_id": session_id,
        "alerts": [
            build_normalized_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Black segment.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    }


# Explicit FastAPI-versus-MCP boundary split


def test_mcp_alert_tools_remain_usable_when_fastapi_auth_and_rate_limiting_are_enabled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Current stdio MCP tools should remain outside the FastAPI auth/limiter boundary."""
    _write_single_alert_session(monkeypatch, tmp_path, "session-mcp-fastapi-split")
    monkeypatch.setenv("ESM_API_AUTH_ENABLED", "true")
    monkeypatch.setenv("ESM_API_AUTH_ALLOWED_KEYS", "alpha-key")
    monkeypatch.setenv("ESM_API_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("ESM_API_RATE_LIMIT_MAX_REQUESTS", "1")

    result = call_mcp_tool(
        "query_session_alerts",
        {"session_id": "session-mcp-fastapi-split"},
    )

    assert result.isError is False
    assert result.structuredContent == _single_alert_payload("session-mcp-fastapi-split")


# Lightweight cross-surface smoke coverage


def test_alert_query_slice_smoke_run_keeps_fastapi_and_stdio_mcp_paths_usable_together(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """One small smoke run should prove the two current public paths still coexist.

    This stays intentionally small. The goal is not to replace the focused
    route and tool suites, but to give one fast regression signal that the
    protected HTTP path and the local stdio MCP path can still read the same
    persisted alert session side by side.
    """
    _write_single_alert_session(monkeypatch, tmp_path, "session-slice-smoke")
    reset_alert_route_rate_limit_state()
    install_api_auth_settings(
        monkeypatch,
        enabled=True,
        allowed_api_keys=("valid-key",),
    )
    install_api_rate_limit_settings(
        monkeypatch,
        enabled=True,
        max_requests=2,
        window_seconds=60,
    )

    fastapi_response = request(
        "GET",
        "/sessions/session-slice-smoke/alerts",
        headers={"X-API-Key": "valid-key"},
    )
    mcp_result = call_mcp_tool(
        "query_session_alerts",
        {"session_id": "session-slice-smoke"},
    )

    assert fastapi_response.status_code == 200
    assert fastapi_response.json() == _single_alert_payload("session-slice-smoke")
    assert mcp_result.isError is False
    assert mcp_result.structuredContent == fastapi_response.json()
