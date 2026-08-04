"""Shared helpers for the split FastAPI/MCP parity suites.

This module intentionally owns only the tiny seams shared by the parity files:

- protected FastAPI alert-route setup for cross-surface reads
- file-backed session setup for parity fixtures
- raw and grouped payload fetch helpers
- meaning-level assertions that compare FastAPI and MCP without forcing
  transport-wrapper identity

Trust-boundary independence stays in
``tests/test_mcp_fastapi_boundary_split.py``. These helpers exist so the
parity suites can read like boundary contracts instead of repeated request
plumbing.
"""

from __future__ import annotations

from collections.abc import Generator, Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

from tests.api_alert_test_support import (
    build_validation_error_payload,
    install_api_auth_settings,
    reset_alert_route_rate_limit_state,
)
from tests.api_boundary_env_test_support import (
    reset_boundary_test_state,
    restore_boundary_test_state,
    snapshot_boundary_env,
)
from tests.api_boundary_test_support import request
from tests.mcp_alert_test_support import call_mcp_tool, tool_error_text
from tests.session_alert_test_support import (
    configure_session_alert_test,
    write_known_session,
)

JsonDict = dict[str, object]


@pytest.fixture(autouse=True)
def clear_boundary_test_state() -> Generator[None, None, None]:
    """Keep env-driven FastAPI boundary state isolated across parity tests."""

    original_values = snapshot_boundary_env()
    reset_boundary_test_state()
    yield
    restore_boundary_test_state(original_values)


def enable_fastapi_alert_route_for_cross_surface_reads(monkeypatch) -> None:
    """Enable the protected FastAPI alert routes used by parity tests.

    The parity suites compare protected HTTP reads against local MCP reads, so
    they share one explicit route-setup seam instead of repeating auth setup in
    every scenario.
    """

    reset_alert_route_rate_limit_state()
    install_api_auth_settings(
        monkeypatch,
        enabled=True,
        allowed_api_keys=("valid-key",),
    )


def write_parity_session(
    monkeypatch,
    tmp_path: Path,
    session_id: str,
    *,
    alert_rows: Sequence[JsonDict] | None = None,
) -> None:
    """Create one parity session with optional persisted alert rows.

    The parity suites intentionally share the same file-backed session setup
    seam so each test can focus on cross-surface meaning instead of storage
    boilerplate.
    """

    session_root = configure_session_alert_test(monkeypatch, tmp_path)
    write_known_session(session_root, session_id, alert_rows=list(alert_rows or []))


def _raw_alert_count(payload: JsonDict) -> int:
    """Return the raw alert count from one cross-surface payload."""

    return len(cast(list[object], payload["alerts"]))


def _timeline_entry_count(payload: JsonDict) -> int:
    """Return the grouped timeline entry count from one cross-surface payload."""

    return len(cast(list[object], payload["entries"]))


def _timeline_entry_order(payload: JsonDict) -> list[tuple[str, str]]:
    """Return the grouped ordering meaning used by parity assertions."""

    entries = cast(list[JsonDict], payload["entries"])
    return [
        (
            cast(str, entry["title"]),
            cast(str, entry["detector_id"]),
        )
        for entry in entries
    ]


def _raw_summary_meaning(payload: JsonDict) -> JsonDict:
    """Return the raw-summary meaning that should match across both surfaces."""

    return {
        "total_alerts": payload["total_alerts"],
        "counts_by_detector": payload["counts_by_detector"],
        "counts_by_severity": payload["counts_by_severity"],
        "first_alert_timestamp_utc": payload["first_alert_timestamp_utc"],
        "last_alert_timestamp_utc": payload["last_alert_timestamp_utc"],
    }


def _incident_summary_meaning(payload: JsonDict) -> JsonDict:
    """Return the grouped-summary meaning that should match across both surfaces."""

    return {
        "total_incidents": payload["total_incidents"],
        "total_alerts": payload["total_alerts"],
        "counts_by_detector": payload["counts_by_detector"],
        "counts_by_severity": payload["counts_by_severity"],
        "top_incident_categories": payload["top_incident_categories"],
    }


