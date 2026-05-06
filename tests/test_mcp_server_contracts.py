"""Focused contract tests for MCP alert-tool registration and launch wiring."""

import importlib
from pathlib import Path
import tomllib

import anyio

from esm_mcp.server import build_mcp_server
from mcp.shared.memory import create_connected_server_and_client_session


def test_mcp_server_registers_alert_tools() -> None:
    """The server should advertise the two alert tools with stable schema basics."""
    async def run() -> None:
        async with create_connected_server_and_client_session(build_mcp_server()) as session:
            tools = await session.list_tools()
            tool_names = sorted(tool.name for tool in tools.tools)
            assert tool_names == ["query_session_alerts", "summarize_session_alerts"]

            query_tool = next(tool for tool in tools.tools if tool.name == "query_session_alerts")
            summary_tool = next(
                tool for tool in tools.tools if tool.name == "summarize_session_alerts"
            )

            assert query_tool.inputSchema["required"] == ["session_id"]
            assert "severity" in query_tool.inputSchema["properties"]
            assert query_tool.outputSchema["properties"]["session_id"]["type"] == "string"
            assert query_tool.outputSchema["properties"]["alerts"]["type"] == "array"

            assert summary_tool.inputSchema["required"] == ["session_id"]
            assert "start_time_utc" in summary_tool.inputSchema["properties"]
            assert (
                summary_tool.outputSchema["properties"]["counts_by_detector"]["type"]
                == "object"
            )
            assert summary_tool.outputSchema["properties"]["total_alerts"]["type"] == "integer"

    anyio.run(run)


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
