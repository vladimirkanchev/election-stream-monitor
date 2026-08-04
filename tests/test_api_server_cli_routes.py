"""HTTP-boundary tests for local and share-mode route policy.

These cases cover authentication, alert limiting, intentional public routes,
and local-only framework documentation. CLI setup and output are tested
separately.
"""

from __future__ import annotations

import logging
from collections.abc import Generator

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
    EMPTY_ALERT_SUMMARY_RESPONSE,
    EMPTY_ALERTS_RESPONSE,
    build_runtime_headers,
    install_one_request_rate_limit_env,
    prepare_runtime_with_empty_alert_routes,
)

_SHARE_PUBLIC_OPERATIONS = frozenset(
    {
        ("GET", "/health"),
        ("GET", "/detectors"),
    }
)
_HTTP_OPERATION_METHODS = frozenset(
    {"delete", "get", "head", "options", "patch", "post", "put"}
)

_SHARE_PROTECTED_REQUESTS = (
    (
        "POST",
        "/sessions",
        "/sessions",
        {
            "mode": "video_files",
            "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
            "selected_detectors": [],
        },
    ),
    ("GET", "/sessions/{session_id}", "/sessions/session-123", None),
    (
        "POST",
        "/sessions/{session_id}/cancel",
        "/sessions/session-123/cancel",
        None,
    ),
    (
        "GET",
        "/sessions/{session_id}/alerts",
        "/sessions/session-123/alerts",
        None,
    ),
    (
        "GET",
        "/sessions/{session_id}/alerts/summary",
        "/sessions/session-123/alerts/summary",
        None,
    ),
    (
        "GET",
        "/sessions/{session_id}/alerts/timeline",
        "/sessions/session-123/alerts/timeline",
        None,
    ),
    (
        "GET",
        "/sessions/{session_id}/alerts/incident-summary",
        "/sessions/session-123/alerts/incident-summary",
        None,
    ),
    (
        "POST",
        "/playback/resolve",
        "/playback/resolve",
        {
            "mode": "video_files",
            "input_path": "tests/fixtures/media/video_files/black_trigger.mp4",
            "current_item": None,
        },
    ),
)

_AUTH_TRANSITION_ROUTE_CASES = (
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
)


def _mounted_application_operations() -> set[tuple[str, str]]:
    """Return documented application operations covered by the share-mode policy.

    OpenAPI is the stable public FastAPI inventory. It avoids depending on the
    mutable Starlette route container shared by in-process boundary tests.
    Framework documentation endpoints remain middleware-controlled and have
    separate local/share tests below.
    """

    return {
        (method.upper(), path)
        for path, path_item in app.openapi()["paths"].items()
        for method in path_item
        if method in _HTTP_OPERATION_METHODS
    }


@pytest.fixture(autouse=True)
def _clear_boundary_settings_caches() -> Generator[None, None, None]:
    """Keep env-driven FastAPI boundary settings isolated across CLI route tests."""

    original_values = snapshot_boundary_env()
    reset_boundary_test_state()
    yield
    restore_boundary_test_state(original_values)


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


def test_mounted_application_operations_have_explicit_security_classes() -> None:
    """Every live application route should be share-public or share-protected.

    The share-mode request cases below must cover every protected operation;
    adding an unclassified operation makes this test fail.
    """

    protected_operations = {
        (method, operation_path)
        for method, operation_path, _, _ in _SHARE_PROTECTED_REQUESTS
    }

    assert _mounted_application_operations() == (
        _SHARE_PUBLIC_OPERATIONS | protected_operations
    )
    assert _SHARE_PUBLIC_OPERATIONS.isdisjoint(protected_operations)


