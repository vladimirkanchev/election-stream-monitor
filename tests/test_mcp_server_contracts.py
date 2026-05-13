"""Focused structural tests for MCP tool registration and launch wiring.

This file owns the MCP surface that should stay stable even before any real
tool call happens:

- registered tool names and count
- input/output schema basics for raw and grouped read tools
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
    """Return one registered MCP tool by name for compact schema assertions.

    The contracts file stays intentionally small, so this helper removes the
    repeated lookup noise without introducing a broader test-support layer.
    """
    return next(tool for tool in tools.tools if tool.name == tool_name)


def test_mcp_server_registers_alert_tools() -> None:
    """The server should advertise the stable read-only MCP tool surface.

    This stays intentionally structural: it locks down the current tool names,
    read-only instructions, and the core raw/grouped input-output schema shape
    while richer payload and error behavior stays in the dedicated MCP tool
    behavior files.
    """
    tools = list_mcp_tools()
    tool_names = sorted(tool.name for tool in tools.tools)
    assert tool_names == [
        "query_session_alert_timeline",
        "query_session_alerts",
        "summarize_session_alert_incidents",
        "summarize_session_alerts",
    ]
    assert "Read-only tools" in SERVER_INSTRUCTIONS

    query_tool = _tool_named(tools, "query_session_alerts")
    summary_tool = _tool_named(tools, "summarize_session_alerts")
    timeline_tool = _tool_named(tools, "query_session_alert_timeline")
    incident_summary_tool = _tool_named(tools, "summarize_session_alert_incidents")

    assert query_tool.inputSchema["required"] == ["session_id"]
    assert "severity" in query_tool.inputSchema["properties"]
    assert query_tool.outputSchema["properties"]["session_id"]["type"] == "string"
    assert query_tool.outputSchema["properties"]["alerts"]["type"] == "array"

    assert summary_tool.inputSchema["required"] == ["session_id"]
    assert "start_time_utc" in summary_tool.inputSchema["properties"]
    assert summary_tool.outputSchema["properties"]["counts_by_detector"]["type"] == "object"
    assert summary_tool.outputSchema["properties"]["total_alerts"]["type"] == "integer"

    assert timeline_tool.inputSchema["required"] == ["session_id"]
    assert "start_time_utc" in timeline_tool.inputSchema["properties"]
    assert timeline_tool.outputSchema["properties"]["entries"]["type"] == "array"
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

    assert incident_summary_tool.inputSchema["required"] == ["session_id"]
    assert "severity" in incident_summary_tool.inputSchema["properties"]
    assert incident_summary_tool.outputSchema["properties"]["top_incident_categories"]["type"] == "object"
    assert (
        incident_summary_tool.outputSchema["properties"]["total_incidents"]["type"]
        == "integer"
    )
    assert "narrative_summary" in incident_summary_tool.outputSchema["properties"]


def test_mcp_server_registers_exactly_four_current_read_only_tools() -> None:
    """The current MCP surface should remain the exact four read/query tools.

    This stays separate from the broader registration/schema test so changes to
    tool count or accidental mutating tool registration fail through one small,
    obvious guard instead of being buried inside the schema assertions.
    """
    tools = list_mcp_tools()

    assert len(tools.tools) == 4
    assert {tool.name for tool in tools.tools} == _current_read_only_tool_names()


def test_main_runs_mcp_server_over_stdio(monkeypatch) -> None:
    """The module entrypoint should keep stdio as the default local transport.

    The repo currently treats MCP as a local-first read surface, so this test
    keeps the launch seam explicit even if registration details evolve later.
    """
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
