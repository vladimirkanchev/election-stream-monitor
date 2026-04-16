from pydantic import BaseModel, Field


class ApiErrorResponse(BaseModel):
    detail: str
    error_code: str
    status_reason: str | None = None
    status_detail: str | None = None


class StartSessionRequest(BaseModel):
    mode: str
    input_path: str
    selected_detectors: list[str] = Field(default_factory=list)


class CancelSessionResponse(BaseModel):
    session_id: str
    mode: str | None = None
    input_path: str | None = None
    selected_detectors: list[str] = Field(default_factory=list)
    status: str


class ResolvePlaybackRequest(BaseModel):
    mode: str
    input_path: str
    current_item: str | None = None


class ResolvePlaybackResponse(BaseModel):
    source: str | None


class HealthResponse(BaseModel):
    status: str
