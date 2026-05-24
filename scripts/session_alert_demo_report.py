#!/usr/bin/env python3
"""Print a compact session-alert report for one persisted session."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]


def ensure_src_on_path() -> None:
    """Allow direct script execution without requiring an installed package."""
    src_root = REPO_ROOT / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))


def build_parser() -> argparse.ArgumentParser:
    """Build the small CLI surface for the session alert report helper."""
    parser = argparse.ArgumentParser(
        description="Print one compact session-alert report from a persisted snapshot.",
    )
    parser.add_argument("--session-id", required=True)
    parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="Output format. Defaults to a small human-readable table.",
    )
    return parser


def main() -> int:
    """Read one persisted session snapshot and print the requested report view."""
    ensure_src_on_path()
    from session_io import read_session_snapshot
    from session_alert_report import (
        build_session_alert_report,
        format_session_alert_report_table,
    )

    args = build_parser().parse_args()
    report = build_session_alert_report(read_session_snapshot(args.session_id))
    if args.format == "json":
        print(json.dumps(report, indent=2))
        return 0
    print(format_session_alert_report_table(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
