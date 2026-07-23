"""FastAPI rate-limiting boundary helpers.

This module keeps the first limiter implementation small and explicit:

- one settings seam
- caller subject selection with optional route-family namespaces
- one in-memory fixed-window store

The route layer can call into it after authentication succeeds, while shared
application services remain unaware of request counting. The current in-memory
store is intentionally local and per-process so it can be replaced later by a
shared backend such as Redis without changing the FastAPI route contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Protocol

from api_auth import AuthPrincipal
from api_boundary_config import (
    ApiRateLimitSettings,
    ApiRateLimitStrategy,
    get_api_rate_limit_settings,
)

RATE_LIMIT_EXCEEDED_DETAIL = "Too many requests for the configured window."
UNKNOWN_REQUEST_HOST = "unknown"


class RateLimitError(Exception):
    """Raised when one caller exceeds the configured request budget.

    The limiter raises this plain domain-style error so the FastAPI boundary
    can decide how to surface it as a stable `429` response.
    """


@dataclass(frozen=True)
class ResolvedRateLimitContext:
    """Resolved settings, safe caller subject, and optional route-family budget."""

    settings: ApiRateLimitSettings
    subject: str
    budget_name: str | None = None


class RateLimiterBackend(Protocol):
    """Storage seam for checking and incrementing one caller budget."""

    def check_and_increment(
        self,
        *,
        subject: str,
        window_seconds: int,
        max_requests: int,
        now_monotonic: float | None = None,
    ) -> None:
        """Record one request or raise when the current window is exhausted."""


@dataclass
class _FixedWindowCounter:
    """Internal counter state for one fixed-window limiter subject."""

    window_start_monotonic: float
    request_count: int


class InMemoryFixedWindowRateLimiter:
    """Local in-memory fixed-window limiter for one FastAPI process.

    This is intentionally the only concrete backend in the current repo
    state. The public seam is small enough that a later shared backend can
    replace this class without changing route-policy code or HTTP contracts.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, _FixedWindowCounter] = {}

    def check_and_increment(
        self,
        *,
        subject: str,
        window_seconds: int,
        max_requests: int,
        now_monotonic: float | None = None,
    ) -> None:
        """Record one request or raise when the current window is exhausted.

        The current algorithm is a simple fixed window keyed by one resolved
        subject string. It favors readability and deterministic local behavior
        over distributed precision, which matches the current project stage.
        """

        effective_now = monotonic() if now_monotonic is None else now_monotonic
        with self._lock:
            counter = self._counters.get(subject)
            if counter is None or _should_start_new_window(
                counter=counter,
                effective_now=effective_now,
                window_seconds=window_seconds,
            ):
                self._start_new_window(
                    subject=subject,
                    effective_now=effective_now,
                )
                return

            if counter.request_count >= max_requests:
                raise RateLimitError(RATE_LIMIT_EXCEEDED_DETAIL)

            counter.request_count += 1

    def reset(self) -> None:
        """Clear all in-memory counters.

        This is mainly a test seam for the current local in-memory
        implementation.
        """

        with self._lock:
            self._counters.clear()

    def _start_new_window(
        self,
        *,
        subject: str,
        effective_now: float,
    ) -> None:
        """Create or replace one subject counter at the start of a new window."""

        self._counters[subject] = _FixedWindowCounter(
            window_start_monotonic=effective_now,
            request_count=1,
        )


_DEFAULT_RATE_LIMITER = InMemoryFixedWindowRateLimiter()


def enforce_api_rate_limit(
    *,
    principal: AuthPrincipal,
    request_host: str | None = None,
    settings: ApiRateLimitSettings | None = None,
    limiter: RateLimiterBackend | None = None,
    now_monotonic: float | None = None,
    budget_name: str | None = None,
) -> None:
    """Enforce one configured caller budget, optionally namespaced by route family."""

    context = resolve_api_rate_limit_context(
        principal=principal,
        request_host=request_host,
        settings=settings,
        budget_name=budget_name,
    )
    if context is None:
        return

    enforce_resolved_rate_limit(
        context=context,
        limiter=limiter,
        now_monotonic=now_monotonic,
    )


def resolve_api_rate_limit_context(
    *,
    principal: AuthPrincipal,
    request_host: str | None = None,
    settings: ApiRateLimitSettings | None = None,
    budget_name: str | None = None,
) -> ResolvedRateLimitContext | None:
    """Resolve settings and a safe caller subject for one optional budget family."""

    active_settings = settings or get_api_rate_limit_settings()
    if not active_settings.enabled:
        return None

    subject = build_rate_limit_subject(
        principal=principal,
        strategy=active_settings.strategy,
        request_host=request_host,
    )
    return ResolvedRateLimitContext(
        settings=active_settings,
        subject=_prefix_rate_limit_subject(subject, budget_name),
        budget_name=budget_name,
    )


def enforce_resolved_rate_limit(
    *,
    context: ResolvedRateLimitContext,
    limiter: RateLimiterBackend | None = None,
    now_monotonic: float | None = None,
) -> None:
    """Enforce one previously resolved rate-limit context.

    This is the smallest seam the FastAPI boundary needs once subject and
    settings resolution has already happened. It keeps policy resolution and
    storage mutation separate without introducing a heavier abstraction model.
    """

    active_limiter = limiter or _DEFAULT_RATE_LIMITER
    active_limiter.check_and_increment(
        subject=context.subject,
        window_seconds=context.settings.window_seconds,
        max_requests=context.settings.max_requests,
        now_monotonic=now_monotonic,
    )


def build_rate_limit_subject(
    *,
    principal: AuthPrincipal,
    strategy: ApiRateLimitStrategy,
    request_host: str | None,
) -> str:
    """Build the current rate-limit subject from the selected strategy.

    The returned string is safe for local logging and in-memory accounting.
    It should identify the caller budget clearly without exposing raw API-key
    material.
    """

    if strategy == "principal":
        return _build_principal_rate_limit_subject(principal)
    if strategy == "ip":
        return f"ip:{request_host or UNKNOWN_REQUEST_HOST}"
    raise RateLimitError("Unsupported API rate-limit strategy")


def _prefix_rate_limit_subject(subject: str, budget_name: str | None) -> str:
    """Keep independent route-family budgets separate for the same caller."""

    if budget_name is None:
        return subject
    return f"budget:{budget_name}:{subject}"


def _build_principal_rate_limit_subject(principal: AuthPrincipal) -> str:
    """Build one principal-based rate-limit subject.

    The preferred identifier is `principal.key_id`, which keeps the limiter
    keyed to the authenticated caller without exposing the raw API key.
    When no `key_id` is available, fall back to the current local principal
    identity so auth-disabled local runs still have one deterministic subject.
    """

    if principal.key_id is not None:
        return f"principal:{principal.key_id}"
    return f"principal:{principal.subject}"


def _should_start_new_window(
    *,
    counter: _FixedWindowCounter,
    effective_now: float,
    window_seconds: int,
) -> bool:
    """Return whether one fixed-window counter has expired."""

    return effective_now - counter.window_start_monotonic >= window_seconds


def reset_api_rate_limit_state() -> None:
    """Reset the default in-memory limiter state for tests.

    Production code should treat the module-level default limiter as an
    internal implementation detail. This helper exists so tests can keep the
    local in-memory backend isolated across scenarios.
    """

    _DEFAULT_RATE_LIMITER.reset()
