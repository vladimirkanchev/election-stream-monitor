"""Read-only raw session alert query helpers shared by API and MCP adapters.

This module intentionally stays transport-agnostic and focused on the raw
persisted alert seam:

- read persisted alert rows for one session
- filter those rows with stable query inputs
- build deterministic raw alert summaries

Grouped timeline and incident-summary behavior lives in
`session_alert_incidents.py` so the raw alert path stays smaller and easier to
scan. This module is the source of truth for the persisted alert row contract
and for the deterministic raw numeric summary built on top of it.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from pathlib import Path

from logger import get_logger
from session_io import get_session_dir, session_exists
from session_models import parse_alert_event_payload

ALERT_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

logger = get_logger(__name__)
AlertEventPayload = dict[str, object]
AlertSummaryPayload = dict[str, object]


class SessionAlertsNotFoundError(ValueError):
    """Raised when one requested session has no persisted metadata snapshot."""


def read_session_alert_events(session_id: str) -> list[AlertEventPayload]:
    """Return persisted alert events for one known session.

    Query semantics intentionally mirror the broader session snapshot layer:

    - missing `session.json` means the session is not known
    - missing `alerts.jsonl` on a known session means no persisted alerts yet
    - malformed alert rows are ignored instead of failing the whole read
    """
    return _read_alert_jsonl(_get_alerts_file_path(session_id))


def filter_session_alert_events(
    session_id: str,
    *,
    detector_id: str | None = None,
    severity: str | None = None,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
) -> list[AlertEventPayload]:
    """Return persisted alerts that match the requested session-scoped filters.

    Filters are deliberately limited to the current persisted alert contract so
    the same helper can back both HTTP and MCP query surfaces without leaking
    transport-specific semantics into the service layer.
    """
    alerts = read_session_alert_events(session_id)
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
) -> AlertSummaryPayload:
    """Return a deterministic summary of one session's filtered alert events.

    This is the raw alert summary read model. It intentionally stays separate
    from the grouped incident summary in `session_alert_incidents.py`.
    """
    alerts = filter_session_alert_events(
        session_id,
        detector_id=detector_id,
        severity=severity,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
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
    counts_by_detector: Counter[str] = Counter()
    counts_by_severity: Counter[str] = Counter()
    parsed_times: list[datetime] = []

    for alert in alerts:
        detector_id = alert.get("detector_id")
        if isinstance(detector_id, str):
            counts_by_detector[detector_id] += 1

        severity = alert.get("severity")
        if isinstance(severity, str):
            counts_by_severity[severity] += 1

        alert_time = read_alert_timestamp_or_none(alert)
        if alert_time is not None:
            parsed_times.append(alert_time)

    first_alert = min(parsed_times).strftime(ALERT_TIMESTAMP_FORMAT) if parsed_times else None
    last_alert = max(parsed_times).strftime(ALERT_TIMESTAMP_FORMAT) if parsed_times else None
    return {
        "session_id": session_id,
        "total_alerts": len(alerts),
        "counts_by_detector": dict(counts_by_detector),
        "counts_by_severity": dict(counts_by_severity),
        "first_alert_timestamp_utc": first_alert,
        "last_alert_timestamp_utc": last_alert,
    }


def read_alert_timestamp_or_none(alert: AlertEventPayload) -> datetime | None:
    """Return one parsed alert timestamp or ``None`` when the payload is unusable.

    This helper stays public because the grouped incident module shares the
    same persisted alert row contract and should not duplicate timestamp
    parsing or warning behavior.
    """
    timestamp_utc = alert.get("timestamp_utc")
    if not isinstance(timestamp_utc, str):
        return None
    try:
        return _parse_alert_timestamp(timestamp_utc, field_name="alert.timestamp_utc")
    except ValueError:
        logger.warning("Ignoring alert with unparseable timestamp: %s", timestamp_utc)
        return None


def _get_alerts_file_path(session_id: str) -> Path:
    """Return the persisted alert log path for one known session."""
    if not session_exists(session_id):
        raise SessionAlertsNotFoundError(session_id)
    return get_session_dir(session_id) / "alerts.jsonl"


def _read_alert_jsonl(file_path: Path) -> list[AlertEventPayload]:
    """Read one JSONL alert log and ignore malformed rows safely."""
    if not file_path.exists():
        return []

    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        logger.warning("Ignoring unreadable alert log: %s", file_path)
        return []

    alerts: list[AlertEventPayload] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("Ignoring unreadable alert line: %s:%d", file_path, line_number)
            continue
        parsed = parse_alert_event_payload(payload)
        if parsed is None:
            logger.warning("Ignoring malformed alert line: %s:%d", file_path, line_number)
            continue
        alerts.append(parsed)
    return alerts


def _parse_time_range(
    *,
    start_time_utc: str | None,
    end_time_utc: str | None,
) -> tuple[datetime | None, datetime | None]:
    """Parse and validate an optional inclusive time range."""
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
    """Parse one optional timestamp using the persisted alert time format."""
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
    if detector_id is not None and alert.get("detector_id") != detector_id:
        return False
    if severity is not None and alert.get("severity") != severity:
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
