
class ApiDomainError(Exception):
    def __init__(
        self,
        *,
        detail: str,
        error_code: str,
        status_code: int,
        status_reason: str | None = None,
        status_detail: str | None = None,
    ) -> None:
        self.detail = detail
        self.error_code = error_code
        self.status_code = status_code
        self.status_reason = status_reason
        self.status_detail = status_detail
        super().__init__(detail)


class SessionNotFoundError(ApiDomainError):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            detail="Session not found",
            error_code="session_not_found",
            status_code=404,
            status_reason="session_not_found",
            status_detail=f"No persisted session snapshot found for session_id={session_id}",
        )


class ValidationFailedError(ApiDomainError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            detail=detail,
            error_code="validation_failed",
            status_code=400,
            status_reason="validation_failed",
            status_detail=detail,
        )


class PlaybackUnavailableError(ApiDomainError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            detail="Playback source could not be resolved",
            error_code="playback_unavailable",
            status_code=400,
            status_reason="playback_unavailable",
            status_detail=detail,
        )


class SessionStartFailedError(ApiDomainError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            detail="Session could not be started",
            error_code="session_start_failed",
            status_code=500,
            status_reason="session_start_failed",
            status_detail=detail,
        )
