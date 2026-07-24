"""Focused unit tests for the FastAPI rate-limiting seam.

These tests stay below the route layer and protect the fixed-window limiter in
isolation. They keep the counting policy readable on its own before the alert
router composes it with authentication and HTTP error mapping.

The file owns:

- enabled versus disabled limiter behavior
- principal and IP subject strategies
- exact-limit and over-limit behavior
- window reset semantics
- independent named route-family budgets
- injected backend seam behavior
- defensive behavior for unsupported limiter strategies
- injected backend short-circuit and propagation behavior
"""

from dataclasses import dataclass, field
from threading import Barrier, Lock, Thread
from typing import cast

import pytest

from api_auth import AuthPrincipal
from api_rate_limit import (
    InMemoryFixedWindowRateLimiter,
    RateLimitError,
    RateLimiterBackend,
    enforce_api_rate_limit,
    reset_api_rate_limit_state,
)
from config import ApiRateLimitSettings, ApiRateLimitStrategy


@pytest.fixture(autouse=True)
def _reset_api_rate_limit_state() -> None:
    """Keep the shared in-memory limiter state isolated between test cases."""
    reset_api_rate_limit_state()
    yield
    reset_api_rate_limit_state()


# Fixed-window behavior with the default principal strategy


def test_enforce_api_rate_limit_skips_when_disabled() -> None:
    """Disabled rate limiting should allow requests without touching counters."""
    enforce_api_rate_limit(
        principal=_build_principal("alpha"),
        settings=ApiRateLimitSettings(
            enabled=False,
            strategy="principal",
            window_seconds=60,
            max_requests=1,
        ),
    )


def test_enforce_api_rate_limit_allows_requests_until_limit_then_rejects() -> None:
    """The fixed window should allow requests through the exact budget and reject the next one."""
    settings = ApiRateLimitSettings(
        enabled=True,
        strategy="principal",
        window_seconds=60,
        max_requests=2,
    )

    enforce_api_rate_limit(
        principal=_build_principal("alpha"),
        settings=settings,
        now_monotonic=100.0,
    )
    enforce_api_rate_limit(
        principal=_build_principal("alpha"),
        settings=settings,
        now_monotonic=101.0,
    )

    with pytest.raises(RateLimitError, match="Too many requests for the configured window"):
        enforce_api_rate_limit(
            principal=_build_principal("alpha"),
            settings=settings,
            now_monotonic=102.0,
        )


def test_enforce_api_rate_limit_keeps_distinct_principals_separate() -> None:
    """Distinct authenticated callers should not share one principal budget."""
    settings = ApiRateLimitSettings(
        enabled=True,
        strategy="principal",
        window_seconds=60,
        max_requests=1,
    )

    enforce_api_rate_limit(
        principal=_build_principal("alpha"),
        settings=settings,
        now_monotonic=100.0,
    )
    enforce_api_rate_limit(
        principal=_build_principal("beta"),
        settings=settings,
        now_monotonic=100.0,
    )

    with pytest.raises(RateLimitError, match="Too many requests for the configured window"):
        enforce_api_rate_limit(
            principal=_build_principal("alpha"),
            settings=settings,
            now_monotonic=101.0,
        )


def test_enforce_api_rate_limit_keeps_named_operation_budgets_separate() -> None:
    """One caller should retain independent capacity for each route family."""
    settings = ApiRateLimitSettings(
        enabled=True,
        strategy="principal",
        window_seconds=60,
        max_requests=1,
    )
    principal = _build_principal("alpha")

    enforce_api_rate_limit(
        principal=principal,
        settings=settings,
        budget_name="session-start",
        now_monotonic=100.0,
    )
    enforce_api_rate_limit(
        principal=principal,
        settings=settings,
        budget_name="playback-resolution",
        now_monotonic=100.0,
    )

    with pytest.raises(RateLimitError, match="Too many requests for the configured window"):
        enforce_api_rate_limit(
            principal=principal,
            settings=settings,
            budget_name="session-start",
            now_monotonic=101.0,
        )
    with pytest.raises(RateLimitError, match="Too many requests for the configured window"):
        enforce_api_rate_limit(
            principal=principal,
            settings=settings,
            budget_name="playback-resolution",
            now_monotonic=101.0,
        )


