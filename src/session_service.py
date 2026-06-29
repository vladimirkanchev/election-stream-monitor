"""Transport-agnostic service for starting, reading, and cancelling sessions.

FastAPI, CLI, and other entrypoints should use this module instead of
re-implementing lifecycle mechanics. It owns the shared contract for session
start/read/cancel while keeping backend-specific diagnostics, such as
`worker.log`, outside the public session snapshot.
"""

from __future__ import annotations

from io import TextIOWrapper
from pathlib import Path
import subprocess  # nosec B404
import sys

from analyzer_contract import InputMode
from logger import format_log_context, get_logger
from session_io import get_worker_log_path, request_session_cancel
from session_models import SessionMetadata
from session_runner import create_session_id
from session_store import SessionSnapshotPayload
from session_store_runtime import get_default_session_store
from source_validation import validate_source_input
from stream_loader import build_api_stream_start_session_contract

TERMINAL_SESSION_STATUSES = {"completed", "cancelled", "failed"}
logger = get_logger(__name__)


class SessionServiceNotFoundError(ValueError):
    """Raised when the requested session has no readable persisted snapshot."""


class SessionServiceStartFailedError(OSError):
    """Raised when the detached worker process cannot be started."""


class SessionServiceCancelFailedError(ValueError):
    """Raised when cancellation is requested for an already terminal session."""

    def __init__(self, session_id: str, current_status: str) -> None:
        self.session_id = session_id
        self.current_status = current_status
        super().__init__(f"Session {session_id} is already {current_status}.")


def start_session(
    mode: InputMode,
    input_path: str,
    selected_detectors: list[str],
) -> SessionMetadata:
    """Validate input, spawn the worker, and return pending session metadata."""
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
    """Return the current session snapshot, or `None` when the session is missing."""
    snapshot = read_session_snapshot(session_id)
    session = snapshot.get("session")
    if not isinstance(session, dict):
        return None
    return snapshot


def read_session_snapshot(session_id: str) -> SessionSnapshotPayload:
    """Read one session snapshot through the current default session store."""
    return get_default_session_store().read_snapshot(session_id)


def cancel_session(session_id: str) -> dict[str, object]:
    """Request cancellation for a live session and return a compact summary."""
    snapshot = read_session_snapshot_or_none(session_id)
    if snapshot is None:
        raise SessionServiceNotFoundError(session_id)

    session = snapshot["session"]
    if not isinstance(session, dict):
        raise SessionServiceNotFoundError(session_id)
    session_status = session.get("status")
    if session_status in TERMINAL_SESSION_STATUSES:
        raise SessionServiceCancelFailedError(session_id, str(session_status))

    request_session_cancel(session_id)
    return _build_cancelling_session_summary(session_id, session)


def build_empty_session_snapshot() -> dict[str, object]:
    """Return the stable empty snapshot shape used by CLI and API callers."""
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
    """Validate one start request, including live-mode contract checks."""
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
    """Build the detached worker command for one session run."""
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
    """Open the append-only log file used by the detached worker process."""
    worker_log_path.parent.mkdir(parents=True, exist_ok=True)
    return worker_log_path.open("a", encoding="utf-8")


def _spawn_detached_session_worker(
    command: list[str],
    *,
    log_handle: TextIOWrapper,
) -> None:
    """Spawn one detached worker process with the local runtime settings."""
    subprocess.Popen(  # noqa: S603
        command,
        cwd=str(Path(__file__).resolve().parent),
        stdout=log_handle,
        stderr=log_handle,
        shell=False,
        start_new_session=True,
    )  # nosec B603


def _spawn_session_worker(
    command: list[str],
    *,
    session_id: str,
    mode: InputMode,
    input_path: str,
) -> None:
    """Open the worker log and start the detached session process."""
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
    """Emit one parent-side launch log entry for the detached worker."""
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

    Keep the payload limited to the stable session contract. Worker logs and
    other backend-owned diagnostics remain out-of-band.
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
    """Build the lightweight cancel-request summary returned to callers."""
    return {
        "session_id": session_id,
        "mode": session.get("mode"),
        "input_path": session.get("input_path"),
        "selected_detectors": session.get("selected_detectors", []),
        "status": "cancelling",
    }
