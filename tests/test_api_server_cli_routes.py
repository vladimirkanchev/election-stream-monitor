"""Focused route-level tests for CLI-prepared FastAPI run modes.

These cases prove that `prepare_cli_runtime(...)` does not only resolve
settings correctly, but also drives the real protected operational-route
behavior for local and share mode.

The file intentionally stays at the HTTP boundary level:

- request succeeds or fails through real routes
- auth and limiter interaction is visible as `401` and `429`
- router-level auth covers session and playback operations in share mode
- CLI-prepared share mode keeps intentional public routes outside that boundary
- public FastAPI schema and detector-discovery surfaces remain outside the
  operational-router authentication boundary
"""

from __future__ import annotations

from collections.abc import Generator
from typing import cast

import httpx
import pytest

from api.app import app
from tests.api_alert_test_support import (
    build_authentication_failed_payload,
    build_rate_limit_exceeded_payload,
)
from tests.api_boundary_env_test_support import (
    reset_boundary_test_state,
    restore_boundary_test_state,
    snapshot_boundary_env,
)
from tests.api_boundary_test_support import request
from tests.api_server_cli_test_support import (
    EMPTY_ALERTS_RESPONSE,
    EMPTY_ALERT_SUMMARY_RESPONSE,
    build_runtime_headers,
    install_one_request_rate_limit_env,
    prepare_runtime_with_empty_alert_routes,
)


@pytest.fixture(autouse=True)
def _clear_boundary_settings_caches() -> Generator[None, None, None]:
    """Keep env-driven FastAPI boundary settings isolated across CLI route tests."""

    original_values = snapshot_boundary_env()
    reset_boundary_test_state()
    yield
    restore_boundary_test_state(original_values)


def _assert_public_routes_remain_open() -> None:
    """Assert intentional public routes stay outside operational-router auth.

    This is the highest-value CLI route-scope regression in the file because
    it proves CLI-prepared share mode keeps the minimal health/docs boundary
    public before the more specific route checks below.
    """
    health_response = request("GET", "/health")
    docs_response = request("GET", "/docs")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert docs_response.status_code == 200


def _assert_public_get_route_is_open(path: str) -> httpx.Response:
    """Assert one public GET route remains outside the share-mode auth boundary.

    The helper keeps the public-route tests transport-focused while leaving the
    route-specific payload assertion in the individual scenario that cares
    about it.
    """

    response = request("GET", path)

    assert response.status_code == 200
    return response


@pytest.mark.parametrize(
    ("path", "manual_api_key", "expected_payload"),
    [
        ("/sessions/session-123/alerts", None, EMPTY_ALERTS_RESPONSE),
        ("/sessions/session-123/alerts", "manual-demo-key", EMPTY_ALERTS_RESPONSE),
        ("/sessions/session-123/alerts/summary", None, EMPTY_ALERT_SUMMARY_RESPONSE),
        (
            "/sessions/session-123/alerts/summary",
            "manual-demo-key",
            EMPTY_ALERT_SUMMARY_RESPONSE,
        ),
    ],
)
def test_prepare_cli_runtime_share_mode_allows_empty_alert_routes_for_valid_keys(
    monkeypatch,
    path: str,
    manual_api_key: str | None,
    expected_payload: dict[str, object],
) -> None:
    """Valid generated and manual share-mode keys should unlock protected read routes.

    The matrix intentionally covers both the raw alerts route and the summary
    route so route-by-route auth drift is caught in one place.
    """

    runtime = prepare_runtime_with_empty_alert_routes(
        monkeypatch,
        mode="share",
        manual_api_key=manual_api_key,
    )
    response = request(
        "GET",
        path,
        headers=build_runtime_headers(runtime, fallback_key=manual_api_key),
    )

    assert response.status_code == 200
    assert response.json() == expected_payload


