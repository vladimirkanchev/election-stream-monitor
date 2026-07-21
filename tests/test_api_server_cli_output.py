"""Focused startup-output tests for the user-facing FastAPI CLI.

These cases protect the operator-facing startup summary separately from the
runtime and route-policy behavior so stdout wording changes stay easy to
review.

The CLI is no longer the primary desktop runtime path, but the startup output
still matters because it is the first thing operators and developers see when
they use backend-only `local` or `share` mode directly.

This file currently owns:

- generated-key share-mode guidance
- manual-key share-mode guidance
- custom listen-address reflection in startup output
- the split between local open startup and protected share startup messaging
"""

from __future__ import annotations

import re
from collections.abc import Generator

import pytest

from tests.api_alert_test_support import (
    build_api_key_headers,
    install_empty_alert_route_services,
)
from tests.api_boundary_env_test_support import (
    reset_boundary_test_state,
    restore_boundary_test_state,
    snapshot_boundary_env,
)
from tests.api_boundary_test_support import request
from tests.api_server_cli_test_support import (
    CliMode,
    EMPTY_ALERTS_RESPONSE,
    assert_server_runner_called_once,
    run_cli_and_capture_output,
)


@pytest.fixture(autouse=True)
def _clear_boundary_settings_caches() -> Generator[None, None, None]:
    """Keep env-driven FastAPI boundary settings isolated across CLI output tests."""

    original_values = snapshot_boundary_env()
    reset_boundary_test_state()
    yield
    restore_boundary_test_state(original_values)


def _assert_share_mode_listen_summary(output: str, *, host: str, port: int) -> None:
    """Assert the common share-mode startup summary header for one CLI run.

    This is the stable high-level block that should stay aligned across
    generated-key and manual-key share-mode startup paths.
    """
    assert "mode: share" in output
    assert f"listen: http://{host}:{port}" in output
    assert "auth: enabled" in output
    assert "rate limiting: enabled" in output


def _assert_manual_share_mode_summary(output: str, *, host: str, port: int) -> None:
    """Assert the common manual-key share-mode summary without raw key leakage.

    Manual share mode intentionally differs from generated-key share mode:
    operators should see that a key was configured, but should not see
    copy-paste guidance that implies the CLI generated one for them.
    """
    _assert_share_mode_listen_summary(output, host=host, port=port)
    assert "API key: configured manually" in output
    assert "Generated API key:" not in output


def _assert_local_mode_listen_summary(output: str, *, host: str, port: int) -> None:
    """Assert the stable local-mode startup summary for one CLI run.

    Local mode stays intentionally simple: no API-key guidance, no protected
    sharing language, and one clear listen address for direct backend use.
    """
    assert "mode: local" in output
    assert f"listen: http://{host}:{port}" in output
    assert "auth: disabled" in output
    assert "rate limiting: disabled" in output


def test_run_from_args_generated_share_key_matches_real_accepted_route_key(
    monkeypatch,
) -> None:
    """The key printed during share-mode startup should be usable on the real route.

    This is the highest-signal startup-output regression in the file because it
    proves the generated key shown to the operator is also the key that the
    protected route actually accepts.
    """

    install_empty_alert_route_services(monkeypatch)
    output, _ = run_cli_and_capture_output(
        mode="share",
        host="127.0.0.1",
        port=8124,
    )
    match = re.search(
        r"^Generated API key:\n(?P<api_key>esm_share_[A-Za-z0-9_-]+)$",
        output,
        re.M,
    )
    assert match is not None

    response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_api_key_headers(match.group("api_key")),
    )

    assert response.status_code == 200
    assert response.json() == EMPTY_ALERTS_RESPONSE


