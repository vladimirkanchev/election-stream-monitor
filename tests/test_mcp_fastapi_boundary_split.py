"""Focused tests for the current FastAPI-versus-stdio MCP boundary split.

This file owns the cross-surface trust rule for the current project stage:

- enabling FastAPI auth and rate limiting must not affect stdio MCP tools
- preparing the explicit FastAPI `share` runtime must not affect stdio MCP
- raw MCP list and summary tools should stay outside direct FastAPI
  auth/rate-limit state together
- grouped MCP timeline and summary tools should stay outside both FastAPI
  `share` protections and direct auth/rate-limit state
- grouped MCP tools should remain usable even if both the CLI `share`
  preparation path and the env-driven FastAPI protection path are touched
- one small smoke run should prove the protected HTTP route and the local MCP
  tool can still operate over the same persisted alert data

Raw MCP tool behavior stays in ``test_mcp_server_alerts_behavior.py`` and
``test_mcp_server_alerts_errors.py``. Grouped MCP tool behavior stays in
``test_mcp_server_incidents_behavior.py`` and
``test_mcp_server_incidents_errors.py``. This file therefore stays focused on
trust-boundary independence rather than on tool-specific payload behavior.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from api_server_cli import prepare_cli_runtime
from tests.api_alert_test_support import (
    install_api_auth_settings,
    install_api_rate_limit_settings,
    reset_alert_route_rate_limit_state,
)
from tests.api_boundary_env_test_support import (
    reset_boundary_test_state,
    restore_boundary_test_state,
    snapshot_boundary_env,
)
from tests.api_boundary_test_support import request
from tests.mcp_alert_test_support import call_mcp_tool
from tests.session_alert_test_support import (
    build_incident_summary_payload,
    build_normalized_alert,
    build_persisted_alert,
    build_timeline_entry,
    configure_session_alert_test,
    write_known_session,
)


@pytest.fixture(autouse=True)
def _clear_boundary_test_state() -> Generator[None, None, None]:
    """Keep env-driven FastAPI boundary state isolated across cross-surface tests."""

    original_values = snapshot_boundary_env()
    reset_boundary_test_state()
    yield
    restore_boundary_test_state(original_values)


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
    """Build the normalized raw-alert payload shared by the boundary fixture."""
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


def _assert_mcp_query_alerts_success(result, *, session_id: str) -> None:
    """Assert one successful MCP raw-alert query against the shared fixture payload."""

    assert result.isError is False
    assert result.structuredContent == _single_alert_payload(session_id)


def _single_alert_summary_payload(session_id: str) -> dict[str, object]:
    """Build the raw summary payload for the shared single-alert boundary fixture.

    The boundary file intentionally keeps one tiny persisted fixture shape for
    both FastAPI and MCP so cross-surface regressions are easier to attribute
    to the transport split rather than to differing test data.
    """
    return {
        "session_id": session_id,
        "total_alerts": 1,
        "counts_by_detector": {"video_metrics": 1},
        "counts_by_severity": {"warning": 1},
        "first_alert_timestamp_utc": "2026-05-06 10:00:00",
        "last_alert_timestamp_utc": "2026-05-06 10:00:00",
    }


def _assert_mcp_raw_alert_tools_success(session_id: str) -> None:
    """Assert both raw MCP read tools against the shared single-alert fixture.

    The boundary file cares about trust-split independence, not about the raw
    MCP tools as separate business behaviors. Keeping the paired success check
    here makes the raw-boundary tests read as one contract.
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


