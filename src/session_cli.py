"""Small CLI entry points for the local React/Electron bridge.

The CLI is intentionally narrow: it exposes a few explicit operations used by
the Electron main process and keeps the bridge semantics separate from the
frontend transport details.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from analyzer_registry import list_available_detectors
from playback_sources import resolve_playback_source
from session_io import read_session_snapshot, request_session_cancel
from session_models import SessionMetadata
from session_runner import create_session_id, run_local_session
from source_validation import validate_source_input
from stream_loader import (
    build_api_stream_playback_contract,
    build_api_stream_start_session_contract,
)


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description="Local session bridge helpers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-detectors")
    list_parser.add_argument("--mode", default=None)

    run_parser = subparsers.add_parser("run-session")
    run_parser.add_argument("--mode", required=True)
    run_parser.add_argument("--input-path", required=True)
    run_parser.add_argument("--detector", action="append", default=[])
    run_parser.add_argument("--session-id", default=None)

    start_parser = subparsers.add_parser("start-session")
    start_parser.add_argument("--mode", required=True)
    start_parser.add_argument("--input-path", required=True)
    start_parser.add_argument("--detector", action="append", default=[])

    snapshot_parser = subparsers.add_parser("read-session")
    snapshot_parser.add_argument("--session-id", required=True)

    cancel_parser = subparsers.add_parser("cancel-session")
    cancel_parser.add_argument("--session-id", required=True)

    playback_parser = subparsers.add_parser("resolve-playback-source")
    playback_parser.add_argument("--mode", required=True)
    playback_parser.add_argument("--input-path", required=True)
    playback_parser.add_argument("--current-item", default=None)

    return parser


def main() -> None:
    """Parse one bridge command and print its JSON response."""
    parser = build_parser()
    args = parser.parse_args()
    _dispatch_command(args)


def _dispatch_command(args: argparse.Namespace) -> None:
    """Run one parsed subcommand and print its JSON payload."""
    handlers = {
        "list-detectors": _handle_list_detectors,
        "run-session": _handle_run_session,
        "start-session": _handle_start_session,
        "read-session": _handle_read_session,
        "cancel-session": _handle_cancel_session,
        "resolve-playback-source": _handle_resolve_playback_source,
    }
    handler = handlers[args.command]
    _print_json(handler(args))


def _handle_list_detectors(args: argparse.Namespace) -> list[dict[str, object]]:
    """Return the detector catalog payload for the requested mode."""
    return list_available_detectors(args.mode)


def _handle_read_session(args: argparse.Namespace) -> dict[str, object]:
    """Return the current persisted session snapshot."""
    return read_session_snapshot(args.session_id)


def _handle_cancel_session(args: argparse.Namespace) -> dict[str, object]:
    """Persist a cancel request and return a frontend-friendly session summary."""
    request_session_cancel(args.session_id)
    snapshot = read_session_snapshot(args.session_id)
    session = snapshot.get("session") or {}
    return {
        "session_id": args.session_id,
        "mode": session.get("mode"),
        "input_path": session.get("input_path"),
        "selected_detectors": session.get("selected_detectors", []),
        "status": "cancelling",
    }


def _handle_resolve_playback_source(args: argparse.Namespace) -> dict[str, str | None]:
    """Resolve one frontend playback source from validated backend inputs."""
    validated_input_path = validate_source_input(args.mode, args.input_path)
    if args.mode == "api_stream":
        return {
            "source": build_api_stream_playback_contract(validated_input_path).source
        }
    resolved = resolve_playback_source(
        mode=args.mode,
        input_path=validated_input_path,
        current_item=args.current_item or None,
    )
    return {"source": resolved}


def _handle_start_session(args: argparse.Namespace) -> dict[str, object]:
    """Spawn a detached local session process and return the pending metadata."""
    validated_input_path = validate_source_input(args.mode, args.input_path)
    if args.mode == "api_stream":
        build_api_stream_start_session_contract(
            input_path=validated_input_path,
            selected_detectors=args.detector,
        )
    session_id = create_session_id()
    subprocess.Popen(  # noqa: S603
        _build_run_session_command(
            mode=args.mode,
            input_path=validated_input_path,
            session_id=session_id,
            detectors=args.detector,
        ),
        cwd=str(Path(__file__).resolve().parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return _build_pending_session_metadata(
        mode=args.mode,
        input_path=validated_input_path,
        session_id=session_id,
        detectors=args.detector,
    )


def _handle_run_session(args: argparse.Namespace) -> dict[str, object]:
    """Execute one session synchronously and return the final metadata summary."""
    validated_input_path = validate_source_input(args.mode, args.input_path)
    metadata = run_local_session(
        mode=args.mode,
        input_path=validated_input_path,
        selected_detectors=args.detector,
        session_id=args.session_id,
    )
    return metadata.to_dict()


def _build_run_session_command(
    *,
    mode: str,
    input_path: str,
    session_id: str,
    detectors: list[str],
) -> list[str]:
    """Build the detached child-process command used by `start-session`."""
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "run-session",
        "--mode",
        mode,
        "--input-path",
        input_path,
        "--session-id",
        session_id,
    ]
    for detector in detectors:
        command.extend(["--detector", detector])
    return command


def _build_pending_session_metadata(
    *,
    mode: str,
    input_path: str,
    session_id: str,
    detectors: list[str],
) -> dict[str, object]:
    """Return the pending session summary shape expected by the bridge."""
    metadata = SessionMetadata(
        session_id=session_id,
        mode=mode,
        input_path=input_path,
        selected_detectors=list(detectors),
        status="pending",
    )
    return metadata.to_dict()


def _print_json(payload: object) -> None:
    """Print one JSON payload using the CLI's stable pretty-printing format."""
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
