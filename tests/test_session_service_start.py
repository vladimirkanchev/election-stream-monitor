"""Focused tests for session start command building and start-session behavior."""

from pathlib import Path

import pytest

import session_service
from tests.session_service_test_support import (
    DEFAULT_DETECTORS,
    DEFAULT_INPUT_PATH,
    DEFAULT_SESSION_ID,
    build_run_session_command,
    build_start_log_context,
    build_worker_log_path,
    install_start_session_harness,
)


def test_start_session_happy_path(monkeypatch, tmp_path: Path) -> None:
    """Start should validate, spawn, and return pending metadata."""
    recorded: dict[str, object] = {}
    install_start_session_harness(
        monkeypatch,
        tmp_path,
        recorded,
        session_id=DEFAULT_SESSION_ID,
    )

    metadata = session_service.start_session(
        mode="video_files",
        input_path=DEFAULT_INPUT_PATH,
        selected_detectors=DEFAULT_DETECTORS,
    )

    assert metadata.to_dict() == {
        "session_id": DEFAULT_SESSION_ID,
        "mode": "video_files",
        "input_path": DEFAULT_INPUT_PATH,
        "selected_detectors": DEFAULT_DETECTORS,
        "status": "pending",
    }
    assert recorded["spawn"] == {
        "command": build_run_session_command(
            mode="video_files",
            input_path=DEFAULT_INPUT_PATH,
            session_id=DEFAULT_SESSION_ID,
            selected_detectors=DEFAULT_DETECTORS,
        ),
        "log_name": str(build_worker_log_path(tmp_path, DEFAULT_SESSION_ID)),
    }
    assert recorded["log"] == (
        "Started detached session worker [%s]",
        build_start_log_context(
            session_id=DEFAULT_SESSION_ID,
            mode="video_files",
            input_path=DEFAULT_INPUT_PATH,
        ),
    )


def test_build_run_session_command_includes_all_selected_detectors() -> None:
    """The detached worker command should preserve detector ordering and values."""
    command = build_run_session_command(
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
    install_start_session_harness(
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
        "command": build_run_session_command(
            mode="api_stream",
            input_path="https://example.com/live/index.m3u8",
            session_id="api-stream-session-123",
            selected_detectors=["video_metrics", "video_blur"],
        ),
        "log_name": str(build_worker_log_path(tmp_path, "api-stream-session-123")),
    }
    assert recorded["log"] == (
        "Started detached session worker [%s]",
        build_start_log_context(
            session_id="api-stream-session-123",
            mode="api_stream",
            input_path="https://example.com/live/index.m3u8",
        ),
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
            selected_detectors=DEFAULT_DETECTORS,
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
            selected_detectors=DEFAULT_DETECTORS,
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
        lambda: DEFAULT_SESSION_ID,
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
            selected_detectors=DEFAULT_DETECTORS,
        )


def test_start_session_copies_selected_detectors_into_metadata(monkeypatch) -> None:
    """Returned metadata should not share the caller's detector list object."""
    detectors = list(DEFAULT_DETECTORS)

    monkeypatch.setattr(
        session_service,
        "validate_source_input",
        lambda mode, input_path: input_path,
    )
    monkeypatch.setattr(
        session_service,
        "create_session_id",
        lambda: DEFAULT_SESSION_ID,
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

    assert metadata.selected_detectors == DEFAULT_DETECTORS
