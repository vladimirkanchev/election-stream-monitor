"""Focused contract tests for MCP alert-tool registration and launch wiring.

These checks stay above the shared service but below scenario-level behavior:

- tool registration names
- input/output schema basics
- stdio launch wiring
- installed console entrypoint metadata

Real alert and incident tool behavior lives in the dedicated MCP behavior
files so this contract file remains short and structural.
"""

import importlib
from pathlib import Path
import tomllib

from tests.mcp_alert_test_support import list_mcp_tools


def test_mcp_server_registers_alert_tools() -> None:
    """The server should advertise alert tools with stable names and schema basics."""
    tools = list_mcp_tools()
    tool_names = sorted(tool.name for tool in tools.tools)
    assert tool_names == [
        "query_session_alert_timeline",
        "query_session_alerts",
        "summarize_session_alert_incidents",
        "summarize_session_alerts",
    ]

    query_tool = next(tool for tool in tools.tools if tool.name == "query_session_alerts")
    summary_tool = next(
        tool for tool in tools.tools if tool.name == "summarize_session_alerts"
    )
    timeline_tool = next(
        tool for tool in tools.tools if tool.name == "query_session_alert_timeline"
    )
    incident_summary_tool = next(
        tool for tool in tools.tools if tool.name == "summarize_session_alert_incidents"
    )

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


def test_main_runs_mcp_server_over_stdio(monkeypatch) -> None:
    """The module entrypoint should keep stdio as the default local transport."""
    calls: list[str] = []
    mcp_server_module = importlib.import_module("esm_mcp.server")

    class FakeServer:
        def run(self, *, transport: str) -> None:
            calls.append(transport)

    monkeypatch.setattr(mcp_server_module, "server", FakeServer())

    mcp_server_module.main()

    assert calls == ["stdio"]


def test_pyproject_declares_esm_mcp_console_entrypoint() -> None:
    """Project metadata should keep the installed console entrypoint wired to the server."""
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["esm-mcp"] == "esm_mcp.server:main"