def test_prepare_cli_runtime_share_mode_generated_key_rejects_wrong_credential(
    monkeypatch,
) -> None:
    """Share mode should still reject callers that do not present the generated key."""

    prepare_runtime_with_empty_alert_routes(
        monkeypatch,
        mode="share",
    )

    response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers={"X-API-Key": "wrong-share-key"},
    )

    assert response.status_code == 401
    assert response.json() == build_authentication_failed_payload("Invalid API key")


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "POST",
            "/sessions",
            {
                "mode": "video_files",
                "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
                "selected_detectors": [],
            },
        ),
        ("GET", "/sessions/session-123", None),
        ("POST", "/sessions/session-123/cancel", None),
        ("GET", "/sessions/session-123/alerts", None),
        (
            "POST",
            "/playback/resolve",
            {
                "mode": "video_files",
                "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
                "current_item": None,
            },
        ),
    ],
)
def test_prepare_cli_runtime_share_mode_requires_auth_for_operational_routes(
    monkeypatch,
    method: str,
    path: str,
    payload: dict[str, object] | None,
) -> None:
    """Operational routes should reject unauthenticated share-mode calls."""

    prepare_runtime_with_empty_alert_routes(monkeypatch, mode="share")

    response = request(method, path, json=payload)

    assert response.status_code == 401
    assert response.json() == build_authentication_failed_payload("Missing API key")


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/sessions", "post"),
        ("/sessions/{session_id}", "get"),
        ("/sessions/{session_id}/cancel", "post"),
        ("/sessions/{session_id}/alerts", "get"),
        ("/playback/resolve", "post"),
    ],
)
def test_operational_routes_advertise_authentication_failures(
    path: str,
    method: str,
) -> None:
    """Protected route families should publish the shared `401` contract."""

    responses = app.openapi()["paths"][path][method]["responses"]

    assert responses["401"]["description"] == "Authentication failed"
    schema_ref = responses["401"]["content"]["application/json"]["schema"]["$ref"]
    assert schema_ref.endswith("/ApiAuthenticationErrorResponse")


@pytest.mark.parametrize(
    ("method", "path", "payload", "expected_status"),
    [
        ("GET", "/sessions/session-123", None, 404),
        ("GET", "/sessions/session-123/alerts", None, 200),
        (
            "POST",
            "/playback/resolve",
            {
                "mode": "video_files",
                "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
                "current_item": None,
            },
            200,
        ),
    ],
)
def test_prepare_cli_runtime_protected_route_families_allow_local_and_valid_share_calls(
    monkeypatch,
    method: str,
    path: str,
    payload: dict[str, object] | None,
    expected_status: int,
) -> None:
    """Local and authenticated share calls should pass router-level auth."""

    prepare_runtime_with_empty_alert_routes(monkeypatch, mode="local")
    local_response = request(method, path, json=payload)

    reset_boundary_test_state()
    runtime = prepare_runtime_with_empty_alert_routes(monkeypatch, mode="share")
    share_response = request(
        method,
        path,
        json=payload,
        headers=build_runtime_headers(runtime),
    )

    assert local_response.status_code == expected_status
    assert share_response.status_code == expected_status


def test_prepare_cli_runtime_share_mode_keeps_public_routes_open(
    monkeypatch,
) -> None:
    """Share mode should keep the minimal health and docs surfaces public."""

    prepare_runtime_with_empty_alert_routes(
        monkeypatch,
        mode="share",
        manual_api_key=None,
    )

    _assert_public_routes_remain_open()


def test_prepare_cli_runtime_share_mode_keeps_openapi_schema_public(
    monkeypatch,
) -> None:
    """CLI-prepared share mode should leave the machine-readable API schema public.

    This protects the developer-facing schema surface that powers `/docs` and
    other contract inspection tooling.
    """

    prepare_runtime_with_empty_alert_routes(
        monkeypatch,
        mode="share",
        manual_api_key=None,
    )

    response = _assert_public_get_route_is_open("/openapi.json")
    openapi_document = cast(dict[str, object], response.json())
    paths = cast(dict[str, object], openapi_document["paths"])

    assert "/sessions/{session_id}/alerts" in paths


def test_prepare_cli_runtime_share_mode_keeps_detectors_route_open(
    monkeypatch,
) -> None:
    """Share mode should preserve detector discovery until its policy is decided.

    `GET /detectors` remains intentionally outside this task's operational
    authentication scope. A later policy decision may classify it differently.
    """

    prepare_runtime_with_empty_alert_routes(
        monkeypatch,
        mode="share",
        manual_api_key=None,
    )

    detectors = _assert_public_get_route_is_open("/detectors").json()

    assert isinstance(detectors, list)


