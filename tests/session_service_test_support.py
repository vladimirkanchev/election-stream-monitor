"""Shared helpers for the split session service start/worker test suites."""

from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from typing import Any

from analyzer_contract import InputMode
import session_service

DEFAULT_INPUT_PATH = "tests/fixtures/media/video_files/black_trigger.mp4"
DEFAULT_DETECTORS = ["video_metrics"]
DEFAULT_SESSION_ID = "test-session-123"


def build_run_session_command(
    *,
    mode: InputMode,
    input_path: str,
    session_id: str,
    selected_detectors: list[str],
) -> list[str]:
    """Build the detached worker CLI command using the real service helper."""
    return session_service._build_run_session_command(
        mode=mode,
        input_path=input_path,
        session_id=session_id,
        selected_detectors=selected_detectors,
    )


def build_worker_log_path(tmp_path: Path, session_id: str) -> Path:
    """Return the per-session worker log path used by start and worker tests."""
    return tmp_path / session_id / "worker.log"


def build_start_log_context(*, session_id: str, mode: str, input_path: str) -> str:
    """Build the normalized info-log context emitted after a successful start."""
    return (
        f"session_id='{session_id}' "
        f"mode='{mode}' "
        f"input_path='<path:{Path(input_path).name}>' "
        "worker_log_path='<path:worker.log>'"
    )


@contextmanager
def context_managed_handle(
    handle: StringIO,
    recorded: dict[str, Any],
    session_id: str,
):
    """Yield a fake opened handle and record which worker log path was requested."""
    recorded["opened_for"] = session_id
    yield handle


def install_start_session_harness(
    monkeypatch,
    tmp_path: Path,
    recorded: dict[str, Any],
    *,
    session_id: str,
) -> None:
    """Install a compact happy-path harness for `start_session` tests."""
    monkeypatch.setattr(
        session_service,
        "validate_source_input",
        lambda mode, input_path: input_path,
    )
    monkeypatch.setattr(session_service, "create_session_id", lambda: session_id)
    monkeypatch.setattr(
        session_service.logger,
        "info",
        lambda message, context: recorded.setdefault("log", (message, context)),
    )
    monkeypatch.setattr(
        session_service,
        "get_worker_log_path",
        lambda current_session_id: build_worker_log_path(tmp_path, current_session_id),
    )
    monkeypatch.setattr(
        session_service,
        "_spawn_detached_session_worker",
        lambda command, *, log_handle: recorded.setdefault(
            "spawn",
            {"command": command, "log_name": log_handle.name},
        ),
    )


def spawn_worker(
    *,
    command: list[str] | None = None,
    session_id: str = "session-123",
    mode: InputMode = "video_files",
    input_path: str = "/tmp/input.mp4",
) -> None:
    """Run the direct worker-spawn helper with stable default arguments."""
    session_service._spawn_session_worker(
        command or ["python", "session_cli.py"],
        session_id=session_id,
        mode=mode,
        input_path=input_path,
    )


__all__ = [
    "DEFAULT_DETECTORS",
    "DEFAULT_INPUT_PATH",
    "DEFAULT_SESSION_ID",
    "build_run_session_command",
    "build_start_log_context",
    "build_worker_log_path",
    "context_managed_handle",
    "install_start_session_harness",
    "spawn_worker",
]
