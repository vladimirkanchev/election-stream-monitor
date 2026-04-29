"""Focused tests for the shared session start/read/cancel service.

These tests cover the canonical application seam directly. FastAPI and CLI
adapter suites stay separate so transport behavior and shared session
mechanics do not get re-tested in the same place.

For the worker-observability milestone, this suite also owns the direct checks
for:

- detached worker command shape
- session-scoped `worker.log` capture
- parent-side launch logging with redacted context
- the rule that diagnostics stay out of public session payloads
"""

from contextlib import contextmanager
from io import StringIO
from pathlib import Path

import pytest

import session_service

DEFAULT_INPUT_PATH = "tests/fixtures/media/video_files/black_trigger.mp4"


@contextmanager
def _context_managed_handle(
    handle: StringIO,
    recorded: dict[str, object],
    session_id: str,
):
    """Yield a fake context-managed log handle while recording the session id."""
    recorded["opened_for"] = session_id
    yield handle


def _install_start_session_harness(
    monkeypatch,
    tmp_path: Path,
    recorded: dict[str, object],
    *,
    session_id: str,
) -> None:
    """Install the common start-session seams used by the observability tests."""
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
        lambda current_session_id: tmp_path / current_session_id / "worker.log",
    )
    monkeypatch.setattr(
        session_service,
        "_spawn_detached_session_worker",
        lambda command, *, log_handle: recorded.setdefault(
            "spawn",
            {"command": command, "log_name": log_handle.name},
        ),
    )


def _spawn_worker(
    *,
    command: list[str] | None = None,
    session_id: str = "session-123",
    mode: str = "video_files",
    input_path: str = "/tmp/input.mp4",
) -> None:
    """Call the direct worker-launch helper with stable test defaults."""
    session_service._spawn_session_worker(
        command or ["python", "session_cli.py"],
        session_id=session_id,
        mode=mode,
        input_path=input_path,
    )


def test_start_session_happy_path(monkeypatch, tmp_path: Path) -> None:
    """Start should validate, spawn, and return pending metadata."""
    recorded: dict[str, object] = {}
    _install_start_session_harness(
        monkeypatch,
        tmp_path,
        recorded,
        session_id="test-session-123",
    )

    metadata = session_service.start_session(
        mode="video_files",
        input_path=DEFAULT_INPUT_PATH,
        selected_detectors=["video_metrics"],
    )

    assert metadata.to_dict() == {
        "session_id": "test-session-123",
        "mode": "video_files",
        "input_path": DEFAULT_INPUT_PATH,
        "selected_detectors": ["video_metrics"],
        "status": "pending",
    }
    assert recorded["spawn"] == {
        "command": [
            session_service.sys.executable,
            str(Path(session_service.__file__).resolve().parent / "session_cli.py"),
            "run-session",
            "--mode",
            "video_files",
            "--input-path",
            DEFAULT_INPUT_PATH,
            "--session-id",
            "test-session-123",
            "--detector",
            "video_metrics",
        ],
        "log_name": str(tmp_path / "test-session-123" / "worker.log"),
    }
    assert recorded["log"] == (
        "Started detached session worker [%s]",
        "session_id='test-session-123' "
        "mode='video_files' "
        "input_path='<path:black_trigger.mp4>' "
        "worker_log_path='<path:worker.log>'",
    )


def test_build_run_session_command_includes_all_selected_detectors() -> None:
    """The detached worker command should preserve detector ordering and values."""
    command = session_service._build_run_session_command(
        mode="api_stream",
        input_path="https://example.com/live/index.m3u8",
        session_id="session-123",
        selected_detectors=["video_metrics", "video_blur"],
    )

    assert command == [
        session_service.sys.executable,
        str(Path(session_service.__file__).resolve().parent / "session_cli.py"),
        "run-session",
        "--mode",
        "api_stream",
        "--input-path",
        "https://example.com/live/index.m3u8",
        "--session-id",
        "session-123",
        "--detector",
        "video_metrics",
        "--detector",
        "video_blur",
    ]


