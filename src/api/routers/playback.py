from fastapi import APIRouter

from api.errors import PlaybackUnavailableError, ValidationFailedError
from api.schemas import (
    ApiErrorResponse,
    ResolvePlaybackRequest,
    ResolvePlaybackResponse,
)
from playback_sources import resolve_playback_source
from source_validation import validate_source_input
from stream_loader import build_api_stream_playback_contract

router = APIRouter(tags=["playback"])


@router.post(
    "/playback/resolve",
    response_model=ResolvePlaybackResponse,
    responses={
        400: {
            "model": ApiErrorResponse,
            "description": "Validation failed or playback source unavailable",
        },
        422: {
            "model": ApiErrorResponse,
            "description": "Request validation failed",
        },
    },
)
async def resolve_playback(payload: ResolvePlaybackRequest) -> ResolvePlaybackResponse:
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