def test_enforce_api_rate_limit_uses_local_fallback_subject_without_key_id() -> None:
    """Local-mode principals should still map to one deterministic limiter subject."""
    settings = ApiRateLimitSettings(
        enabled=True,
        strategy="principal",
        window_seconds=60,
        max_requests=1,
    )

    enforce_api_rate_limit(
        principal=_build_principal(None),
        settings=settings,
        now_monotonic=100.0,
    )

    with pytest.raises(RateLimitError, match="Too many requests for the configured window"):
        enforce_api_rate_limit(
            principal=_build_principal(None),
            settings=settings,
            now_monotonic=101.0,
        )


def test_enforce_api_rate_limit_resets_after_window_expires() -> None:
    """A new fixed window should reopen the budget after the old one expires."""
    settings = ApiRateLimitSettings(
        enabled=True,
        strategy="principal",
        window_seconds=10,
        max_requests=1,
    )

    enforce_api_rate_limit(
        principal=_build_principal("alpha"),
        settings=settings,
        now_monotonic=100.0,
    )

    with pytest.raises(RateLimitError, match="Too many requests for the configured window"):
        enforce_api_rate_limit(
            principal=_build_principal("alpha"),
            settings=settings,
            now_monotonic=105.0,
        )

    enforce_api_rate_limit(
        principal=_build_principal("alpha"),
        settings=settings,
        now_monotonic=110.0,
    )


def test_reset_api_rate_limit_state_reopens_named_operation_budgets() -> None:
    """An explicit in-process reset should clear every route-family counter."""
    settings = ApiRateLimitSettings(
        enabled=True,
        strategy="principal",
        window_seconds=60,
        max_requests=1,
    )
    principal = _build_principal("alpha")

    enforce_api_rate_limit(
        principal=principal,
        settings=settings,
        budget_name="session-control",
        now_monotonic=100.0,
    )
    reset_api_rate_limit_state()

    enforce_api_rate_limit(
        principal=principal,
        settings=settings,
        budget_name="session-control",
        now_monotonic=101.0,
    )