def test_start_session_api_stream_runs_contract_check(monkeypatch, tmp_path: Path) -> None:
    """Start should preserve the extra api_stream contract validation step."""
    recorded: dict[str, object] = {}
    _install_start_session_harness(
        monkeypatch,
        tmp_path,
        recorded,
        session_id="api-stream-session-123",
    )

    def fake_build_api_stream_start_session_contract(
        *,
        input_path: str,
        selected_detectors: list[str],
    ) -> object:
        recorded["contract"] = (input_path, selected_detectors)
        return object()

    monkeypatch.setattr(
        session_service,
        "build_api_stream_start_session_contract",
        fake_build_api_stream_start_session_contract,
    )
    monkeypatch.setattr(
        session_service,
        "_spawn_detached_session_worker",
        lambda command, *, log_handle: recorded.setdefault(
            "spawn",
            {"command": command, "log_name": log_handle.name},
        ),
    )

    metadata = session_service.start_session(
        mode="api_stream",
        input_path="https://example.com/live/index.m3u8",
        selected_detectors=["video_metrics", "video_blur"],
    )

    assert metadata.to_dict() == {
        "session_id": "api-stream-session-123",
        "mode": "api_stream",
        "input_path": "https://example.com/live/index.m3u8",
        "selected_detectors": ["video_metrics", "video_blur"],
        "status": "pending",
    }
    assert recorded["contract"] == (
        "https://example.com/live/index.m3u8",
        ["video_metrics", "video_blur"],
    )
    assert recorded["spawn"] == {
        "command": [
            session_service.sys.executable,
            str(Path(session_service.__file__).resolve().parent / "session_cli.py"),
            "run-session",
            "--mode",
            "api_stream",
            "--input-path",
            "https://example.com/live/index.m3u8",
            "--session-id",
            "api-stream-session-123",
            "--detector",
            "video_metrics",
            "--detector",
            "video_blur",
        ],
        "log_name": str(tmp_path / "api-stream-session-123" / "worker.log"),
    }
    assert recorded["log"] == (
        "Started detached session worker [%s]",
        "session_id='api-stream-session-123' "
        "mode='api_stream' "
        "input_path='<path:index.m3u8>' "
        "worker_log_path='<path:worker.log>'",
    )


def test_start_session_validation_failure(monkeypatch) -> None:
    """Start should surface source validation failures unchanged."""
    def fake_validate_source_input(mode: str, input_path: str) -> str:
        _ = (mode, input_path)
        raise OSError("Input path does not exist: missing.mp4")

    monkeypatch.setattr(
        session_service,
        "validate_source_input",
        fake_validate_source_input,
    )

    with pytest.raises(OSError, match="Input path does not exist: missing.mp4"):
        session_service.start_session(
            mode="video_files",
            input_path="missing.mp4",
            selected_detectors=["video_metrics"],
        )


def test_start_session_validation_failure_does_not_emit_worker_launch_log(monkeypatch) -> None:
    """Validation failures should happen before any parent-side worker launch record."""
    calls: list[tuple[object, ...]] = []

    def fake_validate_source_input(mode: str, input_path: str) -> str:
        _ = (mode, input_path)
        raise OSError("Input path does not exist: missing.mp4")

    monkeypatch.setattr(
        session_service,
        "validate_source_input",
        fake_validate_source_input,
    )
    monkeypatch.setattr(
        session_service.logger,
        "info",
        lambda *args: calls.append(args),
    )

    with pytest.raises(OSError, match="Input path does not exist: missing.mp4"):
        session_service.start_session(
            mode="video_files",
            input_path="missing.mp4",
            selected_detectors=["video_metrics"],
        )

    assert calls == []


