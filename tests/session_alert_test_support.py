"""Shared support helpers for session alert query tests.

These helpers keep the alert-query tests focused on scenario intent:

- isolate one temporary session-output root
- create a minimal persisted session snapshot
- write alert JSONL rows, including intentionally invalid lines
- build alert payloads without repeating the contract shape inline

The module stays small and procedural on purpose. It removes setup noise
without hiding test meaning behind a framework.
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