def test_in_memory_rate_limiter_allows_only_one_concurrent_request_for_same_subject() -> None:
    """Concurrent calls for one subject should still respect one shared fixed-window budget.

    This is a small deployment-shape test for the current local backend: the
    in-memory limiter is process-local, but it still needs to behave
    predictably when multiple threads hit the same caller budget at once.
    """

    limiter = InMemoryFixedWindowRateLimiter()
    barrier = Barrier(5)
    results: list[str] = []
    results_lock = Lock()

    def run() -> None:
        barrier.wait()
        try:
            limiter.check_and_increment(
                subject="principal:alpha",
                window_seconds=60,
                max_requests=1,
                now_monotonic=100.0,
            )
        except RateLimitError:
            outcome = "rate_limited"
        else:
            outcome = "allowed"

        with results_lock:
            results.append(outcome)

    threads = [Thread(target=run) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count("allowed") == 1
    assert results.count("rate_limited") == 4


# Alternate subject strategy behavior


def test_enforce_api_rate_limit_supports_ip_strategy() -> None:
    """The alternate IP strategy should bucket callers by request host."""
    settings = ApiRateLimitSettings(
        enabled=True,
        strategy="ip",
        window_seconds=60,
        max_requests=1,
    )

    enforce_api_rate_limit(
        principal=_build_principal("alpha"),
        request_host="127.0.0.1",
        settings=settings,
        now_monotonic=100.0,
    )
    enforce_api_rate_limit(
        principal=_build_principal("alpha"),
        request_host="127.0.0.2",
        settings=settings,
        now_monotonic=100.0,
    )

    with pytest.raises(RateLimitError, match="Too many requests for the configured window"):
        enforce_api_rate_limit(
            principal=_build_principal("beta"),
            request_host="127.0.0.1",
            settings=settings,
            now_monotonic=101.0,
        )


def test_enforce_api_rate_limit_passes_ip_subject_to_injected_backend() -> None:
    """Injected backends should receive the resolved host-based subject under IP strategy."""
    backend = _RecordingRateLimiterBackend()
    settings = ApiRateLimitSettings(
        enabled=True,
        strategy="ip",
        window_seconds=30,
        max_requests=5,
    )

    enforce_api_rate_limit(
        principal=_build_principal("alpha"),
        request_host="127.0.0.1",
        settings=settings,
        limiter=backend,
        now_monotonic=123.0,
    )

    assert backend.calls == [
        {
            "subject": "ip:127.0.0.1",
            "window_seconds": 30,
            "max_requests": 5,
            "now_monotonic": 123.0,
        }
    ]


# Injected backend seam behavior


def test_enforce_api_rate_limit_uses_injected_backend() -> None:
    """The public limiter seam should honor an injected backend implementation."""
    backend = _RecordingRateLimiterBackend()
    settings = ApiRateLimitSettings(
        enabled=True,
        strategy="principal",
        window_seconds=30,
        max_requests=5,
    )

    enforce_api_rate_limit(
        principal=_build_principal("alpha"),
        settings=settings,
        limiter=backend,
        now_monotonic=123.0,
    )

    assert backend.calls == [
        {
            "subject": "principal:alpha",
            "window_seconds": 30,
            "max_requests": 5,
            "now_monotonic": 123.0,
        }
    ]


def test_enforce_api_rate_limit_propagates_injected_backend_error() -> None:
    """Injected backend failures should surface unchanged through the public seam."""
    backend = _RaisingRateLimiterBackend()
    settings = ApiRateLimitSettings(
        enabled=True,
        strategy="principal",
        window_seconds=30,
        max_requests=5,
    )

    with pytest.raises(RateLimitError, match="backend rejected request"):
        enforce_api_rate_limit(
            principal=_build_principal("alpha"),
            settings=settings,
            limiter=backend,
            now_monotonic=123.0,
        )


def test_enforce_api_rate_limit_skips_injected_backend_when_disabled() -> None:
    """Disabled limiter settings should short-circuit before any backend call happens."""
    backend = _RecordingRateLimiterBackend()
    settings = ApiRateLimitSettings(
        enabled=False,
        strategy="principal",
        window_seconds=30,
        max_requests=5,
    )

    enforce_api_rate_limit(
        principal=_build_principal("alpha"),
        settings=settings,
        limiter=backend,
        now_monotonic=123.0,
    )

    assert backend.calls == []


# Defensive configuration behavior


def test_enforce_api_rate_limit_rejects_unsupported_strategy() -> None:
    """Unexpected limiter strategies should fail clearly instead of silently drifting."""
    settings = ApiRateLimitSettings(
        enabled=True,
        strategy=cast(ApiRateLimitStrategy, "unsupported"),
        window_seconds=60,
        max_requests=1,
    )

    with pytest.raises(RateLimitError, match="Unsupported API rate-limit strategy"):
        enforce_api_rate_limit(
            principal=_build_principal("alpha"),
            settings=settings,
            now_monotonic=100.0,
        )


def _build_principal(key_id: str | None) -> AuthPrincipal:
    """Build a small principal object for limiter-only tests."""
    return AuthPrincipal(
        auth_type="api_key" if key_id is not None else "local",
        subject=f"principal:{key_id}" if key_id is not None else "local-api-client",
        key_id=key_id,
    )


@dataclass
class _RecordingRateLimiterBackend(RateLimiterBackend):
    """Small fake backend that records the limiter call made by the public seam."""

    calls: list[dict[str, object]] = field(default_factory=list)

    def check_and_increment(
        self,
        *,
        subject: str,
        window_seconds: int,
        max_requests: int,
        now_monotonic: float | None = None,
    ) -> None:
        """Record one call so tests can assert the chosen limiter backend was used."""

        self.calls.append(
            {
                "subject": subject,
                "window_seconds": window_seconds,
                "max_requests": max_requests,
                "now_monotonic": now_monotonic,
            }
        )


class _RaisingRateLimiterBackend(RateLimiterBackend):
    """Small fake backend that always rejects to prove error propagation."""

    def check_and_increment(
        self,
        *,
        subject: str,
        window_seconds: int,
        max_requests: int,
        now_monotonic: float | None = None,
    ) -> None:
        raise RateLimitError("backend rejected request")
