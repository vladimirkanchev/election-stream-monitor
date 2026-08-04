"""Read-only raw alert-query services shared by API and MCP adapters.

This module intentionally stays transport-agnostic and focused on the raw
persisted alert seam:

- read persisted alert rows for one session
- filter those rows with stable query inputs
- build deterministic raw alert summaries

Grouped timeline and incident-summary behavior lives in
`session_alert_incidents.py` so the raw alert path stays smaller and easier to
scan. The public entrypoints in this module accept an optional alert store seam
while still defaulting to the runtime-selected alert store.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import TypedDict

from logger import get_logger
from read_resource_policy import MAX_ALERT_QUERY_ROWS
from session_alert_store import (
    DEFAULT_SESSION_ALERT_STORE,
    AlertEventPayload,
    SessionAlertsNotFoundError,
    SessionAlertStore,
)

ALERT_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

logger = get_logger(__name__)
__all__ = [
    "ALERT_TIMESTAMP_FORMAT",
    "AlertSummaryPayload",
    "SessionAlertsNotFoundError",
    "build_alert_summary_payload",
    "filter_session_alert_events",
    "read_alert_timestamp_or_none",
    "read_session_alert_events",
    "summarize_session_alert_events",
]


class AlertSummaryPayload(TypedDict):
    """Stable numeric summary returned by the raw alert-query service."""

    session_id: str
    total_alerts: int
    counts_by_detector: dict[str, int]
    counts_by_severity: dict[str, int]
    first_alert_timestamp_utc: str | None
    last_alert_timestamp_utc: str | None


def read_session_alert_events(
    session_id: str,
    *,
    store: SessionAlertStore = DEFAULT_SESSION_ALERT_STORE,
    max_rows: int | None = None,
) -> list[AlertEventPayload]:
    """Return persisted alert events for one known session.

    Query semantics intentionally mirror the broader session snapshot layer:

    - missing `session.json` means the session is not known
    - missing `alerts.jsonl` on a known session means no persisted alerts yet
    - malformed alert rows are ignored instead of failing the whole read

    The optional store seam keeps the current default backend behind one stable
    read-model path while letting alternate alert stores reuse the same query
    logic. ``max_rows`` is used by bounded query services; direct callers may
    omit it when they need the full durable history.
    """
    return store.read_session_alert_events(session_id, max_rows=max_rows)


def filter_session_alert_events(
    session_id: str,
    *,
    detector_id: str | None = None,
    severity: str | None = None,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
    store: SessionAlertStore = DEFAULT_SESSION_ALERT_STORE,
) -> list[AlertEventPayload]:
    """Return persisted alerts that match the requested session-scoped filters.

    Filters are deliberately limited to the current persisted alert contract so
    the same helper can back both HTTP and MCP query surfaces without leaking
    transport-specific semantics into the service layer. The storage seam stays
    limited to fetching validated raw alert rows.
    """
    alerts = read_session_alert_events(
        session_id,
        store=store,
        max_rows=MAX_ALERT_QUERY_ROWS,
    )
    start_time, end_time = _parse_time_range(
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
    )
    return [
        alert
        for alert in alerts
        if _matches_alert_filters(
            alert,
            detector_id=detector_id,
            severity=severity,
            start_time=start_time,
            end_time=end_time,
        )
    ]


def summarize_session_alert_events(
    session_id: str,
    *,
    detector_id: str | None = None,
    severity: str | None = None,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
    store: SessionAlertStore = DEFAULT_SESSION_ALERT_STORE,
) -> AlertSummaryPayload:
    """Return a deterministic summary of one session's filtered alert events.

    This is the raw alert summary read model. It intentionally stays separate
    from the grouped incident summary in `session_alert_incidents.py`, even
    when the underlying alert rows come from a different store implementation.
    """
    alerts = filter_session_alert_events(
        session_id,
        detector_id=detector_id,
        severity=severity,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
        store=store,
    )
    return build_alert_summary_payload(session_id, alerts)


def build_alert_summary_payload(
    session_id: str,
    alerts: list[AlertEventPayload],
) -> AlertSummaryPayload:
    """Aggregate one filtered alert set into the stable raw summary shape.

    This helper stays public because the grouped incident module reuses the raw
    summary as its numeric base truth.
    """
    counts_by_detector, counts_by_severity, parsed_times = _collect_alert_summary_parts(alerts)
    first_alert, last_alert = _summarize_alert_time_bounds(parsed_times)
    return {
        "session_id": session_id,
        "total_alerts": len(alerts),
        "counts_by_detector": dict(counts_by_detector),
        "counts_by_severity": dict(counts_by_severity),
        "first_alert_timestamp_utc": first_alert,
        "last_alert_timestamp_utc": last_alert,
    }


def _collect_alert_summary_parts(
    alerts: list[AlertEventPayload],
) -> tuple[Counter[str], Counter[str], list[datetime]]:
    """Collect the reusable pieces needed by the raw alert summary model.

    Keeping this separate makes the public summary builder easier to scan while
    preserving the current one-pass aggregation over detector counts, severity
    counts, and valid alert timestamps.
    """
    counts_by_detector: Counter[str] = Counter()
    counts_by_severity: Counter[str] = Counter()
    parsed_times: list[datetime] = []

    for alert in alerts:
        counts_by_detector[alert["detector_id"]] += 1
        counts_by_severity[alert["severity"]] += 1
        alert_time = read_alert_timestamp_or_none(alert)
        if alert_time is not None:
            parsed_times.append(alert_time)

    return counts_by_detector, counts_by_severity, parsed_times


def _summarize_alert_time_bounds(
    parsed_times: list[datetime],
) -> tuple[str | None, str | None]:
    """Return formatted first/last timestamps for one filtered alert set."""
    if not parsed_times:
        return None, None
    return (
        min(parsed_times).strftime(ALERT_TIMESTAMP_FORMAT),
        max(parsed_times).strftime(ALERT_TIMESTAMP_FORMAT),
    )


def read_alert_timestamp_or_none(alert: AlertEventPayload) -> datetime | None:
    """Return one parsed alert timestamp or ``None`` when the payload is unusable.

    This helper stays public because the grouped incident module shares the
    same persisted alert row contract and should not duplicate timestamp
    parsing or warning behavior.
    """
    try:
        return _parse_alert_timestamp(alert["timestamp_utc"], field_name="alert.timestamp_utc")
    except ValueError:
        logger.warning("Ignoring alert with unparseable timestamp: %s", alert["timestamp_utc"])
        return None


def _parse_time_range(
    *,
    start_time_utc: str | None,
    end_time_utc: str | None,
) -> tuple[datetime | None, datetime | None]:
    """Parse and validate one optional inclusive UTC time range."""
    start_time = _parse_optional_timestamp(start_time_utc, field_name="start_time_utc")
    end_time = _parse_optional_timestamp(end_time_utc, field_name="end_time_utc")
    if start_time is not None and end_time is not None and start_time > end_time:
        raise ValueError("start_time_utc must be earlier than or equal to end_time_utc")
    return start_time, end_time


def _parse_optional_timestamp(
    timestamp_utc: str | None,
    *,
    field_name: str,
) -> datetime | None:
    """Parse one optional UTC timestamp using the persisted alert time format."""
    if timestamp_utc is None:
        return None
    return _parse_alert_timestamp(timestamp_utc, field_name=field_name)


def _parse_alert_timestamp(timestamp_utc: str, *, field_name: str) -> datetime:
    """Parse one persisted alert timestamp or raise a validation-style error."""
    try:
        return datetime.strptime(timestamp_utc, ALERT_TIMESTAMP_FORMAT)
    except ValueError as err:
        raise ValueError(
            f"{field_name} must use UTC timestamp format {ALERT_TIMESTAMP_FORMAT!r}"
        ) from err


def _matches_alert_filters(
    alert: AlertEventPayload,
    *,
    detector_id: str | None,
    severity: str | None,
    start_time: datetime | None,
    end_time: datetime | None,
) -> bool:
    """Return whether one alert payload satisfies the current query filters.

    Time filtering is inclusive on both ends. Alerts with unusable persisted
    timestamps are excluded from time-bound queries rather than failing the
    whole read.
    """
    if detector_id is not None and alert["detector_id"] != detector_id:
        return False
    if severity is not None and alert["severity"] != severity:
        return False

    if start_time is None and end_time is None:
        return True

    alert_time = read_alert_timestamp_or_none(alert)
    if alert_time is None:
        return False

    if start_time is not None and alert_time < start_time:
        return False
    if end_time is not None and alert_time > end_time:
        return False
    return True
