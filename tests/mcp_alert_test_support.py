"""Shared in-memory MCP transport helpers for alert-tool tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, TypeVar

import anyio

from esm_mcp.server import build_mcp_server
from mcp.shared.memory import create_connected_server_and_client_session

RunReturn = TypeVar("RunReturn")


def run_with_mcp_session(
    callback: Callable[[Any], Awaitable[RunReturn]],
) -> RunReturn:
    """Run a callback against a fresh in-memory MCP client/server session."""

    async def run() -> RunReturn:
        async with create_connected_server_and_client_session(build_mcp_server()) as session:
            return await callback(session)

    return anyio.run(run)


def call_mcp_tool(
    tool_name: str,
    arguments: Mapping[str, object],
) -> Any:
    """Call one MCP tool with structured arguments and return the raw result."""

    async def run(session: Any) -> Any:
        return await session.call_tool(tool_name, dict(arguments))

    return run_with_mcp_session(run)


def list_mcp_tools() -> Any:
    """Return the current MCP tool listing from a fresh in-memory session."""

    async def run(session: Any) -> Any:
        return await session.list_tools()

    return run_with_mcp_session(run)


def tool_error_text(result: Any) -> str:
    """Return the user-visible text from MCP error content blocks."""
    return "\n".join(
        content.text for content in result.content if hasattr(content, "text")
    )


def assert_mcp_storage_failure_is_sanitized(
    result: Any,
    *,
    forbidden_values: tuple[str, ...],
) -> None:
    """Assert the stable storage error without leaking supplied diagnostics."""
    error_text = tool_error_text(result)

    assert result.isError is True
    assert "Alert storage is unavailable" in error_text
    for forbidden_value in forbidden_values:
        assert forbidden_value not in error_text
