"""Local stdio MCP server for bounded, read-only session-alert queries.

The tools use shared read models but remain outside the FastAPI HTTP boundary.
Their transport and capability policy is owned by ``docs/mcp-server.md``.
"""

from mcp.server.fastmcp import FastMCP

from api.schemas import (
    AlertTimestampFilter,
    DetectorIdentifier,
    ReadPageLimit,
    ReadPageOffset,
    SessionAlertQueryResponse,
    SessionAlertSummaryResponse,
    SessionAlertTimelineResponse,
    SessionIdentifier,
    SessionIncidentSummaryResponse,
)
from esm_mcp.alert_tools import (
    query_session_alert_timeline_tool,
    query_session_alerts_tool,
    summarize_session_alert_incidents_tool,
    summarize_session_alerts_tool,
)
from read_resource_policy import DEFAULT_READ_PAGE_LIMIT
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
        session_id: SessionIdentifier,
        detector_id: DetectorIdentifier | None = None,
        severity: EventSeverity | None = None,
        start_time_utc: AlertTimestampFilter | None = None,
        end_time_utc: AlertTimestampFilter | None = None,
        limit: ReadPageLimit = DEFAULT_READ_PAGE_LIMIT,
        offset: ReadPageOffset = 0,
    ) -> SessionAlertQueryResponse:
        """Return one page of persisted session alerts after optional filtering."""
        return query_session_alerts_tool(
            session_id,
            detector_id=detector_id,
            severity=severity,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
            limit=limit,
            offset=offset,
        )

    @mcp_server.tool(
        description="Return a deterministic summary of one monitoring session's alerts.",
        structured_output=True,
    )
    def summarize_session_alerts(
        session_id: SessionIdentifier,
        detector_id: DetectorIdentifier | None = None,
        severity: EventSeverity | None = None,
        start_time_utc: AlertTimestampFilter | None = None,
        end_time_utc: AlertTimestampFilter | None = None,
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
    """Register MCP tools for grouped incident timeline and summary reads."""

    @mcp_server.tool(
        description="Return grouped incident timeline entries for one monitoring session.",
        structured_output=True,
    )
    def query_session_alert_timeline(
        session_id: SessionIdentifier,
        detector_id: DetectorIdentifier | None = None,
        severity: EventSeverity | None = None,
        start_time_utc: AlertTimestampFilter | None = None,
        end_time_utc: AlertTimestampFilter | None = None,
        limit: ReadPageLimit = DEFAULT_READ_PAGE_LIMIT,
        offset: ReadPageOffset = 0,
    ) -> SessionAlertTimelineResponse:
        """Return one page of grouped incident entries after optional filtering."""
        return query_session_alert_timeline_tool(
            session_id,
            detector_id=detector_id,
            severity=severity,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
            limit=limit,
            offset=offset,
        )

    @mcp_server.tool(
        description="Return grouped incident summary data for one monitoring session.",
        structured_output=True,
    )
    def summarize_session_alert_incidents(
        session_id: SessionIdentifier,
        detector_id: DetectorIdentifier | None = None,
        severity: EventSeverity | None = None,
        start_time_utc: AlertTimestampFilter | None = None,
        end_time_utc: AlertTimestampFilter | None = None,
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
