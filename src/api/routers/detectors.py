from fastapi import APIRouter, Query

from analyzer_contract import DetectorCatalogEntry
from api.schemas import ApiInputMode, DetectorOptionResponse
from detectors.registry import list_available_detectors

router = APIRouter(tags=["detectors"])


@router.get("/detectors", response_model=list[DetectorOptionResponse])
async def get_detectors(
    mode: ApiInputMode | None = Query(default=None),  # noqa: B008
) -> list[DetectorCatalogEntry]:
    return list_available_detectors(mode)