def test_run_from_args_prints_generated_share_mode_key_and_starts_server() -> None:
    """Share-mode startup output should expose the generated API key once."""

    output, seen_calls = run_cli_and_capture_output(
        mode="share",
        host="127.0.0.1",
        port=8123,
    )
    _assert_share_mode_listen_summary(output, host="127.0.0.1", port=8123)
    match = re.search(r"^Generated API key:\n(?P<api_key>\S+)$", output, re.M)
    assert match is not None
    assert output.count(match.group("api_key")) == 1
    assert "X-API-Key: <generated-api-key>" in output
    assert "production-distributed hardened" in output
    assert_server_runner_called_once(seen_calls, host="127.0.0.1", port=8123)


def test_run_from_args_share_mode_generated_key_output_includes_operator_guidance() -> None:
    """Generated-key share startup should print one usable operator guidance block."""

    output, seen_calls = run_cli_and_capture_output(
        mode="share",
        host="127.0.0.1",
        port=8017,
    )

    _assert_share_mode_listen_summary(output, host="127.0.0.1", port=8017)
    assert "Generated API key:" in output
    assert "X-API-Key" in output
    assert "share mode is for temporary protected demo/shared access." in output
    assert_server_runner_called_once(seen_calls, host="127.0.0.1", port=8017)


def test_run_from_args_prints_manual_share_mode_key_summary() -> None:
    """Manual share-mode keys should suppress generated-key startup output."""

    output, _ = run_cli_and_capture_output(
        mode="share",
        host="127.0.0.1",
        port=8000,
        api_key="manual-demo-key",
    )
    _assert_manual_share_mode_summary(output, host="127.0.0.1", port=8000)


def test_run_from_args_manual_share_mode_summary_does_not_leak_manual_key(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Manual keys must stay absent from operator output and logs."""

    manual_key = "manual-demo-key"
    output, _ = run_cli_and_capture_output(
        mode="share",
        host="127.0.0.1",
        port=8000,
        api_key=manual_key,
    )
    captured = capsys.readouterr()

    _assert_manual_share_mode_summary(output, host="127.0.0.1", port=8000)
    assert all(
        manual_key not in sink
        for sink in (output, captured.out, captured.err, caplog.text)
    )


def test_run_from_args_manual_share_mode_output_does_not_claim_generated_key_behavior() -> None:
    """Manual-key share startup should stay distinct from generated-key guidance."""

    output, _ = run_cli_and_capture_output(
        mode="share",
        host="127.0.0.1",
        port=8020,
        api_key="manual-demo-key",
    )

    _assert_manual_share_mode_summary(output, host="127.0.0.1", port=8020)
    assert "Send it in the X-API-Key header." not in output


@pytest.mark.parametrize(
    ("mode", "host", "port", "api_key"),
    [
        ("share", "0.0.0.0", 8456, "manual-demo-key"),
        ("local", "127.0.0.2", 9456, None),
    ],
)
def test_run_from_args_reflects_custom_listen_address_in_manual_share_and_local_modes(
    mode: CliMode,
    host: str,
    port: int,
    api_key: str | None,
) -> None:
    """Custom host and port output should stay aligned with the chosen CLI mode.

    This keeps the output contract honest for both:

    - manual-key share startup, where the listen address is part of operator guidance
    - local startup, where the listen address is the main useful runtime cue
    """

    output, seen_calls = run_cli_and_capture_output(
        mode=mode,
        host=host,
        port=port,
        api_key=api_key,
    )

    if mode == "share":
        _assert_manual_share_mode_summary(output, host=host, port=port)
    else:
        _assert_local_mode_listen_summary(output, host=host, port=port)

    assert_server_runner_called_once(seen_calls, host=host, port=port)


def test_run_from_args_prints_local_mode_summary_without_share_guidance() -> None:
    """Local startup output should stay simple and should not mention protected sharing."""

    output, seen_calls = run_cli_and_capture_output(
        mode="local",
        host="127.0.0.1",
        port=9001,
    )
    _assert_local_mode_listen_summary(output, host="127.0.0.1", port=9001)
    assert "Generated API key:" not in output
    assert "X-API-Key" not in output
    assert_server_runner_called_once(seen_calls, host="127.0.0.1", port=9001)
