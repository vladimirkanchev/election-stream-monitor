"""Read-only session alert query helpers shared by API and MCP adapters.

This module intentionally stays transport-agnostic:

- no FastAPI request/response types
- no MCP manifests or tool registration
- no frontend-specific formatting

It builds on the existing session-file contract and exposes one shared,
session-scoped surface for:

- reading persisted raw alert rows
- filtering them with stable session query inputs
- summarizing raw alert counts
- grouping alert rows into incident-oriented timeline entries
- summarizing grouped incidents for operator- and MCP-facing read models
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
TIMELINE_GROUP_GAP_SECONDS = 60

logger = get_logger(__name__)
AlertEventPayload = dict[str, object]
AlertSummaryPayload = dict[str, object]
AlertTimelinePayload = dict[str, object]
IncidentSummaryPayload = dict[str, object]
IncidentAlertGroup = list[tuple[datetime, AlertEventPayload]]
SortableAlertEvent = tuple[datetime, int, AlertEventPayload]


class SessionAlertsNotFoundError(ValueError):
    """Raised when one requested session has no persisted metadata snapshot."""


# Public read/filter/summary surface


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

    The summary remains numeric and time-bound only. Natural-language
    explanation belongs in a higher-level MCP or agent workflow, not in the
    persisted alert-query service.
    """
    alerts = _read_filtered_session_alerts(
        session_id,
        detector_id=detector_id,
        severity=severity,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
    )
    return _build_alert_summary(session_id, alerts)


def build_session_timeline(
    session_id: str,
    *,
    detector_id: str | None = None,
    severity: str | None = None,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
) -> AlertTimelinePayload:
    """Return grouped incident entries built from filtered session alerts.

    The timeline stays deterministic and transport-agnostic:

    - one filtered alert path is reused for both HTTP and MCP adapters
    - incident grouping is rule-based rather than ML- or prose-driven
    - nearby alerts are grouped only when their stable fields still match
    - entries are ordered by grouped incident start time
    """
    alerts, incidents = _read_filtered_alerts_and_incidents(
        session_id,
        detector_id=detector_id,
        severity=severity,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
    )
    return {
        "session_id": session_id,
        "entries": [_build_timeline_entry(group) for group in incidents],
    }


def build_session_incident_summary(
    session_id: str,
    *,
    detector_id: str | None = None,
    severity: str | None = None,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
) -> IncidentSummaryPayload:
    """Return a grouped incident summary built from filtered session alerts.

    This summary is intentionally distinct from ``summarize_session_alert_events``.
    The older helper reports raw alert counts, while this helper reports grouped
    incident counts, top incident categories, and one optional short narrative
    field.
    """
    alerts, incidents = _read_filtered_alerts_and_incidents(
        session_id,
        detector_id=detector_id,
        severity=severity,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
    )
    return _build_incident_summary(
        session_id=session_id,
        alerts=alerts,
        incidents=incidents,
    )


# Shared internal read paths


def _read_filtered_session_alerts(
    session_id: str,
    *,
    detector_id: str | None = None,
    severity: str | None = None,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
) -> list[AlertEventPayload]:
    """Return filtered alerts through one shared internal read path."""
    return filter_session_alert_events(
        session_id,
        detector_id=detector_id,
        severity=severity,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
    )


def _read_filtered_alerts_and_incidents(
    session_id: str,
    *,
    detector_id: str | None = None,
    severity: str | None = None,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
) -> tuple[list[AlertEventPayload], list[IncidentAlertGroup]]:
    """Return filtered alerts plus their grouped incident view.

    Keeping this pairing in one helper makes the incident-oriented public
    functions read like small orchestration steps instead of repeating the same
    "filter, then group" flow inline.
    """
    alerts = _read_filtered_session_alerts(
        session_id,
        detector_id=detector_id,
        severity=severity,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
    )
    return alerts, _group_alerts_into_incidents(alerts)


# Persisted alert-log loading


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


# Timestamp parsing and filter matching


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
    """Return whether one alert payload satisfies the current query filters."""
    if detector_id is not None and alert.get("detector_id") != detector_id:
        return False
    if severity is not None and alert.get("severity") != severity:
        return False

    if start_time is None and end_time is None:
        return True

    alert_time = _read_alert_timestamp_or_none(alert)
    if alert_time is None:
        return False

    if start_time is not None and alert_time < start_time:
        return False
    if end_time is not None and alert_time > end_time:
        return False
    return True


def _read_alert_timestamp_or_none(alert: AlertEventPayload) -> datetime | None:
    """Return one parsed alert timestamp or ``None`` when the payload is unusable."""
    timestamp_utc = alert.get("timestamp_utc")
    if not isinstance(timestamp_utc, str):
        return None
    try:
        return _parse_alert_timestamp(timestamp_utc, field_name="alert.timestamp_utc")
    except ValueError:
        logger.warning("Ignoring alert with unparseable timestamp: %s", timestamp_utc)
        return None


# Timeline grouping


def _group_alerts_into_incidents(alerts: list[AlertEventPayload]) -> list[IncidentAlertGroup]:
    """Group compatible alerts into deterministic incident buckets.

    The current rule is intentionally simple: alerts belong to the same grouped
    incident when they share detector, severity, and title and arrive within one
    minute of the previous alert in that incident. This is deliberately simpler
    than coarse bucket grouping or detector-specific incident inference.
    """
    sortable_alerts = _collect_sortable_alerts(alerts)
    sortable_alerts.sort(key=lambda item: (item[0], item[1]))

    incidents: list[IncidentAlertGroup] = []
    current_group: IncidentAlertGroup = []
    for alert_time, _, alert in sortable_alerts:
        if not current_group:
            current_group = [(alert_time, alert)]
            continue

        previous_time, previous_alert = current_group[-1]
        if _alerts_belong_to_same_incident(
            previous_alert,
            alert,
            previous_time=previous_time,
            current_time=alert_time,
        ):
            current_group.append((alert_time, alert))
            continue

        incidents.append(current_group)
        current_group = [(alert_time, alert)]

    if current_group:
        incidents.append(current_group)

    return incidents


