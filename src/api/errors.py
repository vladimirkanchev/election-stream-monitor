"""FastAPI-facing domain error types.

These exceptions let the route layer describe stable HTTP error semantics
without pushing transport concerns into the shared application services. Each
error captures the repo's standard API error envelope fields so the app-level
exception handler can serialize one consistent payload shape.
"""


class ApiDomainError(Exception):
    """Base transport-facing error that carries one structured API failure.

    Route adapters raise these errors after translating shared-service or
    boundary-policy outcomes into the repo's stable HTTP contract. The app
    layer then serializes the error consistently through one shared exception
    handler.
    """

    def __init__(
        self,
        *,
        detail: str,
        error_code: str,
        status_code: int,
        status_reason: str | None = None,
        status_detail: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.detail = detail
        self.error_code = error_code
        self.status_code = status_code
        self.status_reason = status_reason
        self.status_detail = status_detail
        self.headers = headers
        super().__init__(detail)

    def to_response_content(self) -> dict[str, str | None]:
        """Return the stable JSON body for one serialized API-domain error.

        Keeping body construction here avoids repeating envelope assembly in
        the app-level handler and makes header-only extensions additive.
        """

        return {
            "detail": self.detail,
            "error_code": self.error_code,
            "status_reason": self.status_reason,
            "status_detail": self.status_detail,
        }


class SessionNotFoundError(ApiDomainError):
    """Error raised when one requested session snapshot is not persisted."""

    def __init__(self, session_id: str) -> None:
        super().__init__(
            detail="Session not found",
            error_code="session_not_found",
            status_code=404,
            status_reason="session_not_found",
            status_detail=f"No persisted session snapshot found for session_id={session_id}",
        )


class ValidationFailedError(ApiDomainError):
    """Error raised when one validated API input fails domain checks."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            detail=detail,
            error_code="validation_failed",
            status_code=400,
            status_reason="validation_failed",
            status_detail=detail,
        )


class AuthenticationFailedError(ApiDomainError):
    """Error raised when one HTTP request fails the FastAPI auth boundary."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            detail="Authentication failed",
            error_code="authentication_failed",
            status_code=401,
            status_reason="authentication_failed",
            status_detail=detail,
        )


class RateLimitExceededError(ApiDomainError):
    """Error raised when one protected caller exceeds the current request budget.

    The current implementation keeps the JSON body stable while optionally
    attaching a coarse `Retry-After` header derived from the active fixed
    window size.
    """

    def __init__(
        self,
        detail: str,
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(
            detail="Rate limit exceeded",
            error_code="rate_limit_exceeded",
            status_code=429,
            status_reason="rate_limit_exceeded",
            status_detail=detail,
            headers=_build_retry_after_headers(retry_after_seconds),
        )


class ResponseLimitExceededError(ApiDomainError):
    """Error raised when a complete response exceeds its boundary without truncation."""

    def __init__(self, *, resource: str, max_bytes: int) -> None:
        super().__init__(
            detail=f"{resource} exceeds the supported response size",
            error_code="response_limit_exceeded",
            status_code=422,
            status_reason="response_limit_exceeded",
            status_detail=f"Maximum serialized response size is {max_bytes} bytes.",
        )


def _build_retry_after_headers(retry_after_seconds: int | None) -> dict[str, str] | None:
    """Return the optional HTTP headers for one coarse rate-limit rejection.

    The current limiter uses a fixed-window policy, so a simple whole-window
    ``Retry-After`` value is a sufficient first client hint without changing
    the stable JSON error payload.
    """

    if retry_after_seconds is None:
        return None
    return {"Retry-After": str(retry_after_seconds)}


class PlaybackUnavailableError(ApiDomainError):
    """Error raised when playback resolution cannot return a usable source."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            detail="Playback source could not be resolved",
            error_code="playback_unavailable",
            status_code=400,
            status_reason="playback_unavailable",
            status_detail=detail,
        )


class SessionStartFailedError(ApiDomainError):
    """Error raised when session startup fails after request validation passed."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            detail="Session could not be started",
            error_code="session_start_failed",
            status_code=500,
            status_reason="session_start_failed",
            status_detail=detail,
        )


class CancelFailedError(ApiDomainError):
    """Error raised when a session cannot transition into cancelling state."""

    def __init__(self, session_id: str, current_status: str) -> None:
        super().__init__(
            detail="Session cannot be cancelled from its current state",
            error_code="cancel_failed",
            status_code=409,
            status_reason="cancel_failed",
            status_detail=f"Session {session_id} is already {current_status}.",
        )
