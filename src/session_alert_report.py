"""Normalize session alert snapshots into compact demo- and test-friendly views.

The owning input for this module is the full session snapshot returned by
``session_io.read_session_snapshot(...)``. The public helpers here intentionally
expose a smaller shape that is easier to:

- print during demos and manual checks
- assert against in tests without carrying full snapshot noise
- reuse from thin CLI adapters without duplicating formatting logic
"""

from __future__ import annotations

from typing import NotRequired, TypedDict, cast


class SessionAlertReportEntry(TypedDict):
    """One normalized alert row from a persisted session snapshot."""

    segment: str
    detector_id: str
    title: str
    timestamp_utc: str
    message: str
    window_index: NotRequired[int | None]


class SessionAlertReport(TypedDict):
    """Compact alert view for one session."""

    session_id: str
    input_path: str
    alerts: list[SessionAlertReportEntry]


def build_session_alert_report(snapshot: dict[str, object]) -> SessionAlertReport:
    """Extract the compact alert report view from a full session snapshot."""
    session = _read_required_dict(snapshot, "session")
    alerts = _read_required_list(snapshot, "alerts")

    report_alerts: list[SessionAlertReportEntry] = []
    for alert in alerts:
        if not isinstance(alert, dict):
            raise TypeError("Session snapshot alerts must contain mapping entries.")
        report_alerts.append(
            {
                "segment": _read_required_str(alert, "source_name"),
                "detector_id": _read_required_str(alert, "detector_id"),
                "title": _read_required_str(alert, "title"),
                "timestamp_utc": _read_required_str(alert, "timestamp_utc"),
                "message": _read_required_str(alert, "message"),
                "window_index": cast(int | None, alert.get("window_index")),
            },
        )

    return {
        "session_id": _read_required_str(session, "session_id"),
        "input_path": _read_required_str(session, "input_path"),
        "alerts": report_alerts,
    }


def format_session_alert_report_table(report: SessionAlertReport) -> str:
    """Render a compact alert report as a small readable table."""
    lines = [
        f"Session: {report['session_id']}",
        f"Source:  {report['input_path']}",
        "",
    ]
    if not report["alerts"]:
        lines.append("No alerts.")
        return "\n".join(lines)

    headers = ("Segment", "Detector", "Title", "Index", "Timestamp", "Description")
    rows = [
        (
            entry["segment"],
            entry["detector_id"],
            entry["title"],
            _display_value(entry.get("window_index")),
            entry["timestamp_utc"],
            entry["message"],
        )
        for entry in report["alerts"]
    ]
    widths = [
        max(len(header), *(len(row[index]) for row in rows))
        for index, header in enumerate(headers)
    ]
    lines.append(_format_row(headers, widths))
    lines.append(_format_separator(widths))
    lines.extend(_format_row(row, widths) for row in rows)
    return "\n".join(lines)


def _read_required_str(payload: dict[str, object], key: str) -> str:
    """Read one required string field from a loosely typed snapshot payload."""
    value = payload[key]
    if not isinstance(value, str):
        raise TypeError(f"Expected '{key}' to be a string.")
    return value


def _read_required_dict(payload: dict[str, object], key: str) -> dict[str, object]:
    """Read one required nested mapping from a loosely typed snapshot payload."""
    value = payload[key]
    if not isinstance(value, dict):
        raise TypeError(f"Expected '{key}' to be a mapping.")
    return value


def _read_required_list(payload: dict[str, object], key: str) -> list[object]:
    """Read one required list field from a loosely typed snapshot payload."""
    value = payload[key]
    if not isinstance(value, list):
        raise TypeError(f"Expected '{key}' to be a list.")
    return value


def _display_value(value: object) -> str:
    if value is None:
        return "-"
    return str(value)


def _format_row(values: tuple[str, ...], widths: list[int]) -> str:
    padded = [value.ljust(widths[index]) for index, value in enumerate(values)]
    return " | ".join(padded)


def _format_separator(widths: list[int]) -> str:
    return "-+-".join("-" * width for width in widths)
