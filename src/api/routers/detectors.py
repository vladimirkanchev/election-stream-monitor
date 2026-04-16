from fastapi import APIRouter, Query

from analyzer_registry import list_available_detectors

router = APIRouter(tags=["detectors"])


@router.get("/detectors")
async def get_detectors(mode: str | None = Query(default=None)) -> list[dict[str, object]]:
    return list_available_detectors(mode)