def test_start_session_spawn_failure(monkeypatch) -> None:
    """Start should wrap detached-worker spawn failures in the service error."""
    monkeypatch.setattr(
        session_service,
        "validate_source_input",
        lambda mode, input_path: input_path,
    )
    monkeypatch.setattr(
        session_service,
        "create_session_id",
        lambda: "test-session-123",
    )
    monkeypatch.setattr(session_service.logger, "info", lambda *args, **kwargs: None)

    def fake_spawn_session_worker(
        command: list[str],
        *,
        session_id: str,
        mode: str,
        input_path: str,
    ) -> None:
        _ = (command, session_id, mode, input_path)
        raise session_service.SessionServiceStartFailedError("spawn failed")

    monkeypatch.setattr(
        session_service,
        "_spawn_session_worker",
        fake_spawn_session_worker,
    )

    with pytest.raises(
        session_service.SessionServiceStartFailedError,
        match="spawn failed",
    ):
        session_service.start_session(
            mode="video_files",
            input_path=DEFAULT_INPUT_PATH,
            selected_detectors=["video_metrics"],
        )


def test_start_session_copies_selected_detectors_into_metadata(monkeypatch) -> None:
    """Returned metadata should not share the caller's detector list object."""
    detectors = ["video_metrics"]

    monkeypatch.setattr(
        session_service,
        "validate_source_input",
        lambda mode, input_path: input_path,
    )
    monkeypatch.setattr(
        session_service,
        "create_session_id",
        lambda: "test-session-123",
    )
    monkeypatch.setattr(session_service.logger, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        session_service,
        "_spawn_session_worker",
        lambda command, *, session_id, mode, input_path: None,
    )

    metadata = session_service.start_session(
        mode="video_files",
        input_path=DEFAULT_INPUT_PATH,
        selected_detectors=detectors,
    )
    detectors.append("video_blur")

    assert metadata.selected_detectors == ["video_metrics"]


def test_read_session_returns_existing_snapshot(monkeypatch) -> None:
    """Read should return the full snapshot when a session exists."""
    monkeypatch.setattr(
        session_service,
        "read_session_snapshot",
        lambda session_id: {
            "session": {
                "session_id": session_id,
                "mode": "video_files",
                "input_path": "/tmp/input.mp4",
                "selected_detectors": ["video_metrics"],
                "status": "running",
            },
            "progress": None,
            "alerts": [],
            "results": [],
            "latest_result": None,
        },
    )

    snapshot = session_service.read_session_snapshot_or_none("session-123")

    assert snapshot is not None
    assert snapshot["session"]["session_id"] == "session-123"


