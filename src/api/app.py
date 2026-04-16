
from fastapi import FastAPI, Request
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
