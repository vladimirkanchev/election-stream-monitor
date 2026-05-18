"""Focused tests for the FastAPI-versus-stdio MCP trust-boundary split.

This file owns the current local-trust rule for MCP:

- enabling FastAPI auth and rate limiting must not affect stdio MCP tools
- preparing the explicit FastAPI ``share`` runtime must not affect stdio MCP
- grouped MCP tools remain usable even if both ``share`` prep and direct
  FastAPI protection env are touched
- one small smoke run proves protected HTTP and local MCP can still read the
  same persisted alert data together

Cross-surface meaning parity now lives in
``tests/test_mcp_fastapi_parity_behavior.py`` and
``tests/test_mcp_fastapi_parity_edges.py``. The one shared boundary-state and
protected-route setup seam reused here lives in
``tests/mcp_fastapi_parity_test_support.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api_server_cli import prepare_cli_runtime
from tests.api_alert_test_support import (
    install_api_rate_limit_settings,
)
from tests.api_boundary_test_support import request
from tests.mcp_alert_test_support import call_mcp_tool
from tests.mcp_fastapi_parity_test_support import (
    clear_boundary_test_state,  # noqa: F401
    enable_fastapi_alert_route_for_cross_surface_reads,
)
from tests.session_alert_test_support import (
    build_incident_summary_payload,
    build_normalized_alert,
    build_persisted_alert,
    build_timeline_entry,
    configure_session_alert_test,
    write_known_session,
)

pytestmark = pytest.mark.usefixtures("clear_boundary_test_state")


def _write_single_alert_session(monkeypatch, tmp_path: Path, session_id: str) -> None:
    """Create one persisted single-alert session shared by boundary tests.

    The trust-boundary slice intentionally uses one tiny fixture so any failure
    is easier to attribute to boundary behavior rather than fixture complexity.
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
    """Build the normalized raw-alert payload for the shared boundary fixture."""

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


def _single_alert_summary_payload(session_id: str) -> dict[str, object]:
    """Build the raw-summary payload for the shared boundary fixture."""

    return {
        "session_id": session_id,
        "total_alerts": 1,
        "counts_by_detector": {"video_metrics": 1},
        "counts_by_severity": {"warning": 1},
        "first_alert_timestamp_utc": "2026-05-06 10:00:00",
        "last_alert_timestamp_utc": "2026-05-06 10:00:00",
    }


def _assert_mcp_query_alerts_success(result, *, session_id: str) -> None:
    """Assert one successful MCP raw-alert query against the shared fixture."""

    assert result.isError is False
    assert result.structuredContent == _single_alert_payload(session_id)


def _assert_mcp_raw_alert_tools_success(session_id: str) -> None:
    """Assert both raw MCP tools against the shared single-alert fixture.

    The boundary file cares about trust-split independence, not the raw MCP
    tools as separate business behaviors, so the paired assertion stays local.
    """

    query_result = call_mcp_tool(
        "query_session_alerts",
        {"session_id": session_id},
    )
    summary_result = call_mcp_tool(
        "summarize_session_alerts",
        {"session_id": session_id},
    )

    _assert_mcp_query_alerts_success(query_result, session_id=session_id)
    assert summary_result.isError is False
    assert summary_result.structuredContent == _single_alert_summary_payload(
        session_id
    )


def _assert_grouped_mcp_tools_success(session_id: str) -> None:
    """Assert grouped MCP tools still expose the shared single-alert contracts.

    Keeping the grouped timeline and grouped summary together here makes the
    grouped trust-boundary rule easier to scan as one contract.
    """

    timeline_result = call_mcp_tool(
        "query_session_alert_timeline",
        {"session_id": session_id},
    )
    summary_result = call_mcp_tool(
        "summarize_session_alert_incidents",
        {"session_id": session_id},
    )

    assert timeline_result.isError is False
    assert timeline_result.structuredContent == {
        "session_id": session_id,
        "entries": [
            build_timeline_entry(
                start_time_utc="2026-05-06 10:00:00",
                end_time_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                severity="warning",
                title="Black screen detected",
                alert_count=1,
                source_names=["segment_0001.ts"],
                sample_message="Black segment.",
            )
        ],
    }
    assert summary_result.isError is False
    assert summary_result.structuredContent == build_incident_summary_payload(
        session_id,
        total_alerts=1,
        total_incidents=1,
        counts_by_detector={"video_metrics": 1},
        counts_by_severity={"warning": 1},
        top_incident_categories={"Black screen detected": 1},
        first_alert_timestamp_utc="2026-05-06 10:00:00",
        last_alert_timestamp_utc="2026-05-06 10:00:00",
        narrative_summary=(
            f"Session {session_id} had 1 grouped incidents across 1 alerts, "
            "mostly from video_metrics, led by black screen detected, with 1 "
            "warning alerts and 0 info alerts."
        ),
    )


