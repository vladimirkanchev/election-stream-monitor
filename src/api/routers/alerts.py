"""FastAPI adapters for session-scoped alert query endpoints.

Keep alert-file reading, filtering, and summary logic in `session_alerts.py`.
Keep this module focused on:

- query parameter binding
- response schema binding
- API-oriented error mapping
"""

from fastapi import APIRouter

from api.errors import SessionNotFoundError, ValidationFailedError
from api.schemas import (
    ApiAlertSeverity,
    ApiErrorResponse,
    SessionAlertQueryResponse,
    SessionAlertSummaryResponse,
)
from session_alerts import (
    SessionAlertsNotFoundError,
    filter_session_alert_events,
    summarize_session_alert_events,
)

router = APIRouter(tags=["alerts"])


@router.get(
    "/sessions/{session_id}/alerts",
    response_model=SessionAlertQueryResponse,
    responses={
        400: {"model": ApiErrorResponse, "description": "Validation failed"},
        404: {"model": ApiErrorResponse, "description": "Session not found"},
        422: {"model": ApiErrorResponse, "description": "Request validation failed"},
    },
)
async def get_session_alerts(
    session_id: str,
    detector_id: str | None = None,
    severity: ApiAlertSeverity | None = None,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
) -> SessionAlertQueryResponse:
    """Return persisted alerts for one session after applying optional filters.

    This route is intentionally a thin adapter over `session_alerts.py`. It
    owns HTTP parameter binding and HTTP-style error mapping, not alert-query
    semantics themselves.
    """
    try:
        alerts = filter_session_alert_events(
            session_id,
            detector_id=detector_id,
            severity=severity,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
        )
    except SessionAlertsNotFoundError:
        raise SessionNotFoundError(session_id) from None
    except ValueError as err:
        raise ValidationFailedError(str(err)) from err
    return SessionAlertQueryResponse.model_validate(
        {
            "session_id": session_id,
            "alerts": alerts,
        }
    )


@router.get(
    "/sessions/{session_id}/alerts/summary",
    response_model=SessionAlertSummaryResponse,
    responses={
        400: {"model": ApiErrorResponse, "description": "Validation failed"},
        404: {"model": ApiErrorResponse, "description": "Session not found"},
        422: {"model": ApiErrorResponse, "description": "Request validation failed"},
    },
)
async def get_session_alert_summary(
    session_id: str,
    detector_id: str | None = None,
    severity: ApiAlertSeverity | None = None,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
) -> SessionAlertSummaryResponse:
    """Return a deterministic summary of persisted alerts for one session.

    Like the list endpoint, this route keeps transport concerns at the HTTP
    boundary and delegates the shared read/filter/summary behavior to the
    session alert service.
    """
    try:
        summary = summarize_session_alert_events(
            session_id,
            detector_id=detector_id,
            severity=severity,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
        )
    except SessionAlertsNotFoundError:
        raise SessionNotFoundError(session_id) from None
    except ValueError as err:
        raise ValidationFailedError(str(err)) from err
    return SessionAlertSummaryResponse.model_validate(summary)
