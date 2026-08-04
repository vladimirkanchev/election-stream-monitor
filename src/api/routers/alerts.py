"""FastAPI adapters for bounded session-scoped alert query endpoints.

Keep raw alert-file reading, filtering, and numeric summary logic in
`session_alerts.py`, and keep grouped incident read models in
`session_alert_incidents.py`. This module stays focused on:

- query parameter binding
- response schema binding
- API-oriented error mapping

The route family is intentionally split into two read models over the same
shared service seam:

- raw alert-event list and raw numeric summary
- grouped incident timeline and grouped incident summary

The whole router is currently protected by the shared alert-route boundary
policy in `api/alert_route_policy.py`. That keeps authentication and rate
limiting at the HTTP boundary and out of the shared alert service modules.
"""

from fastapi import APIRouter, Depends

from api.alert_route_policy import ALERT_ROUTE_RESPONSES, require_http_alert_principal
from api.errors import (
    AlertQueryLimitExceededError,
    SessionNotFoundError,
    ValidationFailedError,
)
from api.schemas import (
    AlertTimestampFilter,
    ApiAlertSeverity,
    DetectorIdentifier,
    ReadPageLimit,
    ReadPageOffset,
    SessionAlertQueryResponse,
    SessionAlertSummaryResponse,
    SessionAlertTimelineResponse,
    SessionIdentifier,
    SessionIncidentSummaryResponse,
)
from read_resource_policy import DEFAULT_READ_PAGE_LIMIT, paginate_read_items
from session_alert_adapter import (
    AlertServiceCallable,
    build_alert_filter_kwargs,
    call_alert_service,
)
from session_alert_incidents import (
    build_session_incident_summary,
    build_session_timeline,
)
from session_alert_store import AlertReadLimitExceededError
from session_alerts import filter_session_alert_events, summarize_session_alert_events

# Router-level protection is intentionally attached here so all alert-query
# routes share the same auth and rate-limit boundary without repeating it per
# endpoint.
router = APIRouter(
    tags=["alerts"],
    dependencies=[Depends(require_http_alert_principal)],
)


def _call_http_alert_service[ServiceResult](
    service_fn: AlertServiceCallable[ServiceResult],
    *,
    session_id: str,
    detector_id: str | None,
    severity: ApiAlertSeverity | None,
    start_time_utc: str | None,
    end_time_utc: str | None,
) -> ServiceResult:
    """Call one shared alert service using the standard HTTP filter/error mapping.

    This keeps the individual route functions easy to scan: bind params, call
    the shared helper, then validate the structured response model. Unknown
    sessions and validation failures are mapped consistently across the raw and
    incident-oriented read models. The router intentionally stays unaware of
    auth and rate-limit mechanics because those already live in the shared
    alert-route boundary policy module.
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
    if isinstance(err, AlertReadLimitExceededError):
        return AlertQueryLimitExceededError(max_rows=err.max_rows)
    return ValidationFailedError(str(err))


@router.get(
    "/sessions/{session_id}/alerts",
    response_model=SessionAlertQueryResponse,
    responses=ALERT_ROUTE_RESPONSES,
)
async def get_session_alerts(
    session_id: SessionIdentifier,
    detector_id: DetectorIdentifier | None = None,
    severity: ApiAlertSeverity | None = None,
    start_time_utc: AlertTimestampFilter | None = None,
    end_time_utc: AlertTimestampFilter | None = None,
    limit: ReadPageLimit = DEFAULT_READ_PAGE_LIMIT,
    offset: ReadPageOffset = 0,
) -> SessionAlertQueryResponse:
    """Return one stable page of persisted alerts after optional filtering.

    This route is intentionally a thin adapter over the shared raw alert
    service. It owns HTTP parameter binding and HTTP-style error mapping, not
    alert-query semantics themselves.
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
            "alerts": paginate_read_items(alerts, limit=limit, offset=offset),
        }
    )


@router.get(
    "/sessions/{session_id}/alerts/summary",
    response_model=SessionAlertSummaryResponse,
    responses=ALERT_ROUTE_RESPONSES,
)
async def get_session_alert_summary(
    session_id: SessionIdentifier,
    detector_id: DetectorIdentifier | None = None,
    severity: ApiAlertSeverity | None = None,
    start_time_utc: AlertTimestampFilter | None = None,
    end_time_utc: AlertTimestampFilter | None = None,
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
    responses=ALERT_ROUTE_RESPONSES,
)
async def get_session_alert_timeline(
    session_id: SessionIdentifier,
    detector_id: DetectorIdentifier | None = None,
    severity: ApiAlertSeverity | None = None,
    start_time_utc: AlertTimestampFilter | None = None,
    end_time_utc: AlertTimestampFilter | None = None,
    limit: ReadPageLimit = DEFAULT_READ_PAGE_LIMIT,
    offset: ReadPageOffset = 0,
) -> SessionAlertTimelineResponse:
    """Return one stable page of grouped incident entries for one session.

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


@router.get(
    "/sessions/{session_id}/alerts/incident-summary",
    response_model=SessionIncidentSummaryResponse,
    responses=ALERT_ROUTE_RESPONSES,
)
async def get_session_alert_incident_summary(
    session_id: SessionIdentifier,
    detector_id: DetectorIdentifier | None = None,
    severity: ApiAlertSeverity | None = None,
    start_time_utc: AlertTimestampFilter | None = None,
    end_time_utc: AlertTimestampFilter | None = None,
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
