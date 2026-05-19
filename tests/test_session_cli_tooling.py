"""Tests for the tooling/debugging session CLI commands and snapshot wiring.

These cases treat the CLI as a thin adapter over `session_service.py`.
They keep the supported command surface explicit without duplicating the
shared start/read/cancel business logic tests.

For the worker-observability milestone, this suite also checks that
`run-session` emits one useful parent-side failure record before an uncaught
worker exception is re-raised into the redirected worker log path.
"""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

import session_cli
from session_alert_store import clear_default_session_alert_store_cache
from session_models import SessionMetadata
from tests.session_alert_test_support import (
    FailingReadAlertStore,
    REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    build_alert_event,
    build_live_runtime_postgres_store,
    build_normalized_alert,
    build_unique_session_id,
    close_store_if_possible,
    install_runtime_postgres_session_alerts,
    select_runtime_postgres_store,
)

# Electron runtime bridge behavior is covered separately in frontend/electron tests.


@pytest.fixture(autouse=True)
def _clear_default_alert_store_cache() -> Iterator[None]:
    """Keep runtime-selected default-store caching isolated in CLI tests."""
    clear_default_session_alert_store_cache()
    yield
    clear_default_session_alert_store_cache()


def _set_argv(monkeypatch, *args: str) -> None:
    """Install one CLI argv sequence for the next `session_cli.main()` call."""
    monkeypatch.setattr("sys.argv", ["session_cli.py", *args])


def _read_session_payload(
    monkeypatch,
    capsys,
    *,
    session_id: str,
) -> dict[str, object]:
    """Run the CLI read-session command and parse its stable JSON payload."""
    _set_argv(monkeypatch, "read-session", "--session-id", session_id)
    session_cli.main()
    return json.loads(capsys.readouterr().out)


def _cli_snapshot_alert(
    session_id: str,
    *,
    timestamp_utc: str,
    title: str,
    message: str,
    source_name: str,
) -> dict[str, object]:
    """Build one normalized CLI snapshot alert payload."""
    return build_normalized_alert(
        session_id,
        timestamp_utc=timestamp_utc,
        detector_id="video_metrics",
        title=title,
        message=message,
        severity="warning",
        source_name=source_name,
    )


def _pending_metadata(
    session_id: str,
    mode: str,
    input_path: str,
    selected_detectors: list[str],
) -> SessionMetadata:
    """Build one pending session metadata payload for start-session tests."""
    return SessionMetadata(
        session_id=session_id,
        mode=mode,
        input_path=input_path,
        selected_detectors=selected_detectors,
        status="pending",
    )


def test_cli_keeps_the_supported_tooling_commands() -> None:
    """The supported tooling command set should stay explicit and stable."""
    parser = session_cli.build_parser()
    commands = parser._subparsers._group_actions[0].choices.keys()

    assert "list-detectors" in commands
    assert "start-session" in commands
    assert "read-session" in commands
    assert "cancel-session" in commands
    assert "resolve-playback-source" in commands


def test_cancel_session_returns_full_session_shape(monkeypatch, capsys) -> None:
    """Cancel-session should preserve source metadata for tooling/debugging use."""
    _set_argv(monkeypatch, "cancel-session", "--session-id", "session-123")
    monkeypatch.setattr(
        session_cli,
        "cancel_session_service",
        lambda session_id: {
            "session_id": session_id,
            "mode": "video_segments",
            "input_path": "/data/streams/segments",
            "selected_detectors": ["video_metrics"],
            "status": "cancelling",
        },
    )

    session_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["session_id"] == "session-123"
    assert payload["mode"] == "video_segments"
    assert payload["input_path"] == "/data/streams/segments"
    assert payload["selected_detectors"] == ["video_metrics"]
    assert payload["status"] == "cancelling"


def test_cancel_session_missing_returns_legacy_cli_shape(monkeypatch, capsys) -> None:
    """Cancel-session should keep the CLI's compatibility payload when missing."""
    _set_argv(monkeypatch, "cancel-session", "--session-id", "missing-session")
    monkeypatch.setattr(
        session_cli,
        "cancel_session_service",
        lambda session_id: (_ for _ in ()).throw(session_cli.SessionServiceNotFoundError(session_id)),
    )

    session_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "session_id": "missing-session",
        "mode": None,
        "input_path": None,
        "selected_detectors": [],
        "status": "cancelling",
    }


