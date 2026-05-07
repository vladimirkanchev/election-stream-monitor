"""FastAPI adapters for session-scoped alert query endpoints.

Keep alert-file reading, filtering, and summary logic in `session_alerts.py`.
Keep this module focused on:

- query parameter binding
- response schema binding
- API-oriented error mapping

The route family is intentionally split into two read models over the same
shared service seam:

- raw alert-event list and raw numeric summary
- grouped incident timeline and grouped incident summary
"""

from fastapi import APIRouter

from api.errors import SessionNotFoundError, ValidationFailedError
from api.schemas import (
    ApiAlertSeverity,
    ApiErrorResponse,
    SessionAlertTimelineResponse,
    SessionAlertQueryResponse,
    SessionIncidentSummaryResponse,
    SessionAlertSummaryResponse,
)
from session_alert_adapter import build_alert_filter_kwargs, call_alert_service
from session_alerts import (
    build_session_incident_summary,
    build_session_timeline,
    filter_session_alert_events,
    summarize_session_alert_events,
)

router = APIRouter(tags=["alerts"])


def _call_http_alert_service(
    service_fn: object,
    *,
    session_id: str,
    detector_id: str | None,
    severity: ApiAlertSeverity | None,
    start_time_utc: str | None,
    end_time_utc: str | None,
) -> object:
    """Call one shared alert service using the standard HTTP filter/error mapping.

    This keeps the individual route functions easy to scan: bind params, call
    the shared helper, then validate the structured response model.
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
        map_not_found=_map_http_not_found,
        map_validation_error=_map_http_validation_error,
    )


def _map_http_not_found(session_id: str) -> Exception:
    """Translate one unknown-session domain error into the FastAPI contract."""
    return SessionNotFoundError(session_id)


def _map_http_validation_error(err: ValueError) -> Exception:
    """Translate one shared-service validation failure into the API contract."""
    return ValidationFailedError(str(err))


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
    alerts = _call_http_alert_service(
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
    summary = _call_http_alert_service(
        summarize_session_alert_events,
        session_id=session_id,
        detector_id=detector_id,
        severity=severity,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
    )
    return SessionAlertSummaryResponse.model_validate(summary)


@router.get(
    "/sessions/{session_id}/alerts/timeline",
    response_model=SessionAlertTimelineResponse,
    responses={
        400: {"model": ApiErrorResponse, "description": "Validation failed"},
        404: {"model": ApiErrorResponse, "description": "Session not found"},
        422: {"model": ApiErrorResponse, "description": "Request validation failed"},
    },
)
async def get_session_alert_timeline(
    session_id: str,
    detector_id: str | None = None,
    severity: ApiAlertSeverity | None = None,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
) -> SessionAlertTimelineResponse:
    """Return grouped incident timeline entries for one session.

    This endpoint remains a pure HTTP adapter. It binds query parameters and
    maps domain errors, while the shared alert service owns all grouping rules.
    """
    timeline = _call_http_alert_service(
        build_session_timeline,
        session_id=session_id,
        detector_id=detector_id,
        severity=severity,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
    )
    return SessionAlertTimelineResponse.model_validate(timeline)


@router.get(
    "/sessions/{session_id}/alerts/incident-summary",
    response_model=SessionIncidentSummaryResponse,
    responses={
        400: {"model": ApiErrorResponse, "description": "Validation failed"},
        404: {"model": ApiErrorResponse, "description": "Session not found"},
        422: {"model": ApiErrorResponse, "description": "Request validation failed"},
    },
)
async def get_session_alert_incident_summary(
    session_id: str,
    detector_id: str | None = None,
    severity: ApiAlertSeverity | None = None,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
) -> SessionIncidentSummaryResponse:
    """Return grouped incident summary data for one session.

    Like the other alert routes, this keeps transport concerns at the FastAPI
    boundary and delegates incident semantics to the shared alert service.
    """
    summary = _call_http_alert_service(
        build_session_incident_summary,
        session_id=session_id,
        detector_id=detector_id,
        severity=severity,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
    )
    return SessionIncidentSummaryResponse.model_validate(summary)
