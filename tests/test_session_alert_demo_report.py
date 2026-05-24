"""Coverage for the compact session alert report builder and CLI adapter."""

from __future__ import annotations

import json

import scripts.session_alert_demo_report as session_alert_demo_report
from session_alert_report import (
    build_session_alert_report,
    format_session_alert_report_table,
)
from tests.session_alert_test_support import build_snapshot_alert_report


def _build_snapshot() -> dict[str, object]:
    return {
        "session": {
            "session_id": "session-demo",
            "mode": "video_segments",
            "input_path": "tests/fixtures/media/video_segments/black_recovery_realert_long",
            "selected_detectors": ["video_blur"],
            "status": "completed",
        },
        "progress": {
            "session_id": "session-demo",
            "status": "completed",
            "processed_count": 10,
            "total_count": 10,
            "current_item": "segment_0009.ts",
            "latest_result_detector": "video_blur",
            "latest_result_detectors": ["video_blur"],
            "alert_count": 1,
            "last_updated_utc": "2026-05-24 07:38:34",
            "status_reason": "completed",
            "status_detail": None,
        },
        "alerts": [
            {
                "session_id": "session-demo",
                "timestamp_utc": "2026-05-24 07:38:34",
                "detector_id": "video_blur",
                "title": "Blur warning",
                "message": "segment_0002.ts entered a blurry state.",
                "severity": "warning",
                "source_name": "segment_0002.ts",
                "window_index": 2,
                "window_start_sec": None,
            }
        ],
        "results": [],
        "latest_result": None,
    }


def test_build_snapshot_alert_report_returns_stable_demo_shape() -> None:
    expected_report = {
        "session_id": "session-demo",
        "input_path": "tests/fixtures/media/video_segments/black_recovery_realert_long",
        "alerts": [
            {
                "segment": "segment_0002.ts",
                "detector_id": "video_blur",
                "title": "Blur warning",
                "window_index": 2,
                "timestamp_utc": "2026-05-24 07:38:34",
                "message": "segment_0002.ts entered a blurry state.",
            }
        ],
    }
    assert build_session_alert_report(_build_snapshot()) == expected_report
    assert build_snapshot_alert_report(_build_snapshot()) == expected_report


def test_format_session_alert_report_table_renders_compact_rows() -> None:
    output = format_session_alert_report_table(build_session_alert_report(_build_snapshot()))

    assert "Session: session-demo" in output
    assert "Source:  tests/fixtures/media/video_segments/black_recovery_realert_long" in output
    assert "Segment" in output
    assert "segment_0002.ts" in output
    assert "Blur warning" in output


def test_demo_report_main_prints_table(monkeypatch, capsys) -> None:
    monkeypatch.setattr("session_io.read_session_snapshot", lambda session_id: _build_snapshot())
    monkeypatch.setattr("sys.argv", ["session_alert_demo_report.py", "--session-id", "session-demo"])

    assert session_alert_demo_report.main() == 0

    output = capsys.readouterr().out
    assert "Session: session-demo" in output
    assert "Source:  tests/fixtures/media/video_segments/black_recovery_realert_long" in output
    assert "segment_0002.ts" in output
    assert "video_blur" in output
    assert "Blur warning" in output


def test_demo_report_main_prints_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr("session_io.read_session_snapshot", lambda session_id: _build_snapshot())
    monkeypatch.setattr(
        "sys.argv",
        ["session_alert_demo_report.py", "--session-id", "session-demo", "--format", "json"],
    )

    assert session_alert_demo_report.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["session_id"] == "session-demo"
    assert payload["input_path"].endswith("black_recovery_realert_long")
    assert payload["alerts"][0]["segment"] == "segment_0002.ts"
