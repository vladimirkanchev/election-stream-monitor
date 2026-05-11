"""Shared helpers for the split FastAPI CLI test slice.

This module intentionally stays small and scenario-oriented. It owns only:

- one empty successful alerts payload
- one empty successful alerts summary payload
- one helper for installing empty alert-route services plus CLI runtime setup
- one helper for deriving request headers from a prepared runtime
- one helper for capturing CLI stdout plus fake server handoff data

That keeps the runtime, route, and output test files focused on the policy
they are proving instead of repeating setup and fake-runner boilerplate.
"""

from __future__ import annotations

import argparse
import io
from collections.abc import Sequence

from api_server_cli import FastApiCliRuntime, prepare_cli_runtime, run_from_args
from tests.api_alert_test_support import (
    build_api_key_headers,
    install_empty_alert_route_services,
)

EMPTY_ALERTS_RESPONSE = {
    "session_id": "session-123",
    "alerts": [],
}

EMPTY_ALERT_SUMMARY_RESPONSE = {
    "session_id": "session-123",
    "total_alerts": 0,
    "counts_by_detector": {},
    "counts_by_severity": {},
    "first_alert_timestamp_utc": None,
    "last_alert_timestamp_utc": None,
}


def prepare_runtime_with_empty_alert_routes(
    monkeypatch,
    *,
    mode: str,
    manual_api_key: str | None = None,
) -> FastApiCliRuntime:
    """Install empty alert-route services and prepare one CLI runtime.

    This keeps the route-oriented CLI tests focused on the boundary policy
    under test instead of repeating the same empty successful route adapter
    setup in every scenario.
    """

    install_empty_alert_route_services(monkeypatch)
    return prepare_cli_runtime(mode=mode, manual_api_key=manual_api_key)


def install_one_request_rate_limit_env(monkeypatch, *, window_seconds: int = 60) -> None:
    """Install one tiny fixed-window limiter config for CLI route scenarios."""

    monkeypatch.setenv("ESM_API_RATE_LIMIT_MAX_REQUESTS", "1")
    monkeypatch.setenv("ESM_API_RATE_LIMIT_WINDOW_SEC", str(window_seconds))


def build_runtime_headers(
    runtime: FastApiCliRuntime,
    *,
    fallback_key: str | None = None,
) -> dict[str, str]:
    """Build one API-key header set from a prepared CLI runtime.

    Share mode may authenticate with either:

    - one generated runtime key
    - one explicit manual key supplied during setup

    The helper keeps that distinction out of the route scenarios so they can
    read like ordinary HTTP examples.
    """

    if runtime.auth_settings.generated_api_key is not None:
        return build_api_key_headers(runtime.auth_settings.generated_api_key)
    if fallback_key is None:
        raise AssertionError(
            "A manual key is required when the runtime did not generate one"
        )
    return build_api_key_headers(fallback_key)


def run_cli_and_capture_output(
    *,
    mode: str,
    host: str,
    port: int,
    api_key: str | None = None,
) -> tuple[str, list[dict[str, object]]]:
    """Run the CLI against a fake server runner and capture observable output."""

    stdout = io.StringIO()
    seen_calls: list[dict[str, object]] = []

    def fake_server_runner(app, *, host: str, port: int) -> None:
        seen_calls.append(
            {
                "app": app,
                "host": host,
                "port": port,
            }
        )

    run_from_args(
        argparse.Namespace(
            mode=mode,
            host=host,
            port=port,
            api_key=api_key,
        ),
        stdout=stdout,
        server_runner=fake_server_runner,
    )
    return stdout.getvalue(), seen_calls


def assert_server_runner_called_once(
    seen_calls: Sequence[dict[str, object]],
    *,
    host: str,
    port: int,
) -> None:
    """Assert one fake CLI server handoff without pinning the app identity twice."""

    assert len(seen_calls) == 1
    assert seen_calls[0]["host"] == host
    assert seen_calls[0]["port"] == port
