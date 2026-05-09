"""Focused unit tests for the FastAPI authentication seam.

These tests intentionally stay below the route layer. They protect the shared
auth decision logic directly so the alert-route policy can stay thin and
transport-focused.

The file owns:

- disabled-auth local fallback behavior
- API-key success and failure cases
- lightweight guards around unsupported or misconfigured auth modes

Route-level `401` mapping and protected-scope behavior live in the alert-route
adapter tests.
"""

import hashlib

import pytest

from config import ApiAuthSettings
from api_auth import AuthenticationError, authenticate_api_request


def test_authenticate_api_request_returns_local_principal_when_disabled() -> None:
    """Disabled FastAPI auth should yield one deterministic local principal."""
    principal = authenticate_api_request(
        x_api_key=None,
        settings=ApiAuthSettings(
            enabled=False,
            mode="api_key",
            allowed_api_keys=(),
        ),
    )

    assert principal.auth_type == "local"
    assert principal.subject == "local-api-client"
    assert principal.key_id is None


def test_authenticate_api_request_returns_fingerprinted_principal_for_valid_key() -> None:
    """Validated keys should become fingerprint-based principals, not raw secrets."""
    fingerprint = hashlib.sha256("alpha-secret".encode("utf-8")).hexdigest()[:12]
    principal = authenticate_api_request(
        x_api_key="alpha-secret",
        settings=ApiAuthSettings(
            enabled=True,
            mode="api_key",
            allowed_api_keys=("alpha-secret",),
        ),
    )

    assert principal.auth_type == "api_key"
    assert principal.subject == f"api-key:{fingerprint}"
    assert principal.key_id == fingerprint


def test_authenticate_api_request_accepts_generated_share_mode_key() -> None:
    """Generated share-mode keys should behave like ordinary configured API keys."""
    fingerprint = hashlib.sha256("esm_share_demo-secret".encode("utf-8")).hexdigest()[:12]
    principal = authenticate_api_request(
        x_api_key="esm_share_demo-secret",
        settings=ApiAuthSettings(
            enabled=True,
            mode="api_key",
            allowed_api_keys=("esm_share_demo-secret",),
            generated_api_key="esm_share_demo-secret",
        ),
    )

    assert principal.auth_type == "api_key"
    assert principal.subject == f"api-key:{fingerprint}"
    assert principal.key_id == fingerprint


def test_authenticate_api_request_rejects_missing_api_key() -> None:
    """Enabled API-key mode should reject a missing credential."""
    with pytest.raises(AuthenticationError, match="Missing API key"):
        authenticate_api_request(
            x_api_key=None,
            settings=ApiAuthSettings(
                enabled=True,
                mode="api_key",
                allowed_api_keys=("alpha-secret",),
            ),
        )


def test_authenticate_api_request_treats_blank_api_key_as_missing() -> None:
    """Whitespace-only header values should not count as valid credentials."""
    with pytest.raises(AuthenticationError, match="Missing API key"):
        authenticate_api_request(
            x_api_key="   ",
            settings=ApiAuthSettings(
                enabled=True,
                mode="api_key",
                allowed_api_keys=("alpha-secret",),
            ),
        )


def test_authenticate_api_request_rejects_invalid_api_key() -> None:
    """Unknown keys should fail cleanly without producing a principal."""
    with pytest.raises(AuthenticationError, match="Invalid API key"):
        authenticate_api_request(
            x_api_key="wrong-secret",
            settings=ApiAuthSettings(
                enabled=True,
                mode="api_key",
                allowed_api_keys=("alpha-secret",),
            ),
        )


def test_authenticate_api_request_rejects_enabled_mode_without_keys() -> None:
    """Enabled API-key auth should fail fast on empty allowed-key configuration."""
    with pytest.raises(
        AuthenticationError,
        match="API key authentication is enabled but no allowed API keys are configured",
    ):
        authenticate_api_request(
            x_api_key="alpha-secret",
            settings=ApiAuthSettings(
                enabled=True,
                mode="api_key",
                allowed_api_keys=(),
            ),
        )


def test_authenticate_api_request_rejects_unsupported_mode() -> None:
    """The shared auth seam should reject modes that are not implemented yet."""
    with pytest.raises(AuthenticationError, match="Unsupported API authentication mode"):
        authenticate_api_request(
            x_api_key="alpha-secret",
            settings=ApiAuthSettings(
                enabled=True,
                mode="jwt",
                allowed_api_keys=("alpha-secret",),
            ),
        )
