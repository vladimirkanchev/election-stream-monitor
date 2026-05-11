"""Local MCP adapters for Election Stream Monitor.

This package is intentionally named `esm_mcp` rather than `mcp` so it does not
shadow the third-party `mcp` SDK package used by the runtime adapter.
"""

from esm_mcp.server import build_mcp_server, server

__all__ = ["build_mcp_server", "server"]
