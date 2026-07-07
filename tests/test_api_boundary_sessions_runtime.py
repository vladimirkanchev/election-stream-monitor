"""Runtime-focused FastAPI session integration checks.

These tests keep one runtime promise honest: the FastAPI session routes and
the detached worker must still meet at a readable persisted snapshot.

Routine runs keep this lane file-backed on purpose. Live PostgreSQL runtime
confidence belongs in a separate opt-in smoke lane.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import time
from typing import cast
from uuid import uuid4

import pytest

import session_service
from session_alert_store import clear_default_session_alert_store_cache
from session_io import get_session_dir, get_worker_log_path
from session_store_postgres_config import POSTGRES_SESSION_DATABASE_URL_ENV
from session_store_runtime import clear_default_session_store_cache
from tests.api_boundary_sessions_test_support import session_not_found_payload
from tests.api_boundary_test_support import request

POLL_INTERVAL_SEC = 0.05
DEFAULT_SEGMENT_COUNT = 2
CANCEL_TEST_SEGMENT_COUNT = 4000


@dataclass(frozen=True)
class RuntimeSessionCase:
    """Minimal runtime test input for one detached-worker session run."""

    session_id: str
    input_dir: Path
    segment_count: int

    @property
    def start_request(self) -> dict[str, object]:
        """Return the API payload used to start this runtime case."""
        return {
            "mode": "video_segments",
            "input_path": str(self.input_dir),
            "selected_detectors": [],
        }

    @property
    def pending_response(self) -> dict[str, object]:
        """Return the expected accepted-start payload for this case."""
        return {
            "session_id": self.session_id,
            "mode": "video_segments",
            "input_path": str(self.input_dir),
            "selected_detectors": [],
            "status": "pending",
        }


@pytest.fixture(autouse=True)
def _clear_runtime_store_caches() -> Iterator[None]:
    """Reset cached stores so each test sees only its own runtime settings."""
    clear_default_session_store_cache()
    clear_default_session_alert_store_cache()
    yield
    clear_default_session_alert_store_cache()
    clear_default_session_store_cache()


@pytest.fixture(autouse=True)
def _use_file_backed_runtime_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin routine runtime checks to the default file-backed session store."""
    monkeypatch.setenv("ESM_SESSION_STORE_BACKEND", "file")


def _write_segment_inputs(
    input_dir: Path,
    *,
    count: int = DEFAULT_SEGMENT_COUNT,
) -> None:
    """Create a compact local segment set for the detached worker path."""
    input_dir.mkdir()
    for index in range(1, count + 1):
        (input_dir / f"segment_{index:04d}.ts").write_bytes(b"ts")


@contextmanager
def _runtime_session_case(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    name: str,
    segment_count: int = DEFAULT_SEGMENT_COUNT,
) -> Iterator[RuntimeSessionCase]:
    """Create one isolated runtime case and clean its session artifacts."""
    session_case = RuntimeSessionCase(
        session_id=f"session-runtime-{name}-{uuid4().hex[:8]}",
        input_dir=tmp_path / "segments",
        segment_count=segment_count,
    )
    _write_segment_inputs(session_case.input_dir, count=segment_count)
    monkeypatch.setattr(
        session_service,
        "create_session_id",
        lambda: session_case.session_id,
    )

    _remove_runtime_session_artifacts(session_case.session_id)
    try:
        yield session_case
    finally:
        _remove_runtime_session_artifacts(session_case.session_id)


def _remove_runtime_session_artifacts(session_id: str) -> None:
    """Delete the session directory created for one runtime test case."""
    session_dir = get_session_dir(session_id)
    if session_dir.exists():
        shutil.rmtree(session_dir)


def _worker_log_text(session_id: str) -> str:
    """Return worker-log text for timeout diagnostics when it exists."""
    worker_log_path = get_worker_log_path(session_id)
    if not worker_log_path.exists():
        return "<worker.log not created>"
    return worker_log_path.read_text(encoding="utf-8")


def _assert_file_backed_session_artifacts_exist(session_id: str) -> None:
    """Confirm the default runtime path wrote the canonical session files."""
    session_dir = get_session_dir(session_id)
    assert (session_dir / "session.json").exists()
    assert (session_dir / "progress.json").exists()
    assert (session_dir / "worker.log").exists()


def _session_payload(snapshot: dict[str, object]) -> dict[str, object]:
    """Return the session payload from a readable runtime snapshot."""
    return cast(dict[str, object], snapshot["session"])


def _progress_payload(snapshot: dict[str, object]) -> dict[str, object]:
    """Return the progress payload from a readable runtime snapshot."""
    return cast(dict[str, object], snapshot["progress"])


def _start_runtime_session(session_case: RuntimeSessionCase) -> None:
    """Start one runtime session and assert the accepted pending response."""
    start_response = request("POST", "/sessions", json=session_case.start_request)

    assert start_response.status_code == 200
    assert start_response.json() == session_case.pending_response