def _collect_sortable_alerts(alerts: list[AlertEventPayload]) -> list[SortableAlertEvent]:
    """Return timestamped rows that can safely participate in incident grouping."""
    sortable_alerts: list[SortableAlertEvent] = []
    for index, alert in enumerate(alerts):
        alert_time = _read_alert_timestamp_or_none(alert)
        if alert_time is None:
            continue
        sortable_alerts.append((alert_time, index, alert))
    return sortable_alerts


def _alerts_belong_to_same_incident(
    previous_alert: AlertEventPayload,
    current_alert: AlertEventPayload,
    *,
    previous_time: datetime,
    current_time: datetime,
) -> bool:
    """Return whether two alerts should collapse into one grouped incident."""
    if previous_alert.get("detector_id") != current_alert.get("detector_id"):
        return False
    if previous_alert.get("severity") != current_alert.get("severity"):
        return False
    if previous_alert.get("title") != current_alert.get("title"):
        return False
    return (current_time - previous_time).total_seconds() <= TIMELINE_GROUP_GAP_SECONDS


def _build_timeline_entry(group: IncidentAlertGroup) -> AlertEventPayload:
    """Convert one grouped incident into the stable timeline entry shape."""
    first_time, first_alert = group[0]
    last_time, _ = group[-1]
    return {
        "start_time_utc": first_time.strftime(ALERT_TIMESTAMP_FORMAT),
        "end_time_utc": last_time.strftime(ALERT_TIMESTAMP_FORMAT),
        "detector_id": first_alert["detector_id"],
        "severity": first_alert["severity"],
        "title": first_alert["title"],
        "alert_count": len(group),
        "source_names": _collect_unique_group_strings(group, field_name="source_name"),
        "sample_message": first_alert["message"],
    }


def _collect_unique_group_strings(
    group: IncidentAlertGroup,
    *,
    field_name: str,
) -> list[str]:
    """Return ordered unique string values from one incident group."""
    seen: set[str] = set()
    values: list[str] = []
    for _, alert in group:
        value = alert.get(field_name)
        if not isinstance(value, str) or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


# Summary builders


def _build_alert_summary(
    session_id: str,
    alerts: list[AlertEventPayload],
) -> AlertSummaryPayload:
    """Aggregate one filtered alert set into the stable summary shape."""
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

        alert_time = _read_alert_timestamp_or_none(alert)
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


def _build_incident_summary(
    *,
    session_id: str,
    alerts: list[AlertEventPayload],
    incidents: list[IncidentAlertGroup],
) -> IncidentSummaryPayload:
    """Aggregate filtered alerts into the grouped incident summary shape.

    The grouped summary intentionally keeps the raw alert summary as its base
    truth, then layers grouped-incident counts and the optional narrative field
    on top. That keeps the numeric contract stable across FastAPI and MCP even
    if the narrative wording evolves later.
    """
    base_summary = _build_alert_summary(session_id, alerts)
    top_incident_categories = _count_incident_categories(incidents)
    return {
        **base_summary,
        "total_incidents": len(incidents),
        "top_incident_categories": top_incident_categories,
        "narrative_summary": _build_narrative_summary(
            session_id=session_id,
            alerts=alerts,
            incidents=incidents,
            counts_by_detector=base_summary["counts_by_detector"],
            counts_by_severity=base_summary["counts_by_severity"],
            top_incident_categories=top_incident_categories,
        ),
    }


def _count_incident_categories(
    incidents: list[IncidentAlertGroup],
) -> dict[str, int]:
    """Count grouped incidents by their stable title field."""
    counts: Counter[str] = Counter()
    for group in incidents:
        _, first_alert = group[0]
        title = first_alert.get("title")
        if isinstance(title, str):
            counts[title] += 1
    return dict(counts)


def _build_narrative_summary(
    *,
    session_id: str,
    alerts: list[AlertEventPayload],
    incidents: list[IncidentAlertGroup],
    counts_by_detector: dict[str, int],
    counts_by_severity: dict[str, int],
    top_incident_categories: dict[str, int],
) -> str:
    """Build one short operator-friendly sentence over the grouped results.

    The sentence is deliberately a convenience field rather than the source of
    truth. Tests and callers should rely on the structured counts first and use
    the narrative only as a compact human-facing summary.
    """
    if not alerts:
        return f"Session {session_id} had no alerts."

    if not incidents:
        alert_label = "alert" if len(alerts) == 1 else "alerts"
        return (
            f"Session {session_id} had {len(alerts)} {alert_label} but no grouped incidents with "
            "valid timestamps."
        )

    dominant_detector = max(
        counts_by_detector.items(),
        key=lambda item: (item[1], item[0]),
    )[0]
    warning_count = counts_by_severity.get("warning", 0)
    info_count = counts_by_severity.get("info", 0)
    top_category = max(
        top_incident_categories.items(),
        key=lambda item: (item[1], item[0]),
    )[0]
    return (
        f"Session {session_id} had {len(incidents)} grouped incidents across "
        f"{len(alerts)} alerts, mostly from {dominant_detector}, led by "
        f"{top_category.lower()}, with "
        f"{warning_count} warning alerts and {info_count} info alerts."
    )
