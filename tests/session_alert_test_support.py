"""Shared support helpers for session alert query tests.

These helpers keep the alert-query tests focused on scenario intent:

- isolate one temporary session-output root
- create a minimal persisted session snapshot
- write alert JSONL rows, including intentionally invalid lines
- build alert payloads without repeating the contract shape inline

The module stays small and procedural on purpose. It removes setup noise
without hiding test meaning behind a framework, and it supports both the raw
alert read model and the grouped incident read models that sit on top of it.
"""

from __future__ import annotations

import json
from pathlib import Path

import config
import pytest

AlertPayload = dict[str, object]
AlertLogRow = AlertPayload | str


def configure_session_alert_test(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Redirect one alert-query test into isolated temporary session state.

    Returning the configured root keeps the callers explicit about where
    session directories are created instead of hiding filesystem ownership
    inside a fixture with more implicit behavior.
    """
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
    """Build one alert payload as it would be persisted to JSONL.

    This shape intentionally omits normalized defaults so tests can distinguish
    persisted rows from the read/query payload returned after parsing.
    """
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
) -> AlertPayload:
    """Build one alert payload in the normalized read/query response shape.

    The service layer normalizes optional window fields to explicit ``None``
    values, so callers can compare full payloads without repeating that detail
    in every assertion.
    """
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
    return alert


def build_timeline_entry(
    *,
    start_time_utc: str,
    end_time_utc: str,
    detector_id: str,
    severity: str,
    title: str,
    alert_count: int,
    source_names: list[str],
    sample_message: str,
) -> AlertPayload:
    """Build one grouped timeline entry in the shared response shape.

    Tests use this helper instead of spelling the same entry shape inline so
    timeline assertions stay focused on grouping intent rather than payload
    boilerplate.
    """
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
) -> AlertPayload:
    """Build the stable raw alert-summary payload used by service and adapters."""
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
    narrative_summary: str | None,
) -> AlertPayload:
    """Build the grouped incident-summary payload shared by service and adapters.

    The grouped summary extends the raw alert summary shape, so this helper
    intentionally layers grouped-incident fields on top of
    ``build_alert_summary_payload``.
    """
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
    """Assert that one summary sentence still carries the important facts."""
    assert narrative is not None
    for part in parts:
        assert part in narrative


def write_known_session(
    session_root: Path,
    session_id: str,
    *,
    alert_rows: list[AlertLogRow] | None = None,
) -> Path:
    """Create one minimal known session with optional alert-log content.

    This writes only the smallest stable session snapshot needed for the
    current alert-query seam: ``session.json`` plus an optional ``alerts.jsonl``.
    """
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
    """Write one alert log file from payload rows or raw invalid-line strings.

    Raw string rows let the service tests cover malformed-line tolerance
    without needing a second helper dedicated only to broken input.
    """
    encoded_rows = [
        row if isinstance(row, str) else json.dumps(row)
        for row in rows
    ]
    (session_dir / "alerts.jsonl").write_text(
        "\n".join(encoded_rows),
        encoding="utf-8",
    )
