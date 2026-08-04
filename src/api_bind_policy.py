"""Deterministic bind-host classification for FastAPI startup policy.

The CLI admits loopback binds in local mode and requires share mode for other
valid hosts. Hostnames are checked syntactically, never resolved through DNS.
"""

from __future__ import annotations

import ipaddress
import re
from enum import StrEnum


class BindHostClass(StrEnum):
    """Bind categories used to admit local or share-mode startup."""

    LOOPBACK = "loopback"
    WILDCARD = "wildcard"
    NON_LOOPBACK = "non_loopback"
    INVALID = "invalid"


_HOSTNAME_LABEL_PATTERN = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
)
_MAX_HOSTNAME_LENGTH = 253


def classify_bind_host(host: str) -> BindHostClass:
    """Classify one bind host without network-dependent DNS resolution.

    Only literal loopback addresses and exact `localhost` are local-safe.
    Other valid hostnames are non-loopback, regardless of local resolver state.
    """

    if not host or host != host.strip():
        return BindHostClass.INVALID
    if host == "localhost":
        return BindHostClass.LOOPBACK

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return (
            BindHostClass.NON_LOOPBACK
            if _is_valid_hostname(host)
            else BindHostClass.INVALID
        )

    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return BindHostClass.NON_LOOPBACK
    if address.is_unspecified:
        return BindHostClass.WILDCARD
    if address.is_loopback:
        return BindHostClass.LOOPBACK
    return BindHostClass.NON_LOOPBACK


def _is_valid_hostname(host: str) -> bool:
    """Return whether a non-IP host matches the accepted ASCII syntax."""

    if len(host) > _MAX_HOSTNAME_LENGTH:
        return False
    hostname = host.removesuffix(".")
    if not hostname:
        return False
    return all(
        _HOSTNAME_LABEL_PATTERN.fullmatch(label) is not None
        for label in hostname.split(".")
    )
