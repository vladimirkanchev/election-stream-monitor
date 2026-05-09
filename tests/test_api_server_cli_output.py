"""Focused startup-output tests for the user-facing FastAPI CLI.

These cases protect the operator-facing startup summary separately from the
runtime and route-policy behavior so stdout wording changes stay easy to
review.
"""

from __future__ import annotations

import re

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
    EMPTY_ALERTS_RESPONSE,
    assert_server_runner_called_once,
    run_cli_and_capture_output,
)


@pytest.fixture(autouse=True)
def _clear_boundary_settings_caches() -> None:
    """Keep env-driven FastAPI boundary settings isolated across CLI output tests."""

    original_values = snapshot_boundary_env()
    reset_boundary_test_state()
    yield
    restore_boundary_test_state(original_values)


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
    assert "mode: share" in output
    assert "auth: enabled" in output
    assert "rate limiting: enabled" in output
    assert "Generated API key:" in output
    assert "X-API-Key" in output
    assert "production-distributed hardened" in output
    assert_server_runner_called_once(seen_calls, host="127.0.0.1", port=8123)


def test_run_from_args_prints_manual_share_mode_key_summary() -> None:
    """Manual share-mode keys should suppress generated-key startup output."""

    output, _ = run_cli_and_capture_output(
        mode="share",
        host="127.0.0.1",
        port=8000,
        api_key="manual-demo-key",
    )
    assert "API key: configured manually" in output
    assert "Generated API key:" not in output


def test_run_from_args_manual_share_mode_summary_does_not_leak_manual_key() -> None:
    """Manual share-mode startup output should never print the provided raw key."""

    output, _ = run_cli_and_capture_output(
        mode="share",
        host="127.0.0.1",
        port=8000,
        api_key="manual-demo-key",
    )
    assert "API key: configured manually" in output
    assert "manual-demo-key" not in output


def test_run_from_args_prints_local_mode_summary_without_share_guidance() -> None:
    """Local startup output should stay simple and should not mention protected sharing."""

    output, seen_calls = run_cli_and_capture_output(
        mode="local",
        host="0.0.0.0",
        port=9001,
    )
    assert "mode: local" in output
    assert "listen: http://0.0.0.0:9001" in output
    assert "auth: disabled" in output
    assert "rate limiting: disabled" in output
    assert "Generated API key:" not in output
    assert "X-API-Key" not in output
    assert_server_runner_called_once(seen_calls, host="0.0.0.0", port=9001)
