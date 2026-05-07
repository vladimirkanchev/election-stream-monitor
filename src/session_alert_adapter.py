"""Shared adapter helpers for alert-query transport layers.

The FastAPI and MCP surfaces intentionally stay as thin wrappers over
``session_alerts.py``. They still share two small pieces of mechanics:

- collecting the optional filter arguments into one stable kwargs shape
- translating shared-service domain failures into transport-specific errors

Keeping that logic here reduces small duplication without hiding the HTTP and
MCP adapters behind a larger abstraction.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, TypedDict

from session_alerts import SessionAlertsNotFoundError


class AlertFilterKwargs(TypedDict):
    """Shared optional filter kwargs accepted by the alert-query service."""

    detector_id: str | None
    severity: str | None
    start_time_utc: str | None
    end_time_utc: str | None


ServiceReturn = TypeVar("ServiceReturn")


def build_alert_filter_kwargs(
    *,
    detector_id: str | None,
    severity: str | None,
    start_time_utc: str | None,
    end_time_utc: str | None,
) -> AlertFilterKwargs:
    """Return one stable kwargs payload for the shared alert-query service."""
    return {
        "detector_id": detector_id,
        "severity": severity,
        "start_time_utc": start_time_utc,
        "end_time_utc": end_time_utc,
    }


def call_alert_service(
    service_fn: Callable[..., ServiceReturn],
    *,
    session_id: str,
    filter_kwargs: AlertFilterKwargs,
    map_not_found: Callable[[str], Exception],
    map_validation_error: Callable[[ValueError], Exception],
) -> ServiceReturn:
    """Call one shared alert service and map domain errors for one transport.

    The shared alert service raises domain-level failures:

    - ``SessionAlertsNotFoundError`` for unknown sessions
    - ``ValueError`` for invalid filter inputs or invalid persisted timestamps

    The adapters decide how those failures should surface to their callers.
    """
    try:
        return service_fn(session_id, **filter_kwargs)
    except SessionAlertsNotFoundError as err:
        raise map_not_found(session_id) from err
    except ValueError as err:
        raise map_validation_error(err) from err
