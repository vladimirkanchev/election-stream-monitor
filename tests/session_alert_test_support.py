"""Small helpers for the alert persistence seam test layer.

The helpers here keep the Task-1 seam tests explicit while avoiding repeated
JSONL setup and payload boilerplate across raw, grouped, API, and MCP tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import config
import pytest
from session_alert_incidents import AlertTimelineEntryPayload, IncidentSummaryPayload
from session_alerts import AlertSummaryPayload
from session_alert_store import AlertEventPayload, SessionAlertStore
from session_models import AlertEvent, EventSeverity

AlertPayload = dict[str, object]
AlertLogRow = AlertPayload | str


class StaticAlertStore(SessionAlertStore):
    """Tiny read-only store used to prove the injected seam is honored."""

    def __init__(self, session_id: str, alerts: list[AlertEventPayload]) -> None:
        """Keep one fixed alert set available for one expected session."""
        self._session_id = session_id
        self._alerts = alerts

    def append_alert(self, event: AlertEvent) -> None:  # pragma: no cover - defensive only
        """Reject writes so the helper stays read-only by design."""
        raise AssertionError("append_alert should not be called in read-only seam tests")

    def read_session_alert_events(self, session_id: str) -> list[AlertEventPayload]:
        """Return the fixed alert set for the expected seam test session."""
        assert session_id == self._session_id
        return self._alerts


def configure_session_alert_test(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point one test at an isolated temporary session-output root."""
    monkeypatch.setattr(config, "SESSION_OUTPUT_FOLDER", tmp_path)
    return tmp_path


def build_persisted_alert(
    session_id: str,
    *,
    timestamp_utc: str,
    detector_id: str,
    title: str,
    message: str,
    severity: str,
    source_name: str,
    window_index: int | None = None,
    window_start_sec: float | None = None,
) -> AlertPayload:
    """Build one alert row in its persisted JSONL shape."""
    alert: AlertPayload = {
        "session_id": session_id,
        "timestamp_utc": timestamp_utc,
        "detector_id": detector_id,
        "title": title,
        "message": message,
        "severity": severity,
        "source_name": source_name,
    }
    if window_index is not None:
        alert["window_index"] = window_index
    if window_start_sec is not None:
        alert["window_start_sec"] = window_start_sec
    return alert


def build_normalized_alert(
    session_id: str,
    *,
    timestamp_utc: str,
    detector_id: str,
    title: str,
    message: str,
    severity: str,
    source_name: str,
    window_index: int | None = None,
    window_start_sec: float | None = None,
) -> AlertEventPayload:
    """Build one alert row in the normalized read/query shape."""
    alert = build_persisted_alert(
        session_id,
        timestamp_utc=timestamp_utc,
        detector_id=detector_id,
        title=title,
        message=message,
        severity=severity,
        source_name=source_name,
        window_index=window_index,
        window_start_sec=window_start_sec,
    )
    alert.setdefault("window_index", None)
    alert.setdefault("window_start_sec", None)
    return cast(AlertEventPayload, alert)


def build_timeline_entry(
    *,
    start_time_utc: str,
    end_time_utc: str,
    detector_id: str,
    severity: EventSeverity,
    title: str,
    alert_count: int,
    source_names: list[str],
    sample_message: str,
) -> AlertTimelineEntryPayload:
    """Build one grouped timeline entry in the shared response shape."""
    return {
        "start_time_utc": start_time_utc,
        "end_time_utc": end_time_utc,
        "detector_id": detector_id,
        "severity": severity,
        "title": title,
        "alert_count": alert_count,
        "source_names": source_names,
        "sample_message": sample_message,
    }


def build_alert_summary_payload(
    session_id: str,
    *,
    total_alerts: int,
    counts_by_detector: dict[str, int],
    counts_by_severity: dict[str, int],
    first_alert_timestamp_utc: str | None,
    last_alert_timestamp_utc: str | None,
) -> AlertSummaryPayload:
    """Build the stable raw alert-summary payload."""
    return {
        "session_id": session_id,
        "total_alerts": total_alerts,
        "counts_by_detector": counts_by_detector,
        "counts_by_severity": counts_by_severity,
        "first_alert_timestamp_utc": first_alert_timestamp_utc,
        "last_alert_timestamp_utc": last_alert_timestamp_utc,
    }


def build_incident_summary_payload(
    session_id: str,
    *,
    total_alerts: int,
    total_incidents: int,
    counts_by_detector: dict[str, int],
    counts_by_severity: dict[str, int],
    top_incident_categories: dict[str, int],
    first_alert_timestamp_utc: str | None,
    last_alert_timestamp_utc: str | None,
    narrative_summary: str,
) -> IncidentSummaryPayload:
    """Build the grouped incident-summary payload."""
    return {
        **build_alert_summary_payload(
            session_id,
            total_alerts=total_alerts,
            counts_by_detector=counts_by_detector,
            counts_by_severity=counts_by_severity,
            first_alert_timestamp_utc=first_alert_timestamp_utc,
            last_alert_timestamp_utc=last_alert_timestamp_utc,
        ),
        "total_incidents": total_incidents,
        "top_incident_categories": top_incident_categories,
        "narrative_summary": narrative_summary,
    }


def assert_narrative_contains(narrative: str | None, *parts: str) -> None:
    """Assert that a narrative summary still carries the important facts."""
    assert narrative is not None
    for part in parts:
        assert part in narrative


def write_known_session(
    session_root: Path,
    session_id: str,
    *,
    alert_rows: list[AlertLogRow] | None = None,
) -> Path:
    """Create the minimal known session used by the alert seam tests."""
    session_dir = session_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "session.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "mode": "video_segments",
                "input_path": "/tmp/input",
                "selected_detectors": ["video_metrics"],
                "status": "running",
            }
        ),
        encoding="utf-8",
    )
    if alert_rows is not None:
        write_alert_log(session_dir, alert_rows)
    return session_dir


def write_alert_log(session_dir: Path, rows: list[AlertLogRow]) -> None:
    """Write one alert log from payload rows or intentionally invalid strings."""
    encoded_rows = [
        row if isinstance(row, str) else json.dumps(row)
        for row in rows
    ]
    (session_dir / "alerts.jsonl").write_text(
        "\n".join(encoded_rows),
        encoding="utf-8",
    )