@pytest.mark.parametrize(
    ("argv", "expected_call", "metadata"),
    [
        (
            [
                "start-session",
                "--mode",
                "api_stream",
                "--input-path",
                "https://example.com/live/playlist.m3u8",
                "--detector",
                "video_blur",
            ],
            ("api_stream", "https://example.com/live/playlist.m3u8", ["video_blur"]),
            {
                "session_id": "session-api-1",
                "mode": "api_stream",
                "input_path": "https://example.com/live/playlist.m3u8",
                "selected_detectors": ["video_blur"],
            },
        ),
        (
            [
                "start-session",
                "--mode",
                "video_segments",
                "--input-path",
                "__TMP__",
                "--detector",
                "video_metrics",
            ],
            ("video_segments", "__TMP__", ["video_metrics"]),
            {
                "session_id": "session-local-1",
                "mode": "video_segments",
                "input_path": "__TMP__",
                "selected_detectors": ["video_metrics"],
            },
        ),
    ],
)
def test_start_session_passes_cli_args_to_service(
    monkeypatch, tmp_path: Path, capsys, argv: list[str], expected_call: tuple[str, str, list[str]], metadata: dict[str, object]
) -> None:
    """Start-session should keep the CLI as a thin adapter over the shared service."""
    calls: list[tuple[str, str, list[str]]] = []
    resolved_argv = [str(tmp_path) if item == "__TMP__" else item for item in argv]
    resolved_call = (
        expected_call[0],
        str(tmp_path) if expected_call[1] == "__TMP__" else expected_call[1],
        expected_call[2],
    )
    resolved_metadata = {
        **metadata,
        "input_path": str(tmp_path) if metadata["input_path"] == "__TMP__" else metadata["input_path"],
        "status": "pending",
    }

    _set_argv(monkeypatch, *resolved_argv)
    monkeypatch.setattr(
        session_cli,
        "start_session_service",
        lambda mode, input_path, selected_detectors: calls.append(
            (mode, input_path, selected_detectors)
        ) or _pending_metadata(
            session_id=str(resolved_metadata["session_id"]),
            mode=str(resolved_metadata["mode"]),
            input_path=str(resolved_metadata["input_path"]),
            selected_detectors=list(resolved_metadata["selected_detectors"]),
        ),
    )

    session_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == resolved_metadata
    assert calls == [resolved_call]


def test_read_session_returns_empty_snapshot_shape_when_missing(monkeypatch, capsys) -> None:
    """Read-session should preserve the CLI's empty snapshot shape for missing sessions."""
    _set_argv(monkeypatch, "read-session", "--session-id", "missing-session")
    monkeypatch.setattr(session_cli, "read_session_snapshot_or_none", lambda session_id: None)

    session_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "session": None,
        "progress": None,
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def test_read_session_returns_existing_snapshot_shape(monkeypatch, capsys) -> None:
    """Read-session should print the shared snapshot unchanged when it exists."""
    _set_argv(monkeypatch, "read-session", "--session-id", "session-123")
    monkeypatch.setattr(
        session_cli,
        "read_session_snapshot_or_none",
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

    session_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "session": {
            "session_id": "session-123",
            "mode": "video_files",
            "input_path": "/tmp/input.mp4",
            "selected_detectors": ["video_metrics"],
            "status": "running",
        },
        "progress": None,
        "alerts": [],
        "results": [],
        "latest_result": None,
    }


