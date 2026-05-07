"""Shared helpers for MCP alert-tool tests.

The MCP tests exercise the real in-memory client/server seam, but most of the
async session setup is mechanical. These helpers keep that plumbing in one
place so the behavior files can stay focused on tool contracts, success
payloads, and readable failure mapping across both raw alert and grouped
incident tools.
"""

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
    """Run one callback against a fresh in-memory MCP client/server session.

    The callback receives the live MCP client session so each test can still be
    explicit about the tool call it is making.
    """

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
    """Flatten MCP text content blocks for concise error assertions.

    The current MCP SDK returns text fragments as content blocks, so the tests
    use this helper when they only care about the user-visible failure message.
    """
    return "\n".join(
        content.text for content in result.content if hasattr(content, "text")
    )
