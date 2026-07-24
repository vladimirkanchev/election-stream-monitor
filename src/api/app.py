"""FastAPI application setup and shared exception handling.

This module keeps the HTTP app assembly small and explicit:

- validate startup configuration for the current protected boundary
- hide framework documentation outside trusted local mode
- attach the current routers
- serialize shared API-domain errors in one stable envelope
"""

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.errors import (
    ApiDomainError,
    RequestBodyTooLargeError,
    UNEXPECTED_BACKEND_ERROR_STATUS_DETAIL,
)
from api.routers import alerts, detectors, health, playback, sessions
from api_boundary_config import (
    MAX_HTTP_REQUEST_BODY_BYTES,
    is_fastapi_documentation_enabled,
    validate_fastapi_boundary_settings,
)
from logger import get_logger


_HttpRequestHandler = Callable[[Request], Awaitable[Response]]
_LOCAL_ONLY_FRAMEWORK_PATHS = frozenset(
    {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
)
_BODY_BEARING_HTTP_METHODS = frozenset({"PATCH", "POST", "PUT"})
logger = get_logger(__name__)


@asynccontextmanager
async def _app_lifespan(_: FastAPI):
    """Validate current FastAPI boundary settings before serving requests.

    Authentication and limiter behavior is config-driven. Validating it here
    keeps invalid protected-boundary settings from surfacing only after the
    first request.
    """

    validate_fastapi_boundary_settings()
    yield


app = FastAPI(
    title="Election Stream Monitor API",
    version="0.6.2",
    lifespan=_app_lifespan,
)


@app.middleware("http")
async def hide_framework_documentation_in_share_mode(
    request: Request,
    call_next: _HttpRequestHandler,
) -> Response:
    """Hide framework documentation in share mode with a generic 404.

    The guard is request-time because the CLI selects its mode after app import.
    """

    if (
        request.url.path in _LOCAL_ONLY_FRAMEWORK_PATHS
        and not is_fastapi_documentation_enabled()
    ):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return await call_next(request)


@app.middleware("http")
async def reject_oversized_request_bodies(
    request: Request,
    call_next: _HttpRequestHandler,
) -> Response:
    """Reject oversized command bodies before route validation or service work.

    The cached body remains available to downstream handlers. This is an
    application boundary; a hosted deployment still needs an ingress limit.
    """

    if request.method not in _BODY_BEARING_HTTP_METHODS:
        return await call_next(request)

    if len(await request.body()) <= MAX_HTTP_REQUEST_BODY_BYTES:
        return await call_next(request)

    error = RequestBodyTooLargeError(max_bytes=MAX_HTTP_REQUEST_BODY_BYTES)
    return JSONResponse(
        status_code=error.status_code,
        content=error.to_response_content(),
    )


app.include_router(health.router)
app.include_router(detectors.router)
app.include_router(sessions.router)
app.include_router(alerts.router)
app.include_router(playback.router)


@app.exception_handler(ApiDomainError)
async def handle_api_domain_error(request: Request, exc: ApiDomainError) -> JSONResponse:
    """Serialize one transport-facing domain error into the shared API envelope.

    This handler is intentionally generic for the current FastAPI boundary:
    auth failures, rate-limit failures, not-found responses, and other
    transport-facing domain errors all flow through the same body shape, with
    optional headers carried by the exception itself.
    """

    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_response_content(),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Serialize FastAPI request-validation failures in the repo's stable shape."""

    return JSONResponse(
        status_code=422,
        content=_build_request_validation_error_content(exc),
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Return a safe envelope without reflecting unexpected backend diagnostics."""

    logger.error(
        "unexpected_backend_error exception_type=%s",
        type(exc).__name__,
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Unexpected backend error",
            "error_code": "internal_error",
            "status_reason": "internal_error",
            "status_detail": UNEXPECTED_BACKEND_ERROR_STATUS_DETAIL,
        },
    )


def _build_request_validation_error_content(
    exc: RequestValidationError,
) -> dict[str, str]:
    """Build the repo's standard JSON body for FastAPI request validation errors.

    FastAPI's native validation detail is normalized here so validation
    failures stay aligned with the rest of the repo's machine-readable error
    vocabulary.
    """

    details = "; ".join(
        f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
        for err in exc.errors()
    )
    return {
        "detail": "Request validation failed",
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": details,
    }