def test_open_worker_log_handle_creates_parent_dir_and_appends(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Worker log handles should be opened in append mode under the session directory."""
    log_path = tmp_path / "session-123" / "worker.log"

    with session_service._open_worker_log_handle(log_path) as handle:
        handle.write("first line\n")
    with session_service._open_worker_log_handle(log_path) as handle:
        handle.write("second line\n")

    assert log_path.read_text(encoding="utf-8") == "first line\nsecond line\n"


def test_spawn_detached_session_worker_preserves_detached_process_settings(monkeypatch) -> None:
    """Detached spawn should keep cwd, shared log handles, and session isolation settings."""
    recorded: dict[str, object] = {}
    log_handle = StringIO()
    command = ["python", "session_cli.py", "run-session"]

    def fake_popen(*args, **kwargs):
        recorded["args"] = args
        recorded["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(session_service.subprocess, "Popen", fake_popen)

    session_service._spawn_detached_session_worker(command, log_handle=log_handle)

    assert recorded["args"] == (command,)
    assert recorded["kwargs"] == {
        "cwd": str(Path(session_service.__file__).resolve().parent),
        "stdout": log_handle,
        "stderr": log_handle,
        "start_new_session": True,
    }
    assert recorded["kwargs"]["stdout"] is not session_service.subprocess.DEVNULL
    assert recorded["kwargs"]["stderr"] is not session_service.subprocess.DEVNULL


def test_spawn_session_worker_creates_session_scoped_worker_log(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Spawning a worker should materialize the append-only session log file."""
    log_path = tmp_path / "session-123" / "worker.log"
    recorded: dict[str, object] = {}

    monkeypatch.setattr(
        session_service,
        "get_worker_log_path",
        lambda session_id: log_path,
    )
    monkeypatch.setattr(session_service.logger, "info", lambda *args, **kwargs: None)

    def fake_spawn_detached_session_worker(command: list[str], *, log_handle) -> None:
        recorded["command"] = command
        recorded["log_name"] = log_handle.name

    monkeypatch.setattr(
        session_service,
        "_spawn_detached_session_worker",
        fake_spawn_detached_session_worker,
    )

    _spawn_worker()

    assert log_path.exists()
    assert recorded == {
        "command": ["python", "session_cli.py"],
        "log_name": str(log_path),
    }


def test_spawn_session_worker_opens_log_handle_and_spawns(monkeypatch) -> None:
    """The orchestration helper should open the session log before spawning the worker."""
    recorded: dict[str, object] = {}
    log_handle = StringIO()
    expected_log_path = Path("/tmp/session-123/worker.log")

    monkeypatch.setattr(
        session_service,
        "get_worker_log_path",
        lambda session_id: expected_log_path,
    )

    monkeypatch.setattr(
        session_service,
        "_open_worker_log_handle",
        lambda worker_log_path: _context_managed_handle(
            log_handle,
            recorded,
            str(worker_log_path),
        ),
    )
    monkeypatch.setattr(session_service.logger, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        session_service,
        "_spawn_detached_session_worker",
        lambda command, *, log_handle: recorded.setdefault(
            "spawn",
            {"command": command, "log_handle": log_handle},
        ),
    )

    _spawn_worker()

    assert recorded["opened_for"] == str(expected_log_path)
    assert recorded["spawn"] == {
        "command": ["python", "session_cli.py"],
        "log_handle": log_handle,
    }


def test_spawn_session_worker_wraps_log_open_failure(monkeypatch) -> None:
    """Log-handle setup failures should still surface as service-level start failures."""
    def fake_open_worker_log_handle(session_id: str):
        _ = session_id
        raise OSError("permission denied")

    monkeypatch.setattr(
        session_service,
        "_open_worker_log_handle",
        fake_open_worker_log_handle,
    )
    monkeypatch.setattr(session_service.logger, "info", lambda *args, **kwargs: None)

    with pytest.raises(session_service.SessionServiceStartFailedError, match="permission denied"):
        _spawn_worker()


def test_read_session_returns_none_when_missing(monkeypatch) -> None:
    """Read should centralize the missing-session check."""
    monkeypatch.setattr(
        session_service,
        "read_session_snapshot",
        lambda session_id: {
            "session": None,
            "progress": None,
            "alerts": [],
            "results": [],
            "latest_result": None,
        },
    )

    snapshot = session_service.read_session_snapshot_or_none("missing-session")

    assert snapshot is None


def test_cancel_failed_error_exposes_current_status() -> None:
    """The service cancel error should keep the parsed status for adapters."""
    error = session_service.SessionServiceCancelFailedError(
        "session-terminal",
        "completed",
    )

    assert error.session_id == "session-terminal"
    assert error.current_status == "completed"
    assert str(error) == "Session session-terminal is already completed."


def test_build_empty_session_snapshot_returns_fresh_lists() -> None:
    """Each empty snapshot call should get its own mutable event lists."""
    first = session_service.build_empty_session_snapshot()
    second = session_service.build_empty_session_snapshot()

    first["alerts"].append({"title": "example"})
    first["results"].append({"detector_id": "video_metrics"})

    assert second == {
        "session": None,
        "progress": None,
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def test_cancel_session_running_happy_path(monkeypatch) -> None:
    """Cancel should allow active sessions and return the cancelling summary."""
    cancelled: list[str] = []

    monkeypatch.setattr(
        session_service,
        "read_session_snapshot",
        lambda session_id: {
            "session": {
                "session_id": session_id,
                "mode": "video_files",
                "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
                "selected_detectors": ["video_metrics"],
                "status": "running",
            },
            "progress": None,
            "alerts": [],
            "results": [],
            "latest_result": None,
        },
    )
    monkeypatch.setattr(
        session_service,
        "request_session_cancel",
        lambda session_id: cancelled.append(session_id),
    )

    summary = session_service.cancel_session("session-running")

    assert cancelled == ["session-running"]
    assert summary == {
        "session_id": "session-running",
        "mode": "video_files",
        "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
        "selected_detectors": ["video_metrics"],
        "status": "cancelling",
    }


def test_cancel_session_allows_already_cancelling(monkeypatch) -> None:
    """Cancel should preserve the existing behavior for already-cancelling runs."""
    cancelled: list[str] = []

    monkeypatch.setattr(
        session_service,
        "read_session_snapshot",
        lambda session_id: {
            "session": {
                "session_id": session_id,
                "mode": "api_stream",
                "input_path": "https://example.com/live/index.m3u8",
                "selected_detectors": ["video_metrics"],
                "status": "cancelling",
            },
            "progress": None,
            "alerts": [],
            "results": [],
            "latest_result": None,
        },
    )
    monkeypatch.setattr(
        session_service,
        "request_session_cancel",
        lambda session_id: cancelled.append(session_id),
    )

    summary = session_service.cancel_session("session-cancelling")

    assert cancelled == ["session-cancelling"]
    assert summary == {
        "session_id": "session-cancelling",
        "mode": "api_stream",
        "input_path": "https://example.com/live/index.m3u8",
        "selected_detectors": ["video_metrics"],
        "status": "cancelling",
    }


def test_cancel_session_rejects_terminal_status(monkeypatch) -> None:
    """Cancel should reject terminal sessions through the service error."""
    monkeypatch.setattr(
        session_service,
        "read_session_snapshot",
        lambda session_id: {
            "session": {
                "session_id": session_id,
                "mode": "video_files",
                "input_path": "/tmp/input.mp4",
                "selected_detectors": ["video_metrics"],
                "status": "completed",
            },
            "progress": None,
            "alerts": [],
            "results": [],
            "latest_result": None,
        },
    )

    with pytest.raises(
        session_service.SessionServiceCancelFailedError,
        match="Session session-terminal is already completed.",
    ):
        session_service.cancel_session("session-terminal")


def test_cancel_session_missing_id_raises_not_found(monkeypatch) -> None:
    """Cancel should use the service-level not-found error for missing sessions."""
    monkeypatch.setattr(
        session_service,
        "read_session_snapshot",
        lambda session_id: {
            "session": None,
            "progress": None,
            "alerts": [],
            "results": [],
            "latest_result": None,
        },
    )

    with pytest.raises(session_service.SessionServiceNotFoundError, match="missing-session"):
        session_service.cancel_session("missing-session")


def test_cancel_session_defaults_missing_selected_detectors_to_empty_list(
    monkeypatch,
) -> None:
    """Cancel summaries should stay stable even when older snapshots miss the field."""
    monkeypatch.setattr(
        session_service,
        "read_session_snapshot",
        lambda session_id: {
            "session": {
                "session_id": session_id,
                "mode": "video_files",
                "input_path": "/tmp/input.mp4",
                "status": "running",
            },
            "progress": None,
            "alerts": [],
            "results": [],
            "latest_result": None,
        },
    )
    monkeypatch.setattr(
        session_service,
        "request_session_cancel",
        lambda session_id: None,
    )

    summary = session_service.cancel_session("session-missing-detectors")

    assert summary == {
        "session_id": "session-missing-detectors",
        "mode": "video_files",
        "input_path": "/tmp/input.mp4",
        "selected_detectors": [],
        "status": "cancelling",
    }