def _assert_no_detector_outputs(snapshot: dict[str, object]) -> None:
    """Confirm the empty-detector runtime path has no result or alert output."""
    assert snapshot["alerts"] == []
    assert snapshot["results"] == []
    assert snapshot["latest_result"] is None


def _assert_snapshot_belongs_to(
    snapshot: dict[str, object],
    session_case: RuntimeSessionCase,
) -> None:
    """Confirm that a readable snapshot belongs to the expected runtime case."""
    assert _session_payload(snapshot)["session_id"] == session_case.session_id
    assert _progress_payload(snapshot)["session_id"] == session_case.session_id


def _install_delayed_worker_start(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    delay_sec: float,
) -> None:
    """Delay the real worker entrypoint long enough to exercise early reads."""
    original_builder = session_service._build_run_session_command
    wrapper_path = tmp_path / "delayed_session_worker.py"
    wrapper_path.write_text(
        "\n".join(
            [
                "import runpy",
                "import sys",
                "import time",
                "",
                "delay_sec = float(sys.argv[1])",
                "session_cli_path = sys.argv[2]",
                "forwarded_args = sys.argv[3:]",
                "time.sleep(delay_sec)",
                'sys.argv = [session_cli_path, *forwarded_args]',
                'runpy.run_path(session_cli_path, run_name="__main__")',
                "",
            ]
        ),
        encoding="utf-8",
    )

    def delayed_command(**kwargs: object) -> list[str]:
        original_command = original_builder(**kwargs)
        python_executable = original_command[0]
        session_cli_path = original_command[1]
        forwarded_args = original_command[2:]
        return [
            python_executable,
            str(wrapper_path),
            str(delay_sec),
            session_cli_path,
            *forwarded_args,
        ]

    monkeypatch.setattr(session_service, "_build_run_session_command", delayed_command)


def _wait_for_readable_snapshot(
    session_id: str,
    *,
    timeout_sec: float = 5.0,
) -> dict[str, object]:
    """Poll until the detached worker has written a readable snapshot."""
    deadline = time.monotonic() + timeout_sec
    last_status: int | None = None
    last_body: object = None

    while time.monotonic() < deadline:
        response = request("GET", f"/sessions/{session_id}")
        last_status = response.status_code
        payload = response.json()
        last_body = payload

        if response.status_code == 200:
            if payload["session"] is not None and payload["progress"] is not None:
                return payload

        time.sleep(POLL_INTERVAL_SEC)

    raise AssertionError(
        "Timed out waiting for a readable runtime snapshot. "
        f"session_id={session_id} last_status={last_status} "
        f"last_body={json.dumps(last_body, sort_keys=True)} "
        f"worker_log={_worker_log_text(session_id)!r}"
    )


def _wait_for_terminal_status(
    session_id: str,
    *,
    expected_status: str,
    timeout_sec: float = 5.0,
) -> dict[str, object]:
    """Poll until the readable snapshot reaches the expected terminal status."""
    deadline = time.monotonic() + timeout_sec
    last_payload: dict[str, object] | None = None

    while time.monotonic() < deadline:
        response = request("GET", f"/sessions/{session_id}")
        if response.status_code == 200:
            payload = response.json()
            last_payload = payload
            session = payload["session"]
            progress = payload["progress"]
            if (
                isinstance(session, dict)
                and isinstance(progress, dict)
                and session.get("status") == expected_status
                and progress.get("status") == expected_status
            ):
                return payload

        time.sleep(POLL_INTERVAL_SEC)

    raise AssertionError(
        f"Timed out waiting for terminal status {expected_status!r} "
        f"for session_id={session_id}. "
        f"last_payload={json.dumps(last_payload, sort_keys=True)} "
        f"worker_log={_worker_log_text(session_id)!r}"
    )


def _wait_for_cancelable_snapshot(
    session_id: str,
    *,
    timeout_sec: float = 5.0,
) -> dict[str, object]:
    """Poll until the session is readable while still non-terminal."""
    deadline = time.monotonic() + timeout_sec
    last_payload: dict[str, object] | None = None

    while time.monotonic() < deadline:
        response = request("GET", f"/sessions/{session_id}")
        if response.status_code == 200:
            payload = response.json()
            last_payload = payload
            session = payload["session"]
            progress = payload["progress"]
            if (
                isinstance(session, dict)
                and isinstance(progress, dict)
                and session.get("status") in {"pending", "running", "cancelling"}
                and progress.get("status") in {"pending", "running", "cancelling"}
            ):
                return payload

        time.sleep(POLL_INTERVAL_SEC)

    raise AssertionError(
        "Timed out waiting for a readable non-terminal runtime snapshot. "
        f"session_id={session_id} "
        f"last_payload={json.dumps(last_payload, sort_keys=True)} "
        f"worker_log={_worker_log_text(session_id)!r}"
    )


