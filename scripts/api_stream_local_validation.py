#!/usr/bin/env python3
"""Helpers for repeatable local api_stream fixture validation."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import config
from session_io import read_session_snapshot
from stream_loader import build_api_stream_temp_session_dir


EXPECTATIONS_PATH = REPO_ROOT / "tests" / "fixtures" / "media" / "api_stream_expectations.json"


def load_expectations() -> dict[str, object]:
    return json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local api_stream validation helpers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-fixtures", help="List the current local api_stream validation fixtures")

    serve_parser = subparsers.add_parser(
        "serve-fixture",
        help="Serve one checked-in HLS fixture over local HTTP and print the manual checklist",
    )
    serve_parser.add_argument("--fixture-id", required=True)
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=0)

    check_parser = subparsers.add_parser(
        "check-session",
        help="Compare one finished session snapshot against the fixture expectation manifest",
    )
    check_parser.add_argument("--fixture-id", required=True)
    check_parser.add_argument("--session-id", required=True)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list-fixtures":
        return handle_list_fixtures()
    if args.command == "serve-fixture":
        return handle_serve_fixture(args.fixture_id, host=args.host, port=args.port)
    if args.command == "check-session":
        return handle_check_session(args.fixture_id, args.session_id)
    raise ValueError(f"Unsupported command: {args.command}")


def handle_list_fixtures() -> int:
    expectations = load_expectations()
    for case in expectations["cases"]:
        print(
            f"{case['id']}: {case['fixture_path']} "
            f"detectors={','.join(case['selected_detectors'])} "
            f"expected=chunks:{case['expected_chunk_count']} "
            f"alerts:{case['expected_alert_count']} "
            f"status:{case['expected_final_status']}"
        )
    return 0


def handle_serve_fixture(fixture_id: str, *, host: str, port: int) -> int:
    case = get_case(fixture_id)
    fixture_dir = REPO_ROOT / "tests" / "fixtures" / "media" / case["fixture_path"]
    playlist_path = fixture_dir / "index.m3u8"
    if not playlist_path.exists():
        raise FileNotFoundError(f"Fixture playlist does not exist: {playlist_path}")

    with serve_directory(fixture_dir, host=host, port=port) as base_url:
        live_url = f"{base_url}/index.m3u8"
        trial = build_manual_trial_expectations(case, live_url=live_url)
        print(f"Fixture: {fixture_id}")
        print(f"Directory: {fixture_dir}")
        print(f"Live URL: {trial['source_input']}")
        print(f"Expected status: {trial['expected_status']}")
        print(
            "Expected metrics: "
            f"chunks={case['expected_chunk_count']} "
            f"alerts={case['expected_alert_count']} "
            f"final_status={case['expected_final_status']}"
        )
        print()
        print("Checklist")
        print("1. Source input")
        print(f"   URL: {trial['source_input']}")
        print(f"   Detectors: {', '.join(case['selected_detectors'])}")
        print("2. Start a detached live session with the local fixture URL:")
        print(
            "   "
            + build_start_session_command(
                live_url=live_url,
                detectors=case["selected_detectors"],
            )
        )
        print("3. Copy the returned `session_id` and watch chunk progression:")
        print("   python src/session_cli.py read-session --session-id <session_id>")
        print(f"4. Expected status")
        print(f"   {trial['expected_status']}")
        print("5. Expected logs")
        for snippet in trial["expected_logs"]:
            print(f"   - {snippet}")
        print("6. Force cancel if you want to validate live shutdown behavior:")
        print("   python src/session_cli.py cancel-session --session-id <session_id>")
        print("7. Inspect foreground loader logs if you want a non-detached run:")
        print(
            "   "
            + build_run_session_command(
                live_url=live_url,
                detectors=case["selected_detectors"],
            )
        )
        print("8. Expected cleanup")
        for check in trial["expected_cleanup"]:
            print(f"   - {check}")
        print("9. Inspect the persisted session snapshot and temp directory:")
        print(f"   session dir root: {config.SESSION_OUTPUT_FOLDER}")
        print(f"   temp dir pattern: {build_api_stream_temp_session_dir('<session_id>')}")
        print("10. Compare the finished session with the expected metrics:")
        print(
            "   "
            f"python scripts/api_stream_local_validation.py check-session "
            f"--fixture-id {fixture_id} --session-id <session_id>"
        )
        print()
        print("Server is running. Press Ctrl-C when you are done.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print()
            print("Stopped local fixture server.")
    return 0


def handle_check_session(fixture_id: str, session_id: str) -> int:
    case = get_case(fixture_id)
    snapshot = read_session_snapshot(session_id)
    actual_status = snapshot["session"]["status"]
    actual_chunks = snapshot["progress"]["processed_count"]
    actual_alerts = len(snapshot["alerts"])

    problems: list[str] = []
    if actual_status != case["expected_final_status"]:
        problems.append(
            f"expected final status {case['expected_final_status']!r}, got {actual_status!r}"
        )
    if actual_chunks != case["expected_chunk_count"]:
        problems.append(
            f"expected chunk count {case['expected_chunk_count']}, got {actual_chunks}"
        )
    if actual_alerts != case["expected_alert_count"]:
        problems.append(
            f"expected alert count {case['expected_alert_count']}, got {actual_alerts}"
        )

    if problems:
        print(f"FAIL: {fixture_id} vs session {session_id}")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print(f"PASS: {fixture_id} vs session {session_id}")
    print(
        f"status={actual_status} processed_count={actual_chunks} alert_count={actual_alerts}"
    )
    return 0


def get_case(fixture_id: str) -> dict[str, object]:
    expectations = load_expectations()
    for case in expectations["cases"]:
        if case["id"] == fixture_id:
            return case
    raise ValueError(f"Unknown fixture id: {fixture_id}")


def build_manual_trial_expectations(
    case: dict[str, object], *, live_url: str
) -> dict[str, object]:
    return {
        "source_input": live_url,
        "expected_status": case["expected_final_status"],
        "expected_logs": list(case["expected_log_snippets"]),
        "expected_cleanup": list(case["expected_cleanup_checks"]),
    }


def build_start_session_command(*, live_url: str, detectors: list[str]) -> str:
    parts = [
        "python src/session_cli.py start-session",
        "--mode api_stream",
        f"--input-path {live_url}",
    ]
    for detector in detectors:
        parts.append(f"--detector {detector}")
    return " ".join(parts)


def build_run_session_command(*, live_url: str, detectors: list[str]) -> str:
    parts = [
        "python src/session_cli.py run-session",
        "--mode api_stream",
        f"--input-path {live_url}",
        "--session-id manual-live-debug",
    ]
    for detector in detectors:
        parts.append(f"--detector {detector}")
    return " ".join(parts)


@contextmanager
def serve_directory(directory: Path, *, host: str, port: int):
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer((host, port), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{host}:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