def _enable_fastapi_auth_and_rate_limiting(monkeypatch) -> None:
    """Enable the current FastAPI protection env used by MCP boundary tests.

    Keeping this env setup local to the boundary file makes the direct
    FastAPI-versus-stdio split obvious and avoids smuggling MCP assumptions
    into the raw or grouped tool behavior files.
    """
    monkeypatch.setenv("ESM_API_AUTH_ENABLED", "true")
    monkeypatch.setenv("ESM_API_AUTH_ALLOWED_KEYS", "alpha-key")
    monkeypatch.setenv("ESM_API_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("ESM_API_RATE_LIMIT_MAX_REQUESTS", "1")


def _prepare_combined_share_and_fastapi_protection_state(monkeypatch) -> None:
    """Apply both current FastAPI protection entrypoints before one MCP read.

    This mirrors the strongest current MCP boundary regression we care about:
    touching both the CLI `share` preparation path and the env-driven FastAPI
    protection path must still leave stdio MCP outside the HTTP trust boundary.
    """
    prepare_cli_runtime(mode="share", manual_api_key=None)
    _enable_fastapi_auth_and_rate_limiting(monkeypatch)


def _assert_grouped_mcp_tools_success(session_id: str) -> None:
    """Assert grouped MCP tools still expose the shared single-alert contracts.

    This helper keeps the boundary tests focused on the split itself:
    FastAPI `share` preparation may tighten the HTTP surface, but the local
    stdio MCP timeline and incident-summary tools must still read the same
    persisted session data without HTTP headers or limiter participation.
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


# Explicit FastAPI-versus-MCP boundary split


def test_mcp_raw_alert_tools_remain_usable_after_share_mode_cli_runtime_preparation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """CLI-prepared share mode should not pull raw stdio MCP into the HTTP boundary.

    This is the direct regression for the current `local`/`share` CLI runtime
    feature: preparing one protected FastAPI share-mode runtime must not make
    either raw MCP read entrypoint require HTTP headers or participate in HTTP
    rate-limit state.
    """

    session_id = "session-mcp-share-mode"
    _write_single_alert_session(monkeypatch, tmp_path, session_id)
    prepare_cli_runtime(mode="share", manual_api_key=None)

    _assert_mcp_raw_alert_tools_success(session_id)


def test_mcp_raw_alert_tools_remain_usable_when_fastapi_auth_and_rate_limiting_are_enabled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Raw stdio MCP list and summary tools should stay outside HTTP protections.

    This combined test is the direct raw-tool boundary guard for the current
    project stage: enabling FastAPI auth and rate limiting must not change the
    behavior of either raw MCP read entrypoint.
    """
    session_id = "session-mcp-fastapi-split"
    _write_single_alert_session(monkeypatch, tmp_path, session_id)
    _enable_fastapi_auth_and_rate_limiting(monkeypatch)

    _assert_mcp_raw_alert_tools_success(session_id)


# Grouped MCP boundary behavior


def test_mcp_incident_tools_remain_usable_after_share_mode_cli_runtime_preparation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Grouped stdio MCP tools should stay outside FastAPI `share` protections."""
    _write_single_alert_session(monkeypatch, tmp_path, "session-mcp-share-incidents")
    prepare_cli_runtime(mode="share", manual_api_key=None)

    _assert_grouped_mcp_tools_success("session-mcp-share-incidents")


def test_mcp_incident_tools_remain_usable_when_fastapi_auth_and_rate_limiting_are_enabled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Grouped stdio MCP tools should stay outside direct FastAPI auth/limiter state."""
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
    """Grouped stdio MCP tools should remain usable when both boundary paths are touched.

    This is the strongest grouped MCP boundary regression in the current file:
    even after both FastAPI protection entrypoints are prepared, stdio MCP must
    stay a local read surface rather than inheriting HTTP trust requirements.
    """
    _write_single_alert_session(
        monkeypatch,
        tmp_path,
        "session-mcp-share-and-fastapi-grouped-split",
    )
    _prepare_combined_share_and_fastapi_protection_state(monkeypatch)

    _assert_grouped_mcp_tools_success("session-mcp-share-and-fastapi-grouped-split")


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
    _assert_mcp_query_alerts_success(mcp_result, session_id="session-slice-smoke")