def test_sessions_start_runtime_path_persists_a_readable_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A real start request should lead to a readable completed snapshot."""
    with _runtime_session_case(monkeypatch, tmp_path, name="fastapi") as session_case:
        _start_runtime_session(session_case)

        readable_snapshot = _wait_for_readable_snapshot(session_case.session_id)
        session = _session_payload(readable_snapshot)
        progress = _progress_payload(readable_snapshot)

        assert session == {
            "session_id": session_case.session_id,
            "mode": "video_segments",
            "input_path": str(session_case.input_dir),
            "selected_detectors": [],
            "status": session["status"],
        }
        assert progress["session_id"] == session_case.session_id
        _assert_no_detector_outputs(readable_snapshot)

        completed_snapshot = _wait_for_terminal_status(
            session_case.session_id,
            expected_status="completed",
        )
        completed_progress = _progress_payload(completed_snapshot)

        _assert_file_backed_session_artifacts_exist(session_case.session_id)
        assert completed_progress["processed_count"] == session_case.segment_count
        assert completed_progress["total_count"] == session_case.segment_count
        assert completed_progress["current_item"] == "segment_0002.ts"
        assert completed_progress["status_reason"] == "completed"
        assert completed_progress["status_detail"] is None


def test_sessions_cancel_runtime_path_reaches_worker_through_durable_cancel_intent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A real cancel request should settle the detached worker to `cancelled`."""
    with _runtime_session_case(
        monkeypatch,
        tmp_path,
        name="cancel",
        segment_count=CANCEL_TEST_SEGMENT_COUNT,
    ) as session_case:
        _start_runtime_session(session_case)

        cancelable_snapshot = _wait_for_cancelable_snapshot(session_case.session_id)
        cancel_response = request("POST", f"/sessions/{session_case.session_id}/cancel")

        assert _session_payload(cancelable_snapshot)["session_id"] == (
            session_case.session_id
        )
        assert cancel_response.status_code == 200
        assert cancel_response.json() == {
            "session_id": session_case.session_id,
            "mode": "video_segments",
            "input_path": str(session_case.input_dir),
            "selected_detectors": [],
            "status": "cancelling",
        }

        cancelled_snapshot = _wait_for_terminal_status(
            session_case.session_id,
            expected_status="cancelled",
        )
        cancelled_session = _session_payload(cancelled_snapshot)
        cancelled_progress = _progress_payload(cancelled_snapshot)

        assert cancelled_session["status"] == "cancelled"
        assert cancelled_progress["status"] == "cancelled"
        assert cancelled_progress["status_reason"] == "cancel_requested"
        assert cancelled_progress["processed_count"] < session_case.segment_count
        assert cancelled_progress["total_count"] == session_case.segment_count
        _assert_file_backed_session_artifacts_exist(session_case.session_id)
        _assert_no_detector_outputs(cancelled_snapshot)


def test_sessions_start_runtime_path_keeps_early_read_honest_before_worker_catches_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An accepted start may briefly read as missing before worker catch-up."""
    _install_delayed_worker_start(monkeypatch, tmp_path, delay_sec=0.35)

    with _runtime_session_case(monkeypatch, tmp_path, name="early-read") as session_case:
        _start_runtime_session(session_case)

        early_read_response = request("GET", f"/sessions/{session_case.session_id}")
        assert early_read_response.status_code == 404
        assert early_read_response.json() == session_not_found_payload(
            session_case.session_id
        )

        readable_snapshot = _wait_for_readable_snapshot(session_case.session_id)
        _assert_snapshot_belongs_to(readable_snapshot, session_case)

        completed_snapshot = _wait_for_terminal_status(
            session_case.session_id,
            expected_status="completed",
        )
        completed_session = _session_payload(completed_snapshot)
        completed_progress = _progress_payload(completed_snapshot)

        _assert_file_backed_session_artifacts_exist(session_case.session_id)
        assert completed_session["status"] == "completed"
        assert completed_progress["status"] == "completed"
        assert completed_progress["processed_count"] == session_case.segment_count
        assert completed_progress["total_count"] == session_case.segment_count


def test_sessions_runtime_path_keeps_parent_and_worker_on_file_backend_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Conflicting PostgreSQL env should not pull this runtime path off file mode."""
    monkeypatch.setenv(
        POSTGRES_SESSION_DATABASE_URL_ENV,
        "not-a-postgres-url://should-not-be-used",
    )

    with _runtime_session_case(
        monkeypatch,
        tmp_path,
        name="backend-selection",
    ) as session_case:
        _start_runtime_session(session_case)

        readable_snapshot = _wait_for_readable_snapshot(session_case.session_id)
        completed_snapshot = _wait_for_terminal_status(
            session_case.session_id,
            expected_status="completed",
        )
        completed_session = _session_payload(completed_snapshot)
        completed_progress = _progress_payload(completed_snapshot)

        _assert_file_backed_session_artifacts_exist(session_case.session_id)
        _assert_snapshot_belongs_to(readable_snapshot, session_case)
        assert completed_session["status"] == "completed"
        assert completed_progress["status"] == "completed"
        assert completed_progress["total_count"] == session_case.segment_count
        assert POSTGRES_SESSION_DATABASE_URL_ENV not in _worker_log_text(
            session_case.session_id
        )