@pytest.mark.parametrize(
    ("method", "_operation_path", "path", "payload"),
    _SHARE_PROTECTED_REQUESTS,
)
def test_prepare_cli_runtime_share_mode_requires_auth_for_operational_routes(
    monkeypatch,
    method: str,
    _operation_path: str,
    path: str,
    payload: dict[str, object] | None,
) -> None:
    """Operational routes should reject unauthenticated share-mode calls."""

    prepare_runtime_with_empty_alert_routes(monkeypatch, mode="share")

    response = request(method, path, json=payload)

    assert response.status_code == 401
    assert response.json() == build_authentication_failed_payload("Missing API key")


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "POST",
            "/sessions",
            {"mode": "video_files", "input_path": "clip.mp4", "selected_detectors": []},
        ),
        ("GET", "/sessions/session-123", None),
        ("POST", "/sessions/session-123/cancel", None),
        ("GET", "/sessions/session-123/alerts", None),
        (
            "POST",
            "/playback/resolve",
            {"mode": "video_files", "input_path": "clip.mp4", "current_item": None},
        ),
    ],
)
def test_operational_route_auth_logs_use_only_safe_failure_context(
    monkeypatch,
    caplog,
    method: str,
    path: str,
    payload: dict[str, object] | None,
) -> None:
    """Every protected router should log a fixed code, never a request key."""

    prepare_runtime_with_empty_alert_routes(monkeypatch, mode="share")
    presented_key = "untrusted-operational-key"

    with caplog.at_level(logging.WARNING, logger="api.http_auth_policy"):
        response = request(
            method,
            path,
            json=payload,
            headers={"X-API-Key": presented_key},
        )

    assert response.status_code == 401
    assert f"path={path}" in caplog.text
    assert "reason_code=invalid_api_key" in caplog.text
    assert presented_key not in caplog.text


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
    _AUTH_TRANSITION_ROUTE_CASES,
)
def test_prepare_cli_runtime_protected_route_families_apply_auth_transitions(
    monkeypatch,
    method: str,
    path: str,
    payload: dict[str, object] | None,
    expected_status: int,
) -> None:
    """Session, alert, and playback families should share the access contract."""

    prepare_runtime_with_empty_alert_routes(monkeypatch, mode="local")
    local_response = request(method, path, json=payload)

    reset_boundary_test_state()
    runtime = prepare_runtime_with_empty_alert_routes(monkeypatch, mode="share")
    missing_response = request(method, path, json=payload)
    blank_response = request(
        method,
        path,
        json=payload,
        headers={"X-API-Key": "   "},
    )
    invalid_response = request(
        method,
        path,
        json=payload,
        headers={"X-API-Key": "wrong-share-key"},
    )
    valid_response = request(
        method,
        path,
        json=payload,
        headers=build_runtime_headers(runtime),
    )

    assert local_response.status_code == expected_status
    assert missing_response.status_code == 401
    assert missing_response.json() == build_authentication_failed_payload(
        "Missing API key"
    )
    assert blank_response.status_code == 401
    assert blank_response.json() == build_authentication_failed_payload(
        "Missing API key"
    )
    assert invalid_response.status_code == 401
    assert invalid_response.json() == build_authentication_failed_payload(
        "Invalid API key"
    )
    assert valid_response.status_code == expected_status


def test_prepare_cli_runtime_share_mode_keeps_health_route_open(
    monkeypatch,
) -> None:
    """Share mode should retain only the minimal public health response."""

    prepare_runtime_with_empty_alert_routes(
        monkeypatch,
        mode="share",
        manual_api_key=None,
    )

    response = request("GET", "/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "path",
    ["/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"],
)
def test_prepare_cli_runtime_share_mode_hides_framework_documentation(
    monkeypatch,
    path: str,
) -> None:
    """Share mode should not expose framework route-discovery endpoints."""

    prepare_runtime_with_empty_alert_routes(
        monkeypatch,
        mode="share",
        manual_api_key=None,
    )

    response = request("GET", path)

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


@pytest.mark.parametrize("path", ["/openapi.json", "/docs", "/redoc"])
def test_prepare_cli_runtime_local_mode_keeps_framework_documentation_available(
    monkeypatch,
    path: str,
) -> None:
    """Local mode should preserve FastAPI documentation for trusted development."""

    prepare_runtime_with_empty_alert_routes(monkeypatch, mode="local")

    assert request("GET", path).status_code == 200


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

    response = request("GET", "/detectors")

    assert response.status_code == 200
    detectors = response.json()
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
