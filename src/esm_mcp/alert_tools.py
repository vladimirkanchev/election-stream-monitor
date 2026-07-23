"""Bounded local MCP adapters for raw-alert and incident reads.

Registration stays in ``server.py``. These adapters expose reviewed input
errors and hide unexpected storage diagnostics at the stdio boundary.
"""

from typing import TypeVar

from api.schemas import (
    ReadPageLimit,
    ReadPageOffset,
    SessionAlertQueryResponse,
    SessionAlertSummaryResponse,
    SessionAlertTimelineResponse,
    SessionIncidentSummaryResponse,
)
from read_resource_policy import DEFAULT_READ_PAGE_LIMIT, paginate_read_items
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
from session_alert_store import AlertReadLimitExceededError
from session_models import EventSeverity

ServiceResult = TypeVar("ServiceResult")

_MCP_ALERT_STORAGE_UNAVAILABLE_MESSAGE = "Alert storage is unavailable"
_MCP_SAFE_VALIDATION_MESSAGES = frozenset(
    {
        "start_time_utc must be earlier than or equal to end_time_utc",
        f"start_time_utc must use UTC timestamp format {ALERT_TIMESTAMP_FORMAT!r}",
        f"end_time_utc must use UTC timestamp format {ALERT_TIMESTAMP_FORMAT!r}",
    }
)


def _call_tool_alert_service(
    service_fn: AlertServiceCallable[ServiceResult],
    *,
    session_id: str,
    detector_id: str | None,
    severity: EventSeverity | None,
    start_time_utc: str | None,
    end_time_utc: str | None,
) -> ServiceResult:
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
    if isinstance(err, AlertReadLimitExceededError):
        return ValueError(str(err))
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
    limit: ReadPageLimit = DEFAULT_READ_PAGE_LIMIT,
    offset: ReadPageOffset = 0,
) -> SessionAlertQueryResponse:
    """Return one stable page of filtered alerts with safe error mapping."""
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
            "alerts": paginate_read_items(alerts, limit=limit, offset=offset),
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
    limit: ReadPageLimit = DEFAULT_READ_PAGE_LIMIT,
    offset: ReadPageOffset = 0,
) -> SessionAlertTimelineResponse:
    """Return one stable page of grouped incident entries for one session."""
    timeline = _call_tool_alert_service(
        build_session_timeline,
        session_id=session_id,
        detector_id=detector_id,
        severity=severity,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
    )
    return SessionAlertTimelineResponse.model_validate(
        {
            **timeline,
            "entries": paginate_read_items(
                timeline["entries"],
                limit=limit,
                offset=offset,
            ),
        }
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
