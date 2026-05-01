from fastapi import APIRouter, Query

from analyzer_contract import DetectorCatalogEntry
from analyzer_registry import list_available_detectors
from api.schemas import ApiInputMode, DetectorOptionResponse

router = APIRouter(tags=["detectors"])


@router.get("/detectors", response_model=list[DetectorOptionResponse])
async def get_detectors(mode: ApiInputMode | None = Query(default=None)) -> list[DetectorCatalogEntry]:
    return list_available_detectors(mode)