def _enable_fastapi_auth_and_rate_limiting(monkeypatch) -> None:
    """Enable the current FastAPI protection env used by MCP boundary tests."""

    monkeypatch.setenv("ESM_API_AUTH_ENABLED", "true")
    monkeypatch.setenv("ESM_API_AUTH_ALLOWED_KEYS", "alpha-key")
    monkeypatch.setenv("ESM_API_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("ESM_API_RATE_LIMIT_MAX_REQUESTS", "1")


def _prepare_combined_share_and_fastapi_protection_state(monkeypatch) -> None:
    """Apply both FastAPI protection entrypoints before one MCP read.

    This mirrors the strongest current MCP boundary regression we care about:
    both the CLI ``share`` path and the env-driven protection path may be
    touched, but stdio MCP must still stay outside the HTTP trust boundary.
    """

    prepare_cli_runtime(mode="share", manual_api_key=None)
    _enable_fastapi_auth_and_rate_limiting(monkeypatch)


def test_mcp_raw_alert_tools_remain_usable_after_share_mode_cli_runtime_preparation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """CLI-prepared share mode should not pull raw stdio MCP into the HTTP boundary."""

    session_id = "session-mcp-share-mode"
    _write_single_alert_session(monkeypatch, tmp_path, session_id)
    prepare_cli_runtime(mode="share", manual_api_key=None)

    _assert_mcp_raw_alert_tools_success(session_id)


def test_mcp_raw_alert_tools_remain_usable_when_fastapi_auth_and_rate_limiting_are_enabled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Raw stdio MCP list and summary tools should stay outside HTTP protections."""

    session_id = "session-mcp-fastapi-split"
    _write_single_alert_session(monkeypatch, tmp_path, session_id)
    _enable_fastapi_auth_and_rate_limiting(monkeypatch)

    _assert_mcp_raw_alert_tools_success(session_id)


def test_mcp_incident_tools_remain_usable_after_share_mode_cli_runtime_preparation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Grouped stdio MCP tools should stay outside FastAPI ``share`` protections."""

    _write_single_alert_session(monkeypatch, tmp_path, "session-mcp-share-incidents")
    prepare_cli_runtime(mode="share", manual_api_key=None)

    _assert_grouped_mcp_tools_success("session-mcp-share-incidents")


def test_mcp_incident_tools_remain_usable_when_fastapi_auth_and_rate_limiting_are_enabled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Grouped stdio MCP tools should stay outside direct FastAPI protections."""

    _write_single_alert_session(
        monkeypatch,
        tmp_path,
        "session-mcp-fastapi-grouped-split",
    )
    _enable_fastapi_auth_and_rate_limiting(monkeypatch)

    _assert_grouped_mcp_tools_success("session-mcp-fastapi-grouped-split")


def test_mcp_incident_tools_remain_usable_when_share_mode_and_direct_fastapi_protections_are_both_prepared(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Grouped MCP tools should remain usable when both boundary paths are touched."""

    _write_single_alert_session(
        monkeypatch,
        tmp_path,
        "session-mcp-share-and-fastapi-grouped-split",
    )
    _prepare_combined_share_and_fastapi_protection_state(monkeypatch)

    _assert_grouped_mcp_tools_success("session-mcp-share-and-fastapi-grouped-split")


def test_alert_query_slice_smoke_run_keeps_fastapi_and_stdio_mcp_paths_usable_together(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """One small smoke run should prove the protected HTTP and local MCP paths coexist."""

    session_id = "session-slice-smoke"
    _write_single_alert_session(monkeypatch, tmp_path, session_id)
    enable_fastapi_alert_route_for_cross_surface_reads(monkeypatch)
    install_api_rate_limit_settings(
        monkeypatch,
        enabled=True,
        max_requests=2,
        window_seconds=60,
    )

    fastapi_response = request(
        "GET",
        f"/sessions/{session_id}/alerts",
        headers={"X-API-Key": "valid-key"},
    )
    mcp_result = call_mcp_tool(
        "query_session_alerts",
        {"session_id": session_id},
    )

    assert fastapi_response.status_code == 200
    assert fastapi_response.json() == _single_alert_payload(session_id)
    _assert_mcp_query_alerts_success(mcp_result, session_id=session_id)
