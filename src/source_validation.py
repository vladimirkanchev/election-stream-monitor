"""Central trust-boundary validation for local and remote monitoring sources.

These helpers intentionally sit close to the backend entrypoints so source
validation stays consistent across the CLI, session runner, and playback
resolution. The goal is to reject unsupported or risky inputs early, before
they reach detector execution or future remote-stream fetching logic.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from urllib.parse import urlparse

import config
from analyzer_contract import InputMode
from path_utils import resolve_app_input_path

API_STREAM_DIRECT_MEDIA_SUFFIXES = (".m3u8", ".mp4")


class InvalidSourceInputError(ValueError):
    """Raised when a source path or URL violates the allowed input contract."""


def normalize_source_input(value: str | Path) -> str:
    """Return one trimmed source string shared by all validation entrypoints."""
    return str(value).strip()


def validate_source_input(mode: InputMode, input_path: str | Path) -> str:
    """Validate one source value for the selected mode and return its normalized form.

    Local modes only accept filesystem-style inputs. `api_stream` delegates to
    URL validation with the stricter remote trust policy.
    """
    normalized = normalize_source_input(input_path)
    if not normalized:
        raise InvalidSourceInputError("Source input cannot be blank.")

    if mode == "api_stream":
        return validate_api_stream_url(normalized)

    if _looks_like_url(normalized):
        raise InvalidSourceInputError(
            f"Unsupported local input scheme for {mode}: {normalized}"
        )

    resolved = resolve_app_input_path(normalized)
    if not resolved.exists():
        raise OSError(f"Input path does not exist: {resolved}")
    return normalized


def validate_api_stream_url(url: str | Path) -> str:
    """Validate one future `api_stream` URL against the current trust policy.

    The current policy is intentionally conservative:

    - only explicitly allowed schemes are accepted
    - embedded credentials are rejected
    - optional host allowlists can narrow accepted domains
    - obvious local-network targets are rejected by default in local mode
    """
    normalized = normalize_source_input(url)
    if not normalized:
        raise InvalidSourceInputError("Source input cannot be blank.")
    parsed = urlparse(normalized)
    if parsed.scheme not in config.API_STREAM_ALLOWED_SCHEMES:
        raise InvalidSourceInputError(
            f"Unsupported api_stream URL scheme: {parsed.scheme or '<missing>'}"
        )
    if not parsed.netloc or not parsed.hostname:
        raise InvalidSourceInputError("api_stream URL must include a host.")
    if parsed.username or parsed.password:
        raise InvalidSourceInputError("api_stream URLs must not include credentials.")
    _validate_api_stream_host(parsed.hostname)
    if not _has_supported_direct_media_suffix(parsed.path):
        raise InvalidSourceInputError(
            "api_stream requires a direct .m3u8 or .mp4 URL, not a webpage URL."
        )
    return normalized


def resolve_validated_local_input_path(mode: InputMode, input_path: str | Path) -> Path:
    """Validate and resolve one local input path under the app's path rules."""
    normalized = validate_source_input(mode, input_path)
    return resolve_app_input_path(normalized)


def validate_local_media_size(file_path: Path) -> None:
    """Enforce the current local media size boundary before analysis starts."""
    if not file_path.exists():
        raise OSError(f"Input path does not exist: {file_path}")
    if file_path.stat().st_size > config.LOCAL_MEDIA_MAX_BYTES:
        raise InvalidSourceInputError(
            f"Local media file exceeds size limit: {file_path.name}"
        )


def ensure_path_within_root(root: Path, candidate: Path) -> Path | None:
    """Resolve one candidate path only when it remains under the supplied root.

    This helper is used to prevent traversal-style references from escaping the
    declared local input directory during playback or playlist resolution.
    """
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError:
        return None
    return resolved_candidate


def _looks_like_url(value: str) -> bool:
    """Return whether a string should be treated as URL-like rather than local."""
    parsed = urlparse(value)
    return bool(
        parsed.scheme
        and (
            "://" in value
            or parsed.scheme.lower() in {"data", "blob", "javascript", "file"}
        )
    )


def _validate_api_stream_host(hostname: str) -> None:
    """Apply host-level `api_stream` restrictions without performing network I/O."""
    normalized_host = hostname.strip().lower()
    if not normalized_host:
        raise InvalidSourceInputError("api_stream URL must include a host.")

    policy = _get_api_stream_host_policy()

    if policy["require_allowlist"] and not policy["allowed_hosts"]:
        raise InvalidSourceInputError(
            "api_stream service mode requires an explicit allowed host list."
        )

    if not policy["allow_private_hosts"] and _is_local_network_target(
        normalized_host
    ):
        raise InvalidSourceInputError(
            f"api_stream host is not allowed in {policy['mode']} mode: {normalized_host}"
        )

    if policy["allowed_hosts"] and not _host_matches_allowlist(
        normalized_host,
        policy["allowed_hosts"],
    ):
        raise InvalidSourceInputError(
            f"api_stream host is not in the allowed host list: {normalized_host}"
        )


def _get_api_stream_host_policy() -> dict[str, object]:
    """Return the current trust policy for remote api_stream host validation."""
    trust_mode = str(getattr(config, "API_STREAM_TRUST_MODE", "local")).strip().lower()
    if trust_mode == "service":
        return {
            "mode": "service",
            "allowed_hosts": tuple(getattr(config, "API_STREAM_SERVICE_ALLOWED_HOSTS", ()) or ()),
            "allow_private_hosts": bool(
                getattr(config, "API_STREAM_SERVICE_ALLOW_PRIVATE_HOSTS", False)
            ),
            "require_allowlist": True,
        }

    return {
        "mode": "local",
        "allowed_hosts": tuple(getattr(config, "API_STREAM_ALLOWED_HOSTS", ()) or ()),
        "allow_private_hosts": bool(getattr(config, "API_STREAM_ALLOW_PRIVATE_HOSTS", False)),
        "require_allowlist": False,
    }


def _has_supported_direct_media_suffix(path: str) -> bool:
    """Return whether a remote path matches the current direct-media contract."""
    normalized_path = path.strip().lower()
    return normalized_path.endswith(API_STREAM_DIRECT_MEDIA_SUFFIXES)


def _host_matches_allowlist(hostname: str, allowed_hosts: tuple[str, ...]) -> bool:
    """Return whether a host matches one configured exact or suffix allowlist entry."""
    normalized_allowed_hosts = [host.strip().lower() for host in allowed_hosts if host.strip()]
    for allowed_host in normalized_allowed_hosts:
        if hostname == allowed_host or hostname.endswith(f".{allowed_host}"):
            return True
    return False


def _is_local_network_target(hostname: str) -> bool:
    """Return whether a host is an obvious loopback or private-network target."""
    if hostname in {"localhost", "localhost.localdomain"}:
        return True

    try:
        parsed_ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False

    return any(
        (
            parsed_ip.is_private,
            parsed_ip.is_loopback,
            parsed_ip.is_link_local,
            parsed_ip.is_multicast,
            parsed_ip.is_reserved,
            parsed_ip.is_unspecified,
        )
    )
