"""Shared helpers for grouped-incident service tests.

This module keeps only the seams reused across the timeline and summary
service suites:
- typed accessors for grouped timeline and summary payloads
- stable empty-result assertions
- small wrappers for time-filter validation
- one-row grouped-session setup reused by filter-focused tests

The service behavior itself stays in the surrounding test modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from session_alert_incidents import (
    AlertTimelineEntryPayload,
    AlertTimelinePayload,
    IncidentSummaryPayload,
    build_session_incident_summary,
    build_session_timeline,
)
from tests.session_alert_test_support import (
    build_incident_summary_payload,
    build_persisted_alert,
    write_known_session,
)

TimelinePayload = AlertTimelinePayload


def timeline_entries(timeline: TimelinePayload) -> list[AlertTimelineEntryPayload]:
    """Return grouped timeline entries through one typed cast at the helper seam."""
    return cast(list[AlertTimelineEntryPayload], timeline["entries"])


def timeline_titles(timeline: TimelinePayload) -> list[object]:
    """Return grouped incident titles in response order for compact assertions."""
    return [entry["title"] for entry in timeline_entries(timeline)]


def build_timeline_with_time_filters(
    session_id: str,
    *,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
) -> TimelinePayload:
    """Call the grouped timeline service with only the time-filter seam exposed."""
    return build_session_timeline(
        session_id,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
    )


def assert_single_timeline_entry(
    timeline: TimelinePayload,
    *,
    expected_entry: AlertTimelineEntryPayload,
) -> None:
    """Assert the full one-entry grouped timeline contract in one readable check."""
    assert timeline == {
        "session_id": timeline["session_id"],
        "entries": [expected_entry],
    }


def assert_empty_timeline(timeline: TimelinePayload, session_id: str) -> None:
    """Assert the stable grouped timeline contract for an empty result."""
    assert timeline == {
        "session_id": session_id,
        "entries": [],
    }


def summary_narrative(summary: IncidentSummaryPayload) -> str:
    """Return the grouped summary narrative through one typed access point."""
    return cast(str, summary["narrative_summary"])


def assert_empty_incident_summary(
    summary: IncidentSummaryPayload, session_id: str
) -> None:
    """Assert the stable grouped incident summary contract for an empty result."""
    assert summary == build_incident_summary_payload(
        session_id,
        total_alerts=0,
        total_incidents=0,
        counts_by_detector={},
        counts_by_severity={},
        top_incident_categories={},
        first_alert_timestamp_utc=None,
        last_alert_timestamp_utc=None,
        narrative_summary=f"Session {session_id} had no alerts.",
    )


def single_time_filter_kwargs(filter_name: str, filter_value: str) -> dict[str, str]:
    """Build one-key kwargs for invalid-time parametrization without inline branching."""
    return {filter_name: filter_value}


def write_single_grouped_alert_session(
    session_root: Path,
    session_id: str,
    *,
    timestamp_utc: str = "2026-05-06 10:00:00",
    detector_id: str = "video_metrics",
    title: str = "Black screen detected",
    message: str = "Known grouped row.",
    severity: str = "warning",
    source_name: str = "segment_0001.ts",
) -> None:
    """Write one known session with a single valid grouped-alert row."""
    write_known_session(
        session_root,
        session_id,
        alert_rows=[
            build_persisted_alert(
                session_id,
                timestamp_utc=timestamp_utc,
                detector_id=detector_id,
                title=title,
                message=message,
                severity=severity,
                source_name=source_name,
            )
        ],
    )


def build_incident_summary_with_time_filters(
    session_id: str,
    *,
    start_time_utc: str | None = None,
    end_time_utc: str | None = None,
    detector_id: str | None = None,
    severity: str | None = None,
) -> IncidentSummaryPayload:
    """Call the grouped summary service with only filter inputs exposed."""
    return build_session_incident_summary(
        session_id,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
        detector_id=detector_id,
        severity=severity,
    )
