"""FastAPI adapter for bounded playback-source resolution.

The router owns request validation and HTTP error mapping. It inherits the
shared authentication dependency so playback resolution is protected in share
mode while source-resolution rules remain in their dedicated modules.
"""

from fastapi import APIRouter, Depends

from api.errors import PlaybackUnavailableError, ValidationFailedError
from api.http_auth_policy import AUTHENTICATION_FAILURE_RESPONSES
from api.playback_route_policy import require_http_playback_principal
from api.schemas import (
    ApiErrorResponse,
    ApiRateLimitErrorResponse,
    ResolvePlaybackRequest,
    ResolvePlaybackResponse,
)
from playback_sources import resolve_playback_source
from source_validation import validate_source_input
from stream_loader import build_api_stream_playback_contract

router = APIRouter(
    tags=["playback"],
    dependencies=[Depends(require_http_playback_principal)],
)


@router.post(
    "/playback/resolve",
    response_model=ResolvePlaybackResponse,
    responses={
        **AUTHENTICATION_FAILURE_RESPONSES,
        400: {
            "model": ApiErrorResponse,
            "description": "Validation failed or playback source unavailable",
        },
        413: {"model": ApiErrorResponse, "description": "Request body too large"},
        422: {
            "model": ApiErrorResponse,
            "description": "Request validation failed",
        },
        429: {
            "model": ApiRateLimitErrorResponse,
            "description": "Rate limit exceeded",
        },
    },
)
async def resolve_playback(payload: ResolvePlaybackRequest) -> ResolvePlaybackResponse:
    """Validate one source and return its operator-facing playback contract."""

    try:
        validated_input_path = validate_source_input(payload.mode, payload.input_path)
    except (OSError, ValueError) as err:
        raise ValidationFailedError(str(err)) from err

    try:
        if payload.mode == "api_stream":
            return ResolvePlaybackResponse(
                source=build_api_stream_playback_contract(validated_input_path).source
            )

        resolved = resolve_playback_source(
            mode=payload.mode,
            input_path=validated_input_path,
            current_item=payload.current_item,
        )
        return ResolvePlaybackResponse(source=resolved)
    except (OSError, ValueError) as err:
        raise PlaybackUnavailableError(str(err)) from err
