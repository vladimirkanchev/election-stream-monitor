"""Shared start/read/cancel service for session lifecycle operations.

Read this module first when you need to change how sessions are started,
looked up, or cancelled across entrypoints.

It is intentionally transport-agnostic:

- no FastAPI request/response types
- no argparse or CLI printing
- no Electron/frontend concerns

FastAPI and the Python CLI both adapt this shared service instead of
re-implementing session lifecycle mechanics separately.
"""

from __future__ import annotations

from io import TextIOWrapper
from pathlib import Path
import subprocess
import sys

from analyzer_contract import InputMode
from logger import format_log_context, get_logger
from session_io import get_worker_log_path, read_session_snapshot, request_session_cancel
from session_models import SessionMetadata
from session_runner import create_session_id
from source_validation import validate_source_input
from stream_loader import build_api_stream_start_session_contract

TERMINAL_SESSION_STATUSES = {"completed", "cancelled", "failed"}
EMPTY_SESSION_SNAPSHOT = {
    "session": None,
    "progress": None,
    "alerts": [],
    "results": [],
    "latest_result": None,
}
logger = get_logger(__name__)


class SessionServiceNotFoundError(ValueError):
    """Raised when one requested session has no persisted snapshot."""


class SessionServiceStartFailedError(OSError):
    """Raised when the detached session worker could not be started."""


class SessionServiceCancelFailedError(ValueError):
    """Raised when cancellation is not allowed for the current session state."""

    def __init__(self, session_id: str, current_status: str) -> None:
        self.session_id = session_id
        self.current_status = current_status
        super().__init__(f"Session {session_id} is already {current_status}.")


def start_session(
    mode: InputMode,
    input_path: str,
    selected_detectors: list[str],
) -> SessionMetadata:
    """Validate, spawn, and return pending metadata for one session.

    Worker diagnostics stay backend-owned in this milestone. The returned
    metadata intentionally does not surface `worker.log` paths or other
    observability-only fields through the shared start/read/cancel contract.
    """
    validated_input_path = _validate_start_request(
        mode=mode,
        input_path=input_path,
        selected_detectors=selected_detectors,
    )
    session_id = create_session_id()
    command = _build_run_session_command(
        mode=mode,
        input_path=validated_input_path,
        session_id=session_id,
        selected_detectors=selected_detectors,
    )
    _spawn_session_worker(
        command,
        session_id=session_id,
        mode=mode,
        input_path=validated_input_path,
    )
    return _build_pending_session_metadata(
        mode=mode,
        input_path=validated_input_path,
        session_id=session_id,
        selected_detectors=selected_detectors,
    )


def read_session_snapshot_or_none(session_id: str) -> dict[str, object] | None:
    """Return the persisted session snapshot, or ``None`` when missing."""
    snapshot = read_session_snapshot(session_id)
    session = snapshot.get("session")
    if not isinstance(session, dict):
        return None
    return snapshot


def cancel_session(session_id: str) -> dict[str, object]:
    """Request cancellation and return the current cancelling summary."""
    snapshot = read_session_snapshot_or_none(session_id)
    if snapshot is None:
        raise SessionServiceNotFoundError(session_id)

    session = snapshot["session"]
    session_status = session.get("status")
    if session_status in TERMINAL_SESSION_STATUSES:
        raise SessionServiceCancelFailedError(session_id, str(session_status))

    request_session_cancel(session_id)
    return _build_cancelling_session_summary(session_id, session)


def build_empty_session_snapshot() -> dict[str, object]:
    """Return the stable empty snapshot shape used by tooling paths."""
    return {
        "session": None,
        "progress": None,
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def _validate_start_request(
    *,
    mode: InputMode,
    input_path: str,
    selected_detectors: list[str],
) -> str:
    """Validate the source path and run live-mode contract checks when needed."""
    validated_input_path = validate_source_input(mode, input_path)
    if mode == "api_stream":
        build_api_stream_start_session_contract(
            input_path=validated_input_path,
            selected_detectors=selected_detectors,
        )
    return validated_input_path


def _build_run_session_command(
    *,
    mode: InputMode,
    input_path: str,
    session_id: str,
    selected_detectors: list[str],
) -> list[str]:
    """Build the detached worker command used for session execution."""
    command = [
        sys.executable,
        str(Path(__file__).resolve().parent / "session_cli.py"),
        "run-session",
        "--mode",
        mode,
        "--input-path",
        input_path,
        "--session-id",
        session_id,
    ]
    for detector in selected_detectors:
        command.extend(["--detector", detector])
    return command


def _open_worker_log_handle(worker_log_path: Path) -> TextIOWrapper:
    """Open the append-only worker log used by the detached session process."""
    worker_log_path.parent.mkdir(parents=True, exist_ok=True)
    return worker_log_path.open("a", encoding="utf-8")


def _spawn_detached_session_worker(
    command: list[str],
    *,
    log_handle: TextIOWrapper,
) -> None:
    """Spawn one detached worker using the stable local session settings."""
    subprocess.Popen(  # noqa: S603
        command,
        cwd=str(Path(__file__).resolve().parent),
        stdout=log_handle,
        stderr=log_handle,
        start_new_session=True,
    )


def _spawn_session_worker(
    command: list[str],
    *,
    session_id: str,
    mode: InputMode,
    input_path: str,
) -> None:
    """Open worker logs and spawn one detached session process."""
    try:
        worker_log_path = get_worker_log_path(session_id)
        with _open_worker_log_handle(worker_log_path) as log_handle:
            _log_worker_start(
                session_id=session_id,
                mode=mode,
                input_path=input_path,
                worker_log_path=worker_log_path,
            )
            _spawn_detached_session_worker(command, log_handle=log_handle)
    except OSError as error:
        raise SessionServiceStartFailedError(str(error)) from error


def _log_worker_start(
    *,
    session_id: str,
    mode: InputMode,
    input_path: str,
    worker_log_path: Path,
) -> None:
    """Emit one redacted parent-side launch record for the detached worker."""
    logger.info(
        "Started detached session worker [%s]",
        format_log_context(
            session_id=session_id,
            mode=mode,
            input_path=input_path,
            worker_log_path=str(worker_log_path),
        ),
    )


def _build_pending_session_metadata(
    *,
    mode: InputMode,
    input_path: str,
    session_id: str,
    selected_detectors: list[str],
) -> SessionMetadata:
    """Build pending metadata for one accepted start request.

    Keep this payload limited to the stable session contract. Backend-owned
    diagnostics such as `worker.log` remain out-of-band unless a later
    milestone deliberately adds a diagnostics surface.
    """
    return SessionMetadata(
        session_id=session_id,
        mode=mode,
        input_path=input_path,
        selected_detectors=list(selected_detectors),
        status="pending",
    )


def _build_cancelling_session_summary(
    session_id: str,
    session: dict[str, object],
) -> dict[str, object]:
    """Build the current frontend/tooling summary for a cancel request."""
    return {
        "session_id": session_id,
        "mode": session.get("mode"),
        "input_path": session.get("input_path"),
        "selected_detectors": session.get("selected_detectors", []),
        "status": "cancelling",
    }
