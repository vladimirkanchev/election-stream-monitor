"""Shared MCP tool implementations for the alert-query surface.

Keep the tool functions in a small dedicated module so:

- `server.py` stays focused on registration and launch
- tool behavior can be tested or reused without rebuilding the server
- transport-neutral alert query logic still lives in `session_alerts.py`
"""

from api.schemas import SessionAlertQueryResponse, SessionAlertSummaryResponse
from session_alerts import (
    SessionAlertsNotFoundError,
    filter_session_alert_events,
    summarize_session_alert_events,
)
from session_models import EventSeverity


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
    try:
        alerts = filter_session_alert_events(
            session_id,
            detector_id=detector_id,
            severity=severity,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
        )
    except SessionAlertsNotFoundError as err:
        raise ValueError(f"Session not found: {session_id}") from err
    except ValueError as err:
        raise ValueError(str(err)) from err
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
    try:
        return SessionAlertSummaryResponse.model_validate(
            summarize_session_alert_events(
                session_id,
                detector_id=detector_id,
                severity=severity,
                start_time_utc=start_time_utc,
                end_time_utc=end_time_utc,
            )
        )
    except SessionAlertsNotFoundError as err:
        raise ValueError(f"Session not found: {session_id}") from err
    except ValueError as err:
        raise ValueError(str(err)) from err
