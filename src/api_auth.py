"""FastAPI authentication boundary helpers.

This module keeps the FastAPI auth seam small and transport-focused. The route
layer can call into it to validate request credentials and obtain a small
authenticated principal object while keeping shared business logic completely
auth-agnostic.

The current implementation supports API-key validation and intentionally leaves
room for a later JWT-backed principal path without forcing the route layer to
change signatures. Protected route families share this seam while retaining
their own authorization and resource-control policies.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Literal

from api_boundary_config import ApiAuthSettings, get_api_auth_settings

API_KEY_HEADER_NAME = "X-API-Key"
API_KEY_FINGERPRINT_LENGTH = 12
AuthType = Literal["local", "api_key", "jwt"]
AuthenticationFailureReason = Literal[
    "missing_api_key",
    "invalid_api_key",
    "auth_configuration_invalid",
    "unsupported_auth_mode",
    "authentication_failed",
]


@dataclass(frozen=True)
class AuthPrincipal:
    """Authenticated caller identity returned by the API auth boundary.

    The object is intentionally auth-mechanism-neutral. FastAPI route policy,
    rate limiting, and any later remote-MCP boundary can reason about the
    caller through this shape without depending on raw API keys or a future
    JWT claim layout.
    """

    auth_type: AuthType
    subject: str
    key_id: str | None = None


class AuthenticationError(Exception):
    """Raised when request credentials are missing, invalid, or unsupported.

    The FastAPI boundary maps this plain auth-seam error into the stable HTTP
    `401` contract. Keeping the error transport-agnostic here avoids coupling
    the underlying credential checks to FastAPI-specific response mechanics.
    """

    def __init__(
        self,
        detail: str,
        *,
        reason_code: AuthenticationFailureReason = "authentication_failed",
    ) -> None:
        """Keep client detail separate from the fixed diagnostic reason code."""

        super().__init__(detail)
        self.reason_code = reason_code


def authenticate_api_request(
    *,
    x_api_key: str | None,
    settings: ApiAuthSettings | None = None,
) -> AuthPrincipal:
    """Authenticate one HTTP request using the configured FastAPI auth mode.

    The route boundary should depend on this function rather than reimplement
    credential checks. Today it supports API-key validation; later JWT support
    can plug into the same seam without changing route signatures.
    """
    active_settings = settings or get_api_auth_settings()
    if not active_settings.enabled:
        return _build_local_principal()
    return _authenticate_enabled_request(
        x_api_key=x_api_key,
        settings=active_settings,
    )


def _authenticate_api_key(
    *,
    x_api_key: str | None,
    settings: ApiAuthSettings,
) -> AuthPrincipal:
    """Validate one presented API key against configured allowed keys.

    This keeps the API-key-specific branch separate from the outer auth-mode
    dispatch so a later JWT path can plug into the same public seam without
    rewriting the request-authentication entrypoint.
    """
    presented_key = _normalize_presented_api_key(x_api_key)
    if presented_key is None:
        raise AuthenticationError("Missing API key", reason_code="missing_api_key")
    if not settings.allowed_api_keys:
        raise AuthenticationError(
            "API key authentication is enabled but no allowed API keys are configured",
            reason_code="auth_configuration_invalid",
        )

    for configured_key in settings.allowed_api_keys:
        if hmac.compare_digest(presented_key, configured_key):
            return _build_api_key_principal(configured_key)

    raise AuthenticationError("Invalid API key", reason_code="invalid_api_key")


def _authenticate_enabled_request(
    *,
    x_api_key: str | None,
    settings: ApiAuthSettings,
) -> AuthPrincipal:
    """Authenticate one request after auth has been enabled in settings.

    Keeping the mode switch here makes the outer boundary read cleanly today
    while giving later JWT support one obvious place to plug in.
    """
    if settings.mode == "api_key":
        return _authenticate_api_key(
            x_api_key=x_api_key,
            settings=settings,
        )
    raise AuthenticationError(
        "Unsupported API authentication mode",
        reason_code="unsupported_auth_mode",
    )


def _build_local_principal() -> AuthPrincipal:
    """Return a local trusted principal when HTTP auth is disabled.

    Local development and single-user desktop runs still move through the same
    principal-shaped seam so downstream boundary code does not need a second
    no-auth path.
    """
    return AuthPrincipal(
        auth_type="local",
        subject="local-api-client",
        key_id=None,
    )


def _build_api_key_principal(configured_key: str) -> AuthPrincipal:
    """Build one stable principal from a validated configured API key.

    The key fingerprint is only for local identity and rate-limiting use. It
    avoids exposing the raw configured API key to downstream code.
    """
    key_fingerprint = hashlib.sha256(configured_key.encode("utf-8")).hexdigest()[
        :API_KEY_FINGERPRINT_LENGTH
    ]
    return AuthPrincipal(
        auth_type="api_key",
        subject=f"api-key:{key_fingerprint}",
        key_id=key_fingerprint,
    )


def _normalize_presented_api_key(x_api_key: str | None) -> str | None:
    """Normalize one presented API key before validation.

    Blank or whitespace-only header values are treated as missing credentials.
    The configured allowed keys remain unchanged; only the presented header
    value is normalized at the transport boundary before comparison.
    """
    if x_api_key is None:
        return None
    normalized = x_api_key.strip()
    if not normalized:
        return None
    return normalized
