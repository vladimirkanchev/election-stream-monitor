"""Grouped incident read models built on top of filtered persisted session alerts.

This module intentionally owns only the incident-oriented layer:

- deterministic timeline grouping
- grouped incident summaries
- one short narrative convenience field

The raw alert read/filter/summary logic stays in `session_alerts.py` so the
two read-model families remain easier to reason about independently. This
module is the source of truth for the deterministic grouping rule used by both
the FastAPI incident routes and the MCP incident tools.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from session_alerts import (
    ALERT_TIMESTAMP_FORMAT,
    AlertEventPayload,
    build_alert_summary_payload,
    filter_session_alert_events,
    read_alert_timestamp_or_none,
)

TIMELINE_GROUP_GAP_SECONDS = 60

AlertTimelinePayload = dict[str, object]
IncidentSummaryPayload = dict[str, object]
IncidentAlertGroup = list[tuple[datetime, AlertEventPayload]]
SortableAlertEvent = tuple[datetime, int, AlertEventPayload]


def build_session_timeline(
    session_id: str,
    *,
    detector_id: str | None = None,
    severity: str | None = None,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
) -> AlertTimelinePayload:
    """Return grouped incident entries built from filtered session alerts.

    The timeline stays transport-agnostic and deterministic: it always starts
    from the shared raw alert filter path and then applies one stable grouping
    rule over the resulting alert rows.
    """
    alerts = filter_session_alert_events(
        session_id,
        detector_id=detector_id,
        severity=severity,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
    )
    incidents = _group_alerts_into_incidents(alerts)
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

    The grouped summary reuses the raw numeric summary as its base truth, then
    layers grouped-incident counts, top categories, and one short narrative
    convenience field on top.
    """
    alerts = filter_session_alert_events(
        session_id,
        detector_id=detector_id,
        severity=severity,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
    )
    incidents = _group_alerts_into_incidents(alerts)
    base_summary = build_alert_summary_payload(session_id, alerts)
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


def _group_alerts_into_incidents(alerts: list[AlertEventPayload]) -> list[IncidentAlertGroup]:
    """Group compatible alerts into deterministic incident buckets.

    The current rule is intentionally simple: alerts belong to the same grouped
    incident when they share detector, severity, and title and arrive within
    one minute of the previous alert in that incident.
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
        alert_time = read_alert_timestamp_or_none(alert)
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

    This sentence is a convenience field for operators and MCP clients. The
    structured counts remain the source of truth for tests and downstream code.
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
