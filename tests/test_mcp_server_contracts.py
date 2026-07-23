"""Focused structural tests for MCP tool registration and launch wiring.

This file owns the MCP surface that should stay stable even before any real
tool call happens:

- registered tool names and count
- input/output schema basics, including bounded raw and timeline pages
- read-only MCP surface intent in server instructions
- stdio launch wiring
- installed console entrypoint metadata

Scenario-level raw alert, grouped incident, and FastAPI-boundary behavior
lives in the dedicated MCP behavior suites so this file can stay short,
structural, and easy to review.
"""

import importlib
from pathlib import Path
import tomllib

from esm_mcp.server import SERVER_INSTRUCTIONS
from tests.mcp_alert_test_support import list_mcp_tools


def _current_read_only_tool_names() -> set[str]:
    """Return the exact stable MCP tool names for the current read-only surface."""
    return {
        "query_session_alerts",
        "summarize_session_alerts",
        "query_session_alert_timeline",
        "summarize_session_alert_incidents",
    }


def _tool_named(tools, tool_name: str):
    """Return one registered MCP tool by name for schema assertions."""
    return next(tool for tool in tools.tools if tool.name == tool_name)


def _assert_shared_alert_filter_schema(tool, *, paged: bool = False) -> None:
    """Assert the current common session-alert request shape for one MCP tool."""
    assert tool.inputSchema["required"] == ["session_id"]
    expected_properties = {
        "session_id",
        "detector_id",
        "severity",
        "start_time_utc",
        "end_time_utc",
    }
    if paged:
        expected_properties.update({"limit", "offset"})
    assert set(tool.inputSchema["properties"]) == expected_properties
    if paged:
        assert tool.inputSchema["properties"]["limit"] == {
            "default": 100,
            "maximum": 250,
            "minimum": 1,
            "title": "Limit",
            "type": "integer",
        }
        assert tool.inputSchema["properties"]["offset"]["minimum"] == 0


def _assert_exact_output_fields(tool, expected_fields: set[str]) -> None:
    """Assert one MCP output exposes only its current public top-level fields."""
    assert set(tool.outputSchema["properties"]) == expected_fields


def test_mcp_server_registers_alert_tools() -> None:
    """The server should expose the stable read-only tool and paging schemas."""
    tools = list_mcp_tools()
    assert "Local stdio-only, read-only tools" in SERVER_INSTRUCTIONS

    query_tool = _tool_named(tools, "query_session_alerts")
    summary_tool = _tool_named(tools, "summarize_session_alerts")
    timeline_tool = _tool_named(tools, "query_session_alert_timeline")
    incident_summary_tool = _tool_named(tools, "summarize_session_alert_incidents")

    _assert_shared_alert_filter_schema(query_tool, paged=True)
    _assert_exact_output_fields(query_tool, {"session_id", "alerts"})
    assert set(
        query_tool.outputSchema["$defs"]["AlertEventResponse"]["properties"]
    ) == {
        "session_id",
        "timestamp_utc",
        "detector_id",
        "title",
        "message",
        "severity",
        "source_name",
        "window_index",
        "window_start_sec",
    }

    _assert_shared_alert_filter_schema(summary_tool)
    _assert_exact_output_fields(
        summary_tool,
        {
            "session_id",
            "total_alerts",
            "counts_by_detector",
            "counts_by_severity",
            "first_alert_timestamp_utc",
            "last_alert_timestamp_utc",
        },
    )

    _assert_shared_alert_filter_schema(timeline_tool, paged=True)
    _assert_exact_output_fields(timeline_tool, {"session_id", "entries"})
    assert (
        timeline_tool.outputSchema["properties"]["entries"]["items"]["$ref"]
        == "#/$defs/SessionAlertTimelineEntryResponse"
    )
    assert (
        timeline_tool.outputSchema["$defs"]["SessionAlertTimelineEntryResponse"][
            "properties"
        ]["sample_message"]["type"]
        == "string"
    )

    _assert_shared_alert_filter_schema(incident_summary_tool)
    _assert_exact_output_fields(
        incident_summary_tool,
        {
            "session_id",
            "total_alerts",
            "total_incidents",
            "counts_by_detector",
            "counts_by_severity",
            "top_incident_categories",
            "first_alert_timestamp_utc",
            "last_alert_timestamp_utc",
            "narrative_summary",
        },
    )


def test_mcp_server_registers_exactly_four_current_read_only_tools() -> None:
    """The MCP allowlist should remain the exact four current read/query tools."""
    tools = list_mcp_tools()

    assert len(tools.tools) == 4
    assert {tool.name for tool in tools.tools} == _current_read_only_tool_names()


def test_main_runs_mcp_server_over_stdio(monkeypatch) -> None:
    """The MCP entrypoint should keep stdio as its local-only transport."""
    calls: list[str] = []
    mcp_server_module = importlib.import_module("esm_mcp.server")

    class FakeServer:
        def run(self, *, transport: str) -> None:
            calls.append(transport)

    monkeypatch.setattr(mcp_server_module, "server", FakeServer())

    mcp_server_module.main()

    assert calls == ["stdio"]


def test_pyproject_declares_esm_mcp_console_entrypoint() -> None:
    """Project metadata should keep the installed MCP console script stable."""
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["esm-mcp"] == "esm_mcp.server:main"
