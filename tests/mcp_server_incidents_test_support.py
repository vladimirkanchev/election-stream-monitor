"""Small shared helpers for split grouped MCP incident-tool tests.

This support module owns only the tiny seams shared by the split grouped MCP
behavior and error files:

- file-backed grouped-session setup
- structured grouped-tool success assertions
- user-visible grouped-tool error assertions

It intentionally stays small so the grouped behavior and error suites remain
easy to scan as service-boundary specs rather than as fixture-driven tests.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tests.mcp_alert_test_support import tool_error_text
from tests.session_alert_test_support import (
    build_persisted_alert,
    configure_session_alert_test,
    write_known_session,
)


def write_incident_tool_session(
    monkeypatch,
    tmp_path: Path,
) -> Path:
    """Create one isolated alert-session root for real grouped MCP scenarios."""
    return configure_session_alert_test(monkeypatch, tmp_path)


def assert_mcp_tool_success(
    result: Any,
    *,
    expected_payload: Mapping[str, object],
) -> None:
    """Assert one successful grouped MCP result against its structured payload."""
    assert result.isError is False
    assert result.structuredContent == expected_payload


def assert_mcp_tool_error(
    result: Any,
    *,
    expected_message: str,
) -> None:
    """Assert one grouped MCP failure against its user-visible error text."""
    assert result.isError is True
    assert expected_message in tool_error_text(result)


def write_empty_incident_session(
    monkeypatch,
    tmp_path: Path,
    session_id: str,
) -> None:
    """Create one known grouped-incident session without persisted alerts."""
    session_root = write_incident_tool_session(monkeypatch, tmp_path)
    write_known_session(session_root, session_id)


def write_known_incident_alert_session(
    monkeypatch,
    tmp_path: Path,
    session_id: str,
) -> None:
    """Create one known grouped-incident session with one persisted alert row.

    The grouped unknown-filter scenarios share this one-row fixture so the
    tests can focus on the "known session, unmatched filters" contract.
    """
    session_root = write_incident_tool_session(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        session_id,
        alert_rows=[
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Known grouped row.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    )
