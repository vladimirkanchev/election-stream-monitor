"""Small shared helpers for split raw MCP alert-tool tests.

This support module owns only the tiny seams shared by the split raw MCP
behavior and error files:

- file-backed session setup for real MCP tool reads
- structured success assertions
- user-visible MCP error-text assertions

It intentionally does not own any MCP business behavior. The goal is to reduce
setup noise in the split suites without hiding the actual raw tool contracts.
"""

from pathlib import Path
from typing import Any, Mapping

from tests.mcp_alert_test_support import tool_error_text
from tests.session_alert_test_support import (
    build_persisted_alert,
    configure_session_alert_test,
    write_known_session,
)


def write_raw_alert_tool_session(
    monkeypatch,
    tmp_path: Path,
) -> Path:
    """Create one isolated alert-session root for real raw MCP tool scenarios."""
    return configure_session_alert_test(monkeypatch, tmp_path)


def assert_mcp_tool_success(
    result: Any,
    *,
    expected_payload: Mapping[str, object],
) -> None:
    """Assert one successful raw MCP result against its structured payload.

    The split raw behavior file should read like transport-plus-payload
    contracts, not repeated MCP SDK plumbing.
    """
    assert result.isError is False
    assert result.structuredContent == expected_payload


def assert_mcp_tool_error(
    result: Any,
    *,
    expected_message: str,
) -> None:
    """Assert one raw MCP tool failure against the user-visible error text.

    MCP errors surface as content blocks, so this helper keeps the negative-path
    tests focused on the stable message contract rather than transport details.
    """
    assert result.isError is True
    assert expected_message in tool_error_text(result)


def write_known_raw_alert_session(
    monkeypatch,
    tmp_path: Path,
    session_id: str,
) -> None:
    """Create one known raw-alert session with one persisted alert row.

    This keeps the "known session, unmatched filters" scenarios easy to scan in
    the split behavior suite.
    """
    session_root = write_raw_alert_tool_session(monkeypatch, tmp_path)
    write_known_session(
        session_root,
        session_id,
        alert_rows=[
            build_persisted_alert(
                session_id,
                timestamp_utc="2026-05-06 10:00:00",
                detector_id="video_metrics",
                title="Black screen detected",
                message="Known raw alert row.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        ],
    )


def write_empty_raw_alert_session(
    monkeypatch,
    tmp_path: Path,
    session_id: str,
) -> None:
    """Create one known raw-alert session without persisted alert rows."""
    session_root = write_raw_alert_tool_session(monkeypatch, tmp_path)
    write_known_session(session_root, session_id)