def test_read_session_uses_the_runtime_selected_postgres_alert_store(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    """Read-session should print seam-backed alerts when Postgres mode is selected."""
    session_id = "session-cli-runtime-postgres"
    alerts = [
        _cli_snapshot_alert(
            session_id,
            timestamp_utc="2026-05-19 23:15:00",
            title="CLI snapshot alert",
            message="Returned through the runtime-selected Postgres seam.",
            source_name="segment_0001.ts",
        )
    ]
    install_runtime_postgres_session_alerts(
        monkeypatch,
        tmp_path,
        session_id=session_id,
        alerts=alerts,
    )
    payload = _read_session_payload(monkeypatch, capsys, session_id=session_id)

    assert payload["alerts"] == alerts


def test_read_session_propagates_runtime_postgres_alert_store_failures(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Read-session should fail loudly when the active seam-backed read fails."""
    session_id = "session-cli-runtime-postgres-failure"
    install_runtime_postgres_session_alerts(
        monkeypatch,
        tmp_path,
        session_id=session_id,
        alerts=[],
    )
    select_runtime_postgres_store(
        monkeypatch,
        FailingReadAlertStore(session_id, "database read failed"),
    )

    _set_argv(monkeypatch, "read-session", "--session-id", session_id)
    with pytest.raises(RuntimeError, match="database read failed"):
        session_cli.main()


def test_read_session_and_service_snapshot_stay_aligned_for_known_empty_alerts_in_postgres_mode(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    """CLI and shared session service should keep the same known-empty snapshot contract."""
    import session_service

    session_id = "session-cli-runtime-postgres-empty"
    install_runtime_postgres_session_alerts(
        monkeypatch,
        tmp_path,
        session_id=session_id,
        alerts=[],
    )
    service_snapshot = session_service.read_session_snapshot_or_none(session_id)
    payload = _read_session_payload(monkeypatch, capsys, session_id=session_id)

    assert service_snapshot is not None
    assert service_snapshot["alerts"] == []
    assert payload["alerts"] == []
    assert payload["session"] == service_snapshot["session"]


@pytest.mark.skipif(
    not REAL_POSTGRES_ALERT_STORE_SMOKE_ENABLED,
    reason="Real PostgreSQL CLI snapshot smoke test is opt-in.",
)
def test_live_runtime_postgres_read_session_reads_alerts_from_the_active_backend(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    """The CLI snapshot command should follow the live runtime-selected backend."""
    session_id = build_unique_session_id("session-cli-runtime-postgres-live")
    store = build_live_runtime_postgres_store(
        monkeypatch,
        tmp_path,
        session_id=session_id,
    )
    _set_argv(monkeypatch, "read-session", "--session-id", session_id)
    expected_alerts = [
        _cli_snapshot_alert(
            session_id,
            timestamp_utc="2026-05-19 23:45:00",
            title="Live CLI snapshot alert",
            message="Read through the live runtime-selected Postgres backend.",
            source_name="segment_0001.ts",
        )
    ]

    try:
        store.append_alert(
            build_alert_event(
                session_id,
                timestamp_utc="2026-05-19 23:45:00",
                detector_id="video_metrics",
                title="Live CLI snapshot alert",
                message="Read through the live runtime-selected Postgres backend.",
                severity="warning",
                source_name="segment_0001.ts",
            )
        )
        payload = _read_session_payload(monkeypatch, capsys, session_id=session_id)
    finally:
        close_store_if_possible(store)

    assert payload["alerts"] == expected_alerts


def test_run_session_logs_useful_failure_context_before_reraising(monkeypatch) -> None:
    """Uncaught run-session failures should log redacted worker context before bubbling up."""
    calls: list[tuple[object, ...]] = []

    _set_argv(
        monkeypatch,
        "run-session",
        "--mode",
        "video_files",
        "--input-path",
        "/tmp/input.mp4",
        "--session-id",
        "session-123",
        "--detector",
        "video_metrics",
    )
    monkeypatch.setattr(session_cli, "validate_source_input", lambda mode, input_path: input_path)
    monkeypatch.setattr(
        session_cli,
        "run_local_session",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("detector crashed")),
    )
    monkeypatch.setattr(
        session_cli.logger,
        "exception",
        lambda message, context: calls.append((message, context)),
    )

    with pytest.raises(RuntimeError, match="detector crashed"):
        session_cli.main()

    assert calls == [
        (
            "run-session worker failed [%s]",
            "session_id='session-123' "
            "mode='video_files' "
            "input_path='<path:input.mp4>'",
        )
    ]


def test_resolve_playback_source_returns_remote_url_for_api_stream(monkeypatch, capsys) -> None:
    """Resolve-playback-source should return passthrough remote URLs for tooling use."""
    _set_argv(
        monkeypatch,
        "resolve-playback-source",
        "--mode",
        "api_stream",
        "--input-path",
        "https://example.com/live/playlist.m3u8",
    )

    session_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"source": "https://example.com/live/playlist.m3u8"}


def test_resolve_playback_source_returns_local_playlist_for_video_segments(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    """Resolve-playback-source should expose the local playlist path for HLS folders."""
    segment_dir = tmp_path / "segments"
    segment_dir.mkdir()
    (segment_dir / "segment_0000.ts").write_bytes(b"video")
    (segment_dir / "index.m3u8").write_text(
        "\n".join(["#EXTM3U", "#EXTINF:1.0,", "segment_0000.ts"]),
        encoding="utf-8",
    )
    _set_argv(
        monkeypatch,
        "resolve-playback-source",
        "--mode",
        "video_segments",
        "--input-path",
        str(segment_dir),
    )

    session_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"source": str(segment_dir / "index.m3u8")}


def test_start_session_rejects_unsupported_api_stream_scheme(monkeypatch) -> None:
    """Start-session should fail early for unsupported remote URL schemes."""
    _set_argv(
        monkeypatch,
        "start-session",
        "--mode",
        "api_stream",
        "--input-path",
        "file:///tmp/playlist.m3u8",
    )

    with pytest.raises(ValueError, match="Unsupported api_stream URL scheme"):
        session_cli.main()


def test_resolve_playback_source_rejects_unsupported_api_stream_scheme(
    monkeypatch,
) -> None:
    """Resolve-playback-source should fail early for unsupported remote URL schemes."""
    _set_argv(
        monkeypatch,
        "resolve-playback-source",
        "--mode",
        "api_stream",
        "--input-path",
        "file:///tmp/playlist.m3u8",
    )

    with pytest.raises(ValueError, match="Unsupported api_stream URL scheme"):
        session_cli.main()


def test_start_session_rejects_localhost_api_stream_target(monkeypatch) -> None:
    """Start-session should reject obvious internal-network probing targets by default."""
    _set_argv(
        monkeypatch,
        "start-session",
        "--mode",
        "api_stream",
        "--input-path",
        "http://localhost:8080/live.m3u8",
    )

    with pytest.raises(ValueError, match="not allowed in local mode"):
        session_cli.main()
