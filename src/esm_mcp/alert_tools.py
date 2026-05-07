"""Shared MCP tool implementations for the alert-query surface.

Keep the tool functions in a small dedicated module so:

- `server.py` stays focused on registration and launch
- tool behavior can be tested or reused without rebuilding the server
- transport-neutral alert query logic still lives in `session_alerts.py`

The MCP surface intentionally mirrors the FastAPI split:

- raw alert-event list and raw numeric summary
- grouped incident timeline and grouped incident summary
"""

from api.schemas import (
    SessionAlertQueryResponse,
    SessionAlertSummaryResponse,
    SessionAlertTimelineResponse,
    SessionIncidentSummaryResponse,
)
from session_alert_adapter import build_alert_filter_kwargs, call_alert_service
from session_alerts import (
    build_session_incident_summary,
    build_session_timeline,
    filter_session_alert_events,
    summarize_session_alert_events,
)
from session_models import EventSeverity


def _call_tool_alert_service(
    service_fn: object,
    *,
    session_id: str,
    detector_id: str | None,
    severity: EventSeverity | None,
    start_time_utc: str | None,
    end_time_utc: str | None,
) -> object:
    """Call one shared alert service using the standard MCP filter/error mapping.

    The tool layer keeps transport-specific failure wording here and leaves the
    underlying query, grouping, and summary semantics in ``session_alerts.py``.
    """
    return call_alert_service(
        service_fn,
        session_id=session_id,
        filter_kwargs=build_alert_filter_kwargs(
            detector_id=detector_id,
            severity=severity,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
        ),
        map_not_found=_map_tool_not_found,
        map_validation_error=_map_tool_validation_error,
    )


def _map_tool_not_found(session_id: str) -> Exception:
    """Translate one unknown-session domain error into the MCP tool contract."""
    return ValueError(f"Session not found: {session_id}")


def _map_tool_validation_error(err: ValueError) -> Exception:
    """Translate one shared-service validation failure into a tool error."""
    return ValueError(str(err))


def query_session_alerts_tool(
    session_id: str,
    detector_id: str | None = None,
    severity: EventSeverity | None = None,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
) -> SessionAlertQueryResponse:
    """Return persisted session alerts after applying optional filters.

    This helper intentionally translates shared-service failures into ordinary
    tool-facing `ValueError`s so the MCP SDK can surface them as structured
    tool errors without exposing backend-specific exception classes.
    """
    alerts = _call_tool_alert_service(
        filter_session_alert_events,
        session_id=session_id,
        detector_id=detector_id,
        severity=severity,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
    )
    return SessionAlertQueryResponse.model_validate(
        {
            "session_id": session_id,
            "alerts": alerts,
        }
    )


def summarize_session_alerts_tool(
    session_id: str,
    detector_id: str | None = None,
    severity: EventSeverity | None = None,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
) -> SessionAlertSummaryResponse:
    """Return counts and time bounds for persisted session alerts.

    This is the MCP-facing equivalent of the FastAPI summary adapter: small
    transport error mapping on top of the shared alert-query service.
    """
    return SessionAlertSummaryResponse.model_validate(
        _call_tool_alert_service(
            summarize_session_alert_events,
            session_id=session_id,
            detector_id=detector_id,
            severity=severity,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
        )
    )


def query_session_alert_timeline_tool(
    session_id: str,
    detector_id: str | None = None,
    severity: EventSeverity | None = None,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
) -> SessionAlertTimelineResponse:
    """Return grouped incident timeline entries for one session.

    This tool mirrors the FastAPI timeline adapter: shared-service call plus
    lightweight MCP-facing error mapping only.
    """
    return SessionAlertTimelineResponse.model_validate(
        _call_tool_alert_service(
            build_session_timeline,
            session_id=session_id,
            detector_id=detector_id,
            severity=severity,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
        )
    )


def summarize_session_alert_incidents_tool(
    session_id: str,
    detector_id: str | None = None,
    severity: EventSeverity | None = None,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
) -> SessionIncidentSummaryResponse:
    """Return grouped incident summary data for one session.

    This stays distinct from the raw alert-count summary tool by calling the
    grouped incident summary service directly.
    """
    return SessionIncidentSummaryResponse.model_validate(
        _call_tool_alert_service(
            build_session_incident_summary,
            session_id=session_id,
            detector_id=detector_id,
            severity=severity,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
        )
    )
