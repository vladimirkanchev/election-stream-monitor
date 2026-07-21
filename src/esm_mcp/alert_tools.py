"""MCP adapters for local read-only raw-alert and incident-query tools.

The adapters call the shared alert read models, keep server registration in
``server.py``, and map only reviewed input errors into MCP responses.
"""

from api.schemas import (
    SessionAlertQueryResponse,
    SessionAlertSummaryResponse,
    SessionAlertTimelineResponse,
    SessionIncidentSummaryResponse,
)
from session_alert_adapter import (
    AlertServiceCallable,
    build_alert_filter_kwargs,
    call_alert_service,
)
from session_alert_incidents import build_session_incident_summary, build_session_timeline
from session_alerts import (
    ALERT_TIMESTAMP_FORMAT,
    filter_session_alert_events,
    summarize_session_alert_events,
)
from session_models import EventSeverity

_MCP_ALERT_STORAGE_UNAVAILABLE_MESSAGE = "Alert storage is unavailable"
_MCP_SAFE_VALIDATION_MESSAGES = frozenset(
    {
        "start_time_utc must be earlier than or equal to end_time_utc",
        f"start_time_utc must use UTC timestamp format {ALERT_TIMESTAMP_FORMAT!r}",
        f"end_time_utc must use UTC timestamp format {ALERT_TIMESTAMP_FORMAT!r}",
    }
)


def _call_tool_alert_service(
    service_fn: AlertServiceCallable[object],
    *,
    session_id: str,
    detector_id: str | None,
    severity: EventSeverity | None,
    start_time_utc: str | None,
    end_time_utc: str | None,
) -> object:
    """Call one shared alert service using the standard MCP filter/error mapping.

    Validation and missing-session errors remain readable tool feedback. Other
    storage failures become one safe MCP error instead of exposing driver,
    filesystem, or configuration diagnostics through the stdio boundary.
    """
    try:
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
    except ValueError:
        raise
    except Exception:
        raise ValueError(_MCP_ALERT_STORAGE_UNAVAILABLE_MESSAGE) from None


def _map_tool_not_found(session_id: str) -> Exception:
    """Translate one unknown-session domain error into the MCP tool contract."""
    return ValueError(f"Session not found: {session_id}")


def _map_tool_validation_error(err: ValueError) -> Exception:
    """Expose only reviewed filter errors; hide unexpected backend detail."""
    message = str(err)
    if message in _MCP_SAFE_VALIDATION_MESSAGES:
        return ValueError(message)
    return ValueError(_MCP_ALERT_STORAGE_UNAVAILABLE_MESSAGE)


def query_session_alerts_tool(
    session_id: str,
    detector_id: str | None = None,
    severity: EventSeverity | None = None,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
) -> SessionAlertQueryResponse:
    """Return filtered persisted alerts with safe MCP error mapping."""
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
    """Return counts and time bounds for filtered persisted alerts."""
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
    """Return filtered grouped incident timeline entries for one session."""
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
    """Return filtered grouped incident counts and narrative summary."""
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
