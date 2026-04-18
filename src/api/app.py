
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.errors import ApiDomainError
from api.routers import detectors, health, playback, sessions


app = FastAPI(title="Election Stream Monitor API", version="0.1.0")

app.include_router(health.router)
app.include_router(detectors.router)
app.include_router(sessions.router)
app.include_router(playback.router)


@app.exception_handler(ApiDomainError)
async def handle_api_domain_error(request: Request, exc: ApiDomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error_code": exc.error_code,
            "status_reason": exc.status_reason,
            "status_detail": exc.status_detail,
        },
    )


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    details = "; ".join(
        f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
        for err in exc.errors()
    )
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Request validation failed",
            "error_code": "validation_failed",
            "status_reason": "validation_failed",
            "status_detail": details,
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Unexpected backend error",
            "error_code": "internal_error",
            "status_reason": "internal_error",
            "status_detail": str(exc),
        },
    )
