"""MCP server exposing read-only session alert tools.

This adapter sits beside the FastAPI boundary and calls the shared alert query
service directly. It does not reimplement alert parsing or route through HTTP.
"""

from mcp.server.fastmcp import FastMCP

from api.schemas import SessionAlertQueryResponse, SessionAlertSummaryResponse
from esm_mcp.alert_tools import (
    query_session_alerts_tool,
    summarize_session_alerts_tool,
)
from session_models import EventSeverity

SERVER_NAME = "Election Stream Monitor MCP"
SERVER_INSTRUCTIONS = (
    "Read-only tools for querying persisted session alerts from the local-first "
    "Election Stream Monitor backend."
)


def build_mcp_server() -> FastMCP:
    """Return the project's MCP server with the current alert-query tools.

    The current server intentionally stays small:

    - stdio-first transport for local clients
    - read-only tools only
    - one shared alert-query seam reused from the FastAPI milestone
    """
    mcp_server = FastMCP(
        SERVER_NAME,
        instructions=SERVER_INSTRUCTIONS,
    )

    @mcp_server.tool(
        description="Return persisted alert events for one monitoring session.",
        structured_output=True,
    )
    def query_session_alerts(
        session_id: str,
        detector_id: str | None = None,
        severity: EventSeverity | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> SessionAlertQueryResponse:
        """Return persisted session alerts after applying optional filters."""
        return query_session_alerts_tool(
            session_id,
            detector_id=detector_id,
            severity=severity,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
        )

    @mcp_server.tool(
        description="Return a deterministic summary of one monitoring session's alerts.",
        structured_output=True,
    )
    def summarize_session_alerts(
        session_id: str,
        detector_id: str | None = None,
        severity: EventSeverity | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> SessionAlertSummaryResponse:
        """Return counts and time bounds for persisted session alerts."""
        return summarize_session_alerts_tool(
            session_id,
            detector_id=detector_id,
            severity=severity,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
        )

    return mcp_server


server = build_mcp_server()


def main() -> None:
    """Run the project's MCP server over stdio.

    Stdio is the intended default transport for the current local-first stage
    because it fits Codex and similar desktop/local MCP clients without
    introducing extra HTTP hosting concerns yet.
    """
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