def empty_raw_summary_meaning() -> JsonDict:
    """Return the stable empty raw-summary meaning shared by both surfaces."""

    return {
        "total_alerts": 0,
        "counts_by_detector": {},
        "counts_by_severity": {},
        "first_alert_timestamp_utc": None,
        "last_alert_timestamp_utc": None,
    }


def empty_incident_summary_meaning() -> JsonDict:
    """Return the stable empty grouped-summary meaning shared by both surfaces."""

    return {
        "total_incidents": 0,
        "total_alerts": 0,
        "counts_by_detector": {},
        "counts_by_severity": {},
        "top_incident_categories": {},
    }


def single_category_incident_summary_meaning(
    *,
    total_incidents: int,
    total_alerts: int,
    detector_id: str,
    severity: str,
    title: str,
) -> JsonDict:
    """Build grouped-summary meaning for one single-category scenario."""

    return {
        "total_incidents": total_incidents,
        "total_alerts": total_alerts,
        "counts_by_detector": {detector_id: total_alerts},
        "counts_by_severity": {severity: total_alerts},
        "top_incident_categories": {title: total_incidents},
    }


def build_time_filter_parity_inputs(
    *,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
) -> tuple[str, JsonDict]:
    """Build the shared FastAPI query string and MCP arguments for one time filter."""

    query_parts: list[str] = []
    mcp_arguments: JsonDict = {}

    if start_time_utc is not None:
        query_parts.append(f"start_time_utc={start_time_utc.replace(' ', '%20')}")
        mcp_arguments["start_time_utc"] = start_time_utc
    if end_time_utc is not None:
        query_parts.append(f"end_time_utc={end_time_utc.replace(' ', '%20')}")
        mcp_arguments["end_time_utc"] = end_time_utc

    query_string = f"?{'&'.join(query_parts)}" if query_parts else ""
    return query_string, mcp_arguments


def fetch_raw_parity_payloads(
    session_id: str,
    *,
    query_string: str = "",
    mcp_arguments: Mapping[str, object] | None = None,
) -> tuple[JsonDict, JsonDict, JsonDict, JsonDict]:
    """Read the same raw session view through FastAPI and MCP.

    The returned tuple is ordered as FastAPI list, FastAPI summary, MCP list,
    and MCP summary so the parity tests can stay compact and predictable.
    """

    mcp_arguments = {"session_id": session_id, **(mcp_arguments or {})}
    fastapi_alerts = request(
        "GET",
        f"/sessions/{session_id}/alerts{query_string}",
        headers={"X-API-Key": "valid-key"},
    )
    fastapi_summary = request(
        "GET",
        f"/sessions/{session_id}/alerts/summary{query_string}",
        headers={"X-API-Key": "valid-key"},
    )
    mcp_alerts = call_mcp_tool("query_session_alerts", mcp_arguments)
    mcp_summary = call_mcp_tool("summarize_session_alerts", mcp_arguments)

    assert fastapi_alerts.status_code == 200
    assert fastapi_summary.status_code == 200
    assert mcp_alerts.isError is False
    assert mcp_summary.isError is False

    return (
        fastapi_alerts.json(),
        fastapi_summary.json(),
        cast(dict[str, object], mcp_alerts.structuredContent),
        cast(dict[str, object], mcp_summary.structuredContent),
    )


def fetch_grouped_parity_payloads(
    session_id: str,
    *,
    query_string: str = "",
    mcp_arguments: Mapping[str, object] | None = None,
) -> tuple[JsonDict, JsonDict, JsonDict, JsonDict]:
    """Read the same grouped session view through FastAPI and MCP.

    The returned tuple is ordered as FastAPI timeline, FastAPI incident
    summary, MCP timeline, and MCP incident summary.
    """

    mcp_arguments = {"session_id": session_id, **(mcp_arguments or {})}
    fastapi_timeline = request(
        "GET",
        f"/sessions/{session_id}/alerts/timeline{query_string}",
        headers={"X-API-Key": "valid-key"},
    )
    fastapi_incident_summary = request(
        "GET",
        f"/sessions/{session_id}/alerts/incident-summary{query_string}",
        headers={"X-API-Key": "valid-key"},
    )
    mcp_timeline = call_mcp_tool("query_session_alert_timeline", mcp_arguments)
    mcp_incident_summary = call_mcp_tool(
        "summarize_session_alert_incidents",
        mcp_arguments,
    )

    assert fastapi_timeline.status_code == 200
    assert fastapi_incident_summary.status_code == 200
    assert mcp_timeline.isError is False
    assert mcp_incident_summary.isError is False

    return (
        fastapi_timeline.json(),
        fastapi_incident_summary.json(),
        cast(dict[str, object], mcp_timeline.structuredContent),
        cast(dict[str, object], mcp_incident_summary.structuredContent),
    )


