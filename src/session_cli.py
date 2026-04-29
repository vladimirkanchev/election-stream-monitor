"""Tooling/debugging CLI for local session workflows.

For normal desktop use, Electron talks to the local FastAPI backend.
This CLI remains useful for:

- scripted inspection
- manual debugging
- internal worker execution through `run-session`

Keep shared start/read/cancel mechanics in `session_service.py`.
Keep this file focused on argparse, command dispatch, and JSON printing.
"""

import argparse
import json

from analyzer_registry import list_available_detectors
from logger import format_log_context, get_logger
from playback_sources import resolve_playback_source
from session_runner import run_local_session
from session_service import (
    SessionServiceNotFoundError,
    build_empty_session_snapshot,
    cancel_session as cancel_session_service,
    read_session_snapshot_or_none,
    start_session as start_session_service,
)
from source_validation import validate_source_input
from stream_loader import (
    build_api_stream_playback_contract,
)

logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Create the parser for the supported tooling commands."""
    parser = argparse.ArgumentParser(
        description="Tooling/debugging helpers for local session workflows"
    )
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
    """Parse one command and print its JSON response."""
    parser = build_parser()
    args = parser.parse_args()
    _dispatch_command(args)


def _dispatch_command(args: argparse.Namespace) -> None:
    """Dispatch one parsed subcommand and print its JSON payload."""
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
    snapshot = read_session_snapshot_or_none(args.session_id)
    return snapshot if snapshot is not None else build_empty_session_snapshot()


def _handle_cancel_session(args: argparse.Namespace) -> dict[str, object]:
    """Request cancellation and return the CLI-compatible summary."""
    try:
        return cancel_session_service(args.session_id)
    except SessionServiceNotFoundError:
        return {
            "session_id": args.session_id,
            "mode": None,
            "input_path": None,
            "selected_detectors": [],
            "status": "cancelling",
        }


def _handle_resolve_playback_source(args: argparse.Namespace) -> dict[str, str | None]:
    """Resolve one playback source from validated backend inputs."""
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
    """Spawn a detached session worker and return pending metadata."""
    metadata = start_session_service(
        mode=args.mode,
        input_path=args.input_path,
        selected_detectors=args.detector,
    )
    return metadata.to_dict()


def _handle_run_session(args: argparse.Namespace) -> dict[str, object]:
    """Execute one session synchronously and return final metadata."""
    validated_input_path = validate_source_input(args.mode, args.input_path)
    try:
        metadata = run_local_session(
            mode=args.mode,
            input_path=validated_input_path,
            selected_detectors=args.detector,
            session_id=args.session_id,
        )
    except Exception:
        logger.exception(
            "run-session worker failed [%s]",
            format_log_context(
                session_id=args.session_id,
                mode=args.mode,
                input_path=validated_input_path,
            ),
        )
        raise
    return metadata.to_dict()


def _print_json(payload: object) -> None:
    """Print one JSON payload using the CLI's stable pretty-printing format."""
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
