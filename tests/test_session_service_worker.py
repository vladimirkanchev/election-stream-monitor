"""Focused tests for detached worker launch, logging, and env inheritance."""

import os
from io import StringIO, TextIOWrapper
from pathlib import Path
from typing import cast

import pytest

import session_service
from session_alert_store_postgres_config import POSTGRES_ALERT_DATABASE_URL_ENV
from session_alert_store_runtime_config import ALERT_STORE_BACKEND_ENV
from session_store_postgres_config import POSTGRES_SESSION_DATABASE_URL_ENV
from session_store_runtime_config import SESSION_STORE_BACKEND_ENV
from tests.session_service_test_support import context_managed_handle, spawn_worker


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


def test_spawn_detached_session_worker_preserves_detached_process_settings(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Detached spawn should keep cwd, shared log handles, and session isolation settings."""
    recorded: dict[str, object] = {}
    log_path = tmp_path / "worker.log"
    log_handle = log_path.open("a", encoding="utf-8")
    command = ["python", "session_cli.py", "run-session"]

    def fake_popen(*args, **kwargs):
        recorded["args"] = args
        recorded["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(session_service.subprocess, "Popen", fake_popen)

    try:
        session_service._spawn_detached_session_worker(
            command,
            log_handle=cast(TextIOWrapper, log_handle),
        )
    finally:
        log_handle.close()

    assert recorded["args"] == (command,)
    kwargs = cast(dict[str, object], recorded["kwargs"])
    expected_env = os.environ.copy()
    expected_env.pop("ESM_API_AUTH_ALLOWED_KEYS", None)
    assert kwargs == {
        "cwd": str(Path(session_service.__file__).resolve().parent),
        "env": expected_env,
        "stdout": log_handle,
        "stderr": log_handle,
        "shell": False,
        "start_new_session": True,
    }
    assert kwargs["stdout"] is not session_service.subprocess.DEVNULL
    assert kwargs["stderr"] is not session_service.subprocess.DEVNULL


def test_spawn_detached_session_worker_passes_session_store_runtime_env(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The spawned worker should receive the parent's selected session store config."""
    recorded: dict[str, object] = {}
    log_path = tmp_path / "worker.log"
    log_handle = log_path.open("a", encoding="utf-8")
    command = ["python", "session_cli.py", "run-session", "--session-id", "session-123"]

    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setenv(
        POSTGRES_SESSION_DATABASE_URL_ENV,
        "postgresql://session:secret@db.example/esm",
    )

    def fake_popen(*args, **kwargs):
        recorded["args"] = args
        recorded["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(session_service.subprocess, "Popen", fake_popen)

    try:
        session_service._spawn_detached_session_worker(
            command,
            log_handle=cast(TextIOWrapper, log_handle),
        )
    finally:
        log_handle.close()

    assert recorded["args"] == (command,)
    env = cast(dict[str, str], cast(dict[str, object], recorded["kwargs"])["env"])
    assert env[SESSION_STORE_BACKEND_ENV] == "postgres"
    assert (
        env[POSTGRES_SESSION_DATABASE_URL_ENV]
        == "postgresql://session:secret@db.example/esm"
    )


def test_build_detached_session_worker_env_preserves_session_store_runtime_env(
    monkeypatch,
) -> None:
    """Worker env should carry the same session-store backend settings as the parent."""
    monkeypatch.setenv(SESSION_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setenv(
        POSTGRES_SESSION_DATABASE_URL_ENV,
        "postgresql://session:secret@db.example/esm",
    )
    monkeypatch.setenv(ALERT_STORE_BACKEND_ENV, "postgres")
    monkeypatch.setenv(
        POSTGRES_ALERT_DATABASE_URL_ENV,
        "postgresql://alerts:secret@db.example/esm",
    )
    monkeypatch.setenv("ESM_API_AUTH_ALLOWED_KEYS", "share-api-key")
    monkeypatch.setenv("UNRELATED_PARENT_FLAG", "kept")

    worker_env = session_service._build_detached_session_worker_env()

    assert worker_env[SESSION_STORE_BACKEND_ENV] == "postgres"
    assert (
        worker_env[POSTGRES_SESSION_DATABASE_URL_ENV]
        == "postgresql://session:secret@db.example/esm"
    )
    assert worker_env[ALERT_STORE_BACKEND_ENV] == "postgres"
    assert (
        worker_env[POSTGRES_ALERT_DATABASE_URL_ENV]
        == "postgresql://alerts:secret@db.example/esm"
    )
    assert "ESM_API_AUTH_ALLOWED_KEYS" not in worker_env
    assert worker_env["UNRELATED_PARENT_FLAG"] == "kept"


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

    spawn_worker()

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
        lambda worker_log_path: context_managed_handle(
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

    spawn_worker()

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
        spawn_worker()
