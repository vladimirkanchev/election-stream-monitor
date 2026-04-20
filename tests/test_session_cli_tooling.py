"""Tests for the tooling/debugging session CLI commands.

These tests keep the supported Python CLI surface explicit for scripted
inspection, manual lifecycle control, and backend diagnostics. They are not
the primary Electron runtime transport tests.
"""

import json
from pathlib import Path

import pytest

import session_cli

# Electron runtime bridge behavior is covered separately in frontend/electron tests.


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
    monkeypatch.setattr(
        "sys.argv",
        ["session_cli.py", "cancel-session", "--session-id", "session-123"],
    )
    monkeypatch.setattr(session_cli, "request_session_cancel", lambda session_id: None)
    monkeypatch.setattr(
        session_cli,
        "read_session_snapshot",
        lambda session_id: {
            "session": {
                "session_id": session_id,
                "mode": "video_segments",
                "input_path": "/data/streams/segments",
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
    assert payload["session_id"] == "session-123"
    assert payload["mode"] == "video_segments"
    assert payload["input_path"] == "/data/streams/segments"
    assert payload["selected_detectors"] == ["video_metrics"]
    assert payload["status"] == "cancelling"


def test_start_session_returns_pending_shape_for_api_stream(monkeypatch, capsys) -> None:
    """Start-session should preserve api_stream shape for tooling/debugging use."""
    popen_calls: list[dict[str, object]] = []

    class DummyPopen:
        def __init__(self, command, **kwargs):
            popen_calls.append({"command": command, "kwargs": kwargs})

    monkeypatch.setattr(
        "sys.argv",
        [
            "session_cli.py",
            "start-session",
            "--mode",
            "api_stream",
            "--input-path",
            "https://example.com/live/playlist.m3u8",
            "--detector",
            "video_blur",
        ],
    )
    monkeypatch.setattr(session_cli, "create_session_id", lambda: "session-api-1")
    monkeypatch.setattr(session_cli.subprocess, "Popen", DummyPopen)

    session_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "session_id": "session-api-1",
        "mode": "api_stream",
        "input_path": "https://example.com/live/playlist.m3u8",
        "selected_detectors": ["video_blur"],
        "status": "pending",
    }
    assert popen_calls
    assert "--mode" in popen_calls[0]["command"]
    assert "api_stream" in popen_calls[0]["command"]


def test_start_session_uses_detached_child_process_settings(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    """Start-session should spawn the internal run-session worker with stable settings."""
    popen_calls: list[dict[str, object]] = []

    class DummyPopen:
        def __init__(self, command, **kwargs):
            popen_calls.append({"command": command, "kwargs": kwargs})

    monkeypatch.setattr(
        "sys.argv",
        [
            "session_cli.py",
            "start-session",
            "--mode",
            "video_segments",
            "--input-path",
            str(tmp_path),
            "--detector",
            "video_metrics",
        ],
    )
    monkeypatch.setattr(session_cli, "create_session_id", lambda: "session-local-1")
    monkeypatch.setattr(session_cli.subprocess, "Popen", DummyPopen)

    session_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "session_id": "session-local-1",
        "mode": "video_segments",
        "input_path": str(tmp_path),
        "selected_detectors": ["video_metrics"],
        "status": "pending",
    }
    assert len(popen_calls) == 1
    popen_call = popen_calls[0]
    assert popen_call["command"] == [
        session_cli.sys.executable,
        str(Path(session_cli.__file__).resolve()),
        "run-session",
        "--mode",
        "video_segments",
        "--input-path",
        str(tmp_path),
        "--session-id",
        "session-local-1",
        "--detector",
        "video_metrics",
    ]
    assert popen_call["kwargs"]["cwd"] == str(Path(session_cli.__file__).resolve().parent)
    assert popen_call["kwargs"]["stdout"] is session_cli.subprocess.DEVNULL
    assert popen_call["kwargs"]["stderr"] is session_cli.subprocess.DEVNULL
    assert popen_call["kwargs"]["start_new_session"] is True


def test_resolve_playback_source_returns_remote_url_for_api_stream(monkeypatch, capsys) -> None:
    """Resolve-playback-source should return passthrough remote URLs for tooling use."""
    monkeypatch.setattr(
        "sys.argv",
        [
            "session_cli.py",
            "resolve-playback-source",
            "--mode",
            "api_stream",
            "--input-path",
            "https://example.com/live/playlist.m3u8",
        ],
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
    monkeypatch.setattr(
        "sys.argv",
        [
            "session_cli.py",
            "resolve-playback-source",
            "--mode",
            "video_segments",
            "--input-path",
            str(segment_dir),
        ],
    )

    session_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"source": str(segment_dir / "index.m3u8")}


def test_start_session_rejects_unsupported_api_stream_scheme(monkeypatch) -> None:
    """Start-session should fail early for unsupported remote URL schemes."""
    monkeypatch.setattr(
        "sys.argv",
        [
            "session_cli.py",
            "start-session",
            "--mode",
            "api_stream",
            "--input-path",
            "file:///tmp/playlist.m3u8",
        ],
    )

    with pytest.raises(ValueError, match="Unsupported api_stream URL scheme"):
        session_cli.main()


def test_resolve_playback_source_rejects_unsupported_api_stream_scheme(
    monkeypatch,
) -> None:
    """Resolve-playback-source should fail early for unsupported remote URL schemes."""
    monkeypatch.setattr(
        "sys.argv",
        [
            "session_cli.py",
            "resolve-playback-source",
            "--mode",
            "api_stream",
            "--input-path",
            "file:///tmp/playlist.m3u8",
        ],
    )

    with pytest.raises(ValueError, match="Unsupported api_stream URL scheme"):
        session_cli.main()


def test_start_session_rejects_localhost_api_stream_target(monkeypatch) -> None:
    """Start-session should reject obvious internal-network probing targets by default."""
    monkeypatch.setattr(
        "sys.argv",
        [
            "session_cli.py",
            "start-session",
            "--mode",
            "api_stream",
            "--input-path",
            "http://localhost:8080/live.m3u8",
        ],
    )

    with pytest.raises(ValueError, match="not allowed in local mode"):
        session_cli.main()