def test_prepare_cli_runtime_local_mode_keeps_real_alert_route_open_without_key(
    monkeypatch,
) -> None:
    """Local mode should preserve the trusted no-key route behavior on the real alerts router."""

    prepare_runtime_with_empty_alert_routes(monkeypatch, mode="local")

    response = request("GET", "/sessions/session-123/alerts")

    assert response.status_code == 200
    assert response.json() == EMPTY_ALERTS_RESPONSE


def test_prepare_cli_runtime_invalid_share_key_does_not_spend_valid_caller_budget(
    monkeypatch,
) -> None:
    """Auth failures in share mode should short-circuit before the limiter budget."""

    install_one_request_rate_limit_env(monkeypatch)
    runtime = prepare_runtime_with_empty_alert_routes(monkeypatch, mode="share")
    valid_headers = build_runtime_headers(runtime)

    invalid_response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers={"X-API-Key": "wrong-share-key"},
    )
    first_valid_response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=valid_headers,
    )
    second_valid_response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=valid_headers,
    )

    assert invalid_response.status_code == 401
    assert first_valid_response.status_code == 200
    assert second_valid_response.status_code == 429


@pytest.mark.parametrize(
    ("manual_api_key", "path"),
    [
        (None, "/sessions/session-123/alerts"),
        ("manual-demo-key", "/sessions/session-123/alerts"),
        (None, "/sessions/session-123/alerts/incident-summary"),
    ],
)
def test_prepare_cli_runtime_share_mode_rate_limits_protected_routes(
    monkeypatch,
    manual_api_key: str | None,
    path: str,
) -> None:
    """Protected alerts routes should share one real CLI-prepared limiter policy.

    The parametrized paths here intentionally prove that one CLI-prepared share
    runtime applies the same router-scoped budget to both raw and grouped
    alerts routes.
    """

    install_one_request_rate_limit_env(monkeypatch)
    runtime = prepare_runtime_with_empty_alert_routes(
        monkeypatch,
        mode="share",
        manual_api_key=manual_api_key,
    )
    headers = build_runtime_headers(runtime, fallback_key=manual_api_key)

    first_response = request("GET", path, headers=headers)
    second_response = request("GET", path, headers=headers)

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.json() == build_rate_limit_exceeded_payload(
        "Too many requests for the configured window."
    )


def test_prepare_cli_runtime_local_mode_enabled_rate_limit_uses_real_local_fallback_budget(
    monkeypatch,
) -> None:
    """Local mode should still allow explicit limiter enablement through the real route."""

    monkeypatch.setenv("ESM_API_RATE_LIMIT_ENABLED", "true")
    install_one_request_rate_limit_env(monkeypatch)
    prepare_runtime_with_empty_alert_routes(monkeypatch, mode="local")

    first_response = request("GET", "/sessions/session-123/alerts")
    second_response = request("GET", "/sessions/session-123/alerts")

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.json() == build_rate_limit_exceeded_payload(
        "Too many requests for the configured window."
    )


def test_prepare_cli_runtime_share_mode_disabled_rate_limit_keeps_real_routes_open(
    monkeypatch,
) -> None:
    """Disabling the limiter explicitly should remove the real 429 path in share mode."""

    monkeypatch.setenv("ESM_API_RATE_LIMIT_ENABLED", "false")
    runtime = prepare_runtime_with_empty_alert_routes(monkeypatch, mode="share")
    headers = build_runtime_headers(runtime)

    first_response = request("GET", "/sessions/session-123/alerts", headers=headers)
    second_response = request("GET", "/sessions/session-123/alerts", headers=headers)

    assert first_response.status_code == 200
    assert second_response.status_code == 200


def test_prepare_cli_runtime_strips_manual_share_key_whitespace(monkeypatch) -> None:
    """Manual share-mode keys should be normalized for copy/paste-friendly CLI usage."""

    runtime = prepare_runtime_with_empty_alert_routes(
        monkeypatch,
        mode="share",
        manual_api_key="  manual-demo-key  ",
    )

    assert runtime.auth_settings.allowed_api_keys == ("manual-demo-key",)
    response = request(
        "GET",
        "/sessions/session-123/alerts",
        headers=build_runtime_headers(runtime, fallback_key="manual-demo-key"),
    )

    assert response.status_code == 200