def fetch_full_parity_payloads(
    session_id: str,
    *,
    query_string: str = "",
    mcp_arguments: Mapping[str, object] | None = None,
) -> tuple[
    JsonDict,
    JsonDict,
    JsonDict,
    JsonDict,
    JsonDict,
    JsonDict,
    JsonDict,
    JsonDict,
]:
    """Read the same raw and grouped views through both public surfaces.

    This keeps the edge-heavy parity tests readable when one scenario needs to
    compare both raw and grouped meaning for the same filter window.
    """

    raw_payloads = fetch_raw_parity_payloads(
        session_id,
        query_string=query_string,
        mcp_arguments=mcp_arguments,
    )
    grouped_payloads = fetch_grouped_parity_payloads(
        session_id,
        query_string=query_string,
        mcp_arguments=mcp_arguments,
    )
    return (*raw_payloads, *grouped_payloads)


def assert_raw_parity_meaning(
    fastapi_alert_payload: JsonDict,
    fastapi_summary_payload: JsonDict,
    mcp_alert_payload: JsonDict,
    mcp_summary_payload: JsonDict,
    *,
    expected_count: int,
    expected_summary_meaning: JsonDict,
) -> None:
    """Assert one cross-surface raw parity contract at the meaning level."""

    assert (
        _raw_alert_count(fastapi_alert_payload)
        == _raw_alert_count(mcp_alert_payload)
        == expected_count
    )
    assert _raw_summary_meaning(fastapi_summary_payload) == expected_summary_meaning
    assert _raw_summary_meaning(mcp_summary_payload) == expected_summary_meaning


def assert_grouped_parity_meaning(
    fastapi_timeline_payload: JsonDict,
    fastapi_summary_payload: JsonDict,
    mcp_timeline_payload: JsonDict,
    mcp_summary_payload: JsonDict,
    *,
    expected_count: int,
    expected_summary_meaning: JsonDict,
) -> None:
    """Assert one cross-surface grouped parity contract at the meaning level."""

    assert (
        _timeline_entry_count(fastapi_timeline_payload)
        == _timeline_entry_count(mcp_timeline_payload)
        == expected_count
    )
    assert _incident_summary_meaning(fastapi_summary_payload) == expected_summary_meaning
    assert _incident_summary_meaning(mcp_summary_payload) == expected_summary_meaning


def assert_cross_surface_validation_failure(
    *,
    fastapi_path: str,
    mcp_tool_name: str,
    mcp_arguments: JsonDict,
    expected_detail: str,
) -> None:
    """Assert one FastAPI-versus-MCP validation failure parity contract.

    The parity slice compares client-visible failure meaning, not transport
    wrapper equality, so FastAPI keeps its stable validation envelope while
    MCP stays a readable tool-error assertion.
    """

    fastapi_response = request(
        "GET",
        fastapi_path,
        headers={"X-API-Key": "valid-key"},
    )
    mcp_result = call_mcp_tool(mcp_tool_name, mcp_arguments)

    assert fastapi_response.status_code == 400
    assert fastapi_response.json() == build_validation_error_payload(expected_detail)
    assert mcp_result.isError is True
    assert expected_detail in tool_error_text(mcp_result)


def assert_timeline_order_parity(
    fastapi_timeline_payload: JsonDict,
    mcp_timeline_payload: JsonDict,
    *,
    expected_order: list[tuple[str, str]],
) -> None:
    """Assert grouped timeline ordering stays equivalent across both surfaces."""

    assert _timeline_entry_order(fastapi_timeline_payload) == expected_order
    assert _timeline_entry_order(mcp_timeline_payload) == expected_order
