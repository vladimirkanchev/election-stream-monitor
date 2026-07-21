"""Focused tests for deterministic FastAPI bind-host classification."""

from __future__ import annotations

import pytest

from api_bind_policy import BindHostClass, classify_bind_host


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", BindHostClass.LOOPBACK),
        ("127.255.255.255", BindHostClass.LOOPBACK),
        ("::1", BindHostClass.LOOPBACK),
        ("localhost", BindHostClass.LOOPBACK),
        ("0.0.0.0", BindHostClass.WILDCARD),
        ("::", BindHostClass.WILDCARD),
        ("192.168.1.20", BindHostClass.NON_LOOPBACK),
        ("203.0.113.10", BindHostClass.NON_LOOPBACK),
        ("2001:db8::10", BindHostClass.NON_LOOPBACK),
        ("::ffff:127.0.0.1", BindHostClass.NON_LOOPBACK),
        ("demo.example.test", BindHostClass.NON_LOOPBACK),
        ("demo.example.test.", BindHostClass.NON_LOOPBACK),
    ],
)
def test_classify_bind_host_distinguishes_supported_bind_categories(
    host: str,
    expected: BindHostClass,
) -> None:
    """The policy should classify addresses without consulting DNS."""

    assert classify_bind_host(host) is expected


@pytest.mark.parametrize("host", ["localhost.", "LOCALHOST"])
def test_classify_bind_host_keeps_noncanonical_localhost_out_of_loopback(
    host: str,
) -> None:
    """Only exact `localhost` may receive the local-safe hostname classification."""

    assert classify_bind_host(host) is BindHostClass.NON_LOOPBACK


@pytest.mark.parametrize(
    "host",
    [
        "",
        " 127.0.0.1",
        "127.0.0.1 ",
        "[::1]",
        "127.0.0.1:8000",
        "bad host",
        "demo..example.test",
        "-demo.example.test",
        "demo-.example.test",
        "a" * 254,
    ],
)
def test_classify_bind_host_rejects_ambiguous_or_malformed_values(host: str) -> None:
    """Ambiguous host spellings must not inherit the local-safe classification."""

    assert classify_bind_host(host) is BindHostClass.INVALID
