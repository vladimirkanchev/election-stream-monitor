"""Focused seam tests for the shared alert-query transport adapter helpers.

These tests stay intentionally small. The raw alert and grouped incident
services already have broad behavior coverage elsewhere; this file only locks
the adapter mechanics that FastAPI and MCP share:

- stable filter-kwargs shaping
- service-call forwarding
- domain-error mapping for unknown sessions and validation failures
"""

from __future__ import annotations

import pytest

from session_alert_adapter import (
    AlertFilterKwargs,
    build_alert_filter_kwargs,
    call_alert_service,
)
from session_alerts import SessionAlertsNotFoundError

DEFAULT_FILTER_KWARGS: AlertFilterKwargs = {
    "detector_id": "video_metrics",
    "severity": "warning",
    "start_time_utc": "2026-05-06 10:00:00",
    "end_time_utc": "2026-05-06 10:05:00",
}
EMPTY_FILTER_KWARGS: AlertFilterKwargs = {
    "detector_id": None,
    "severity": None,
    "start_time_utc": None,
    "end_time_utc": None,
}


def _runtime_error_not_found_mapper(session_id: str) -> RuntimeError:
    """Return the small runtime error shape used by the adapter seam tests."""
    return RuntimeError(f"missing:{session_id}")


def _runtime_error_validation_mapper(err: ValueError) -> RuntimeError:
    """Return the small validation error shape used by the adapter seam tests."""
    return RuntimeError(str(err))


def test_build_alert_filter_kwargs_preserves_the_shared_filter_shape() -> None:
    """The adapter should keep one stable kwargs bundle for both transports."""
    open_ended_filter_kwargs: AlertFilterKwargs = {
        **DEFAULT_FILTER_KWARGS,
        "end_time_utc": None,
    }
    assert build_alert_filter_kwargs(
        detector_id=open_ended_filter_kwargs["detector_id"],
        severity=open_ended_filter_kwargs["severity"],
        start_time_utc=open_ended_filter_kwargs["start_time_utc"],
        end_time_utc=open_ended_filter_kwargs["end_time_utc"],
    ) == open_ended_filter_kwargs


def test_call_alert_service_forwards_session_id_and_filter_kwargs() -> None:
    """The shared adapter should stay a thin forwarding seam on the happy path."""
    observed: dict[str, object] = {}

    def fake_service(
        session_id: str,
        *,
        detector_id: str | None = None,
        severity: str | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
    ) -> dict[str, object]:
        observed.update(
            {
                "session_id": session_id,
                "detector_id": detector_id,
                "severity": severity,
                "start_time_utc": start_time_utc,
                "end_time_utc": end_time_utc,
            }
        )
        return {"ok": True}

    result = call_alert_service(
        fake_service,
        session_id="session-123",
        filter_kwargs=DEFAULT_FILTER_KWARGS,
        map_not_found=_runtime_error_not_found_mapper,
        map_validation_error=_runtime_error_validation_mapper,
    )

    assert result == {"ok": True}
    assert observed == {
        "session_id": "session-123",
        **DEFAULT_FILTER_KWARGS,
    }


def test_call_alert_service_maps_unknown_session_errors() -> None:
    """Unknown-session service failures should be translated by the transport mapper."""

    def missing_service(
        session_id: str,
        **_: object,
    ) -> list[dict[str, object]]:
        raise SessionAlertsNotFoundError(session_id)

    with pytest.raises(RuntimeError, match="missing:missing-session"):
        call_alert_service(
            missing_service,
            session_id="missing-session",
            filter_kwargs=EMPTY_FILTER_KWARGS,
            map_not_found=_runtime_error_not_found_mapper,
            map_validation_error=_runtime_error_validation_mapper,
        )


def test_call_alert_service_maps_validation_errors() -> None:
    """Validation failures should also be translated by the transport mapper."""

    def invalid_service(
        session_id: str,
        **_: object,
    ) -> dict[str, object]:
        raise ValueError(f"bad range for {session_id}")

    with pytest.raises(RuntimeError, match="bad range for session-123"):
        call_alert_service(
            invalid_service,
            session_id="session-123",
            filter_kwargs=build_alert_filter_kwargs(
                detector_id=EMPTY_FILTER_KWARGS["detector_id"],
                severity=EMPTY_FILTER_KWARGS["severity"],
                start_time_utc="2026-05-06 10:10:00",
                end_time_utc="2026-05-06 10:00:00",
            ),
            map_not_found=_runtime_error_not_found_mapper,
            map_validation_error=_runtime_error_validation_mapper,
        )
