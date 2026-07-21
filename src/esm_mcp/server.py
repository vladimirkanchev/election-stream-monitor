"""Local stdio MCP server for read-only session-alert queries.

It calls shared read models directly; FastAPI authentication and rate limiting
do not apply to this separate local-process boundary.
"""

from mcp.server.fastmcp import FastMCP

from api.schemas import (
    SessionAlertQueryResponse,
    SessionAlertSummaryResponse,
    SessionAlertTimelineResponse,
    SessionIncidentSummaryResponse,
)
from esm_mcp.alert_tools import (
    query_session_alerts_tool,
    query_session_alert_timeline_tool,
    summarize_session_alert_incidents_tool,
    summarize_session_alerts_tool,
)
from session_models import EventSeverity

SERVER_NAME = "Election Stream Monitor MCP"
SERVER_INSTRUCTIONS = (
    "Local stdio-only, read-only tools for querying persisted session alerts "
    "from the local-first Election Stream Monitor backend."
)


def _register_raw_alert_query_tools(mcp_server: FastMCP) -> None:
    """Register MCP tools for raw persisted alert queries."""

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


def _register_incident_alert_tools(mcp_server: FastMCP) -> None:
    """Register MCP tools for grouped incident timeline and summary views.

    These tools reuse the same shared incident-building logic as the FastAPI
    routes so operators and coding agents see one consistent grouped read
    model.
    """

    @mcp_server.tool(
        description="Return grouped incident timeline entries for one monitoring session.",
        structured_output=True,
    )
    def query_session_alert_timeline(
        session_id: str,
        detector_id: str | None = None,
        severity: EventSeverity | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> SessionAlertTimelineResponse:
        """Return grouped incident timeline entries after optional filtering."""
        return query_session_alert_timeline_tool(
            session_id,
            detector_id=detector_id,
            severity=severity,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
        )

    @mcp_server.tool(
        description="Return grouped incident summary data for one monitoring session.",
        structured_output=True,
    )
    def summarize_session_alert_incidents(
        session_id: str,
        detector_id: str | None = None,
        severity: EventSeverity | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> SessionIncidentSummaryResponse:
        """Return grouped incident counts, categories, and narrative summary."""
        return summarize_session_alert_incidents_tool(
            session_id,
            detector_id=detector_id,
            severity=severity,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
        )


def build_mcp_server() -> FastMCP:
    """Build the current local read-only MCP alert-query server."""
    mcp_server = FastMCP(
        SERVER_NAME,
        instructions=SERVER_INSTRUCTIONS,
    )
    _register_raw_alert_query_tools(mcp_server)
    _register_incident_alert_tools(mcp_server)
    return mcp_server


server = build_mcp_server()


def main() -> None:
    """Run the local MCP server over its only supported transport: stdio."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
