from typing import Literal

from pydantic import BaseModel, Field


ApiInputMode = Literal["video_segments", "video_files", "api_stream"]
ApiSessionStatus = Literal[
    "pending",
    "running",
    "cancelling",
    "cancelled",
    "completed",
    "failed",
]
ApiAlertSeverity = Literal["info", "warning"]


class StartSessionRequest(BaseModel):
    mode: ApiInputMode
    input_path: str
    selected_detectors: list[str] = Field(default_factory=list)


class CancelSessionResponse(BaseModel):
    session_id: str
    mode: str | None = None
    input_path: str | None = None
    selected_detectors: list[str] = Field(default_factory=list)
    status: str


class ResolvePlaybackRequest(BaseModel):
    mode: ApiInputMode
    input_path: str
    current_item: str | None = None


class ResolvePlaybackResponse(BaseModel):
    source: str | None


class HealthResponse(BaseModel):
    status: str


class ApiErrorResponse(BaseModel):
    detail: str
    error_code: str
    status_reason: str | None = None
    status_detail: str | None = None


class DetectorOptionResponse(BaseModel):
    id: str
    display_name: str
    description: str
    category: str
    origin: str
    status: str
    default_rule_id: str | None = None
    default_selected: bool
    produces_alerts: bool
    supported_modes: list[str] = Field(default_factory=list)
    supported_suffixes: list[str] = Field(default_factory=list)


class SessionSummaryResponse(BaseModel):
    session_id: str
    mode: ApiInputMode
    input_path: str
    selected_detectors: list[str] = Field(default_factory=list)
    status: ApiSessionStatus


class SessionProgressResponse(BaseModel):
    session_id: str
    status: ApiSessionStatus
    processed_count: int
    total_count: int
    current_item: str | None = None
    latest_result_detector: str | None = None
    alert_count: int
    last_updated_utc: str
    latest_result_detectors: list[str] = Field(default_factory=list)
    status_reason: str | None = None
    status_detail: str | None = None


class ResultEventResponse(BaseModel):
    session_id: str
    detector_id: str
    payload: dict[str, object]


class AlertEventResponse(BaseModel):
    session_id: str
    timestamp_utc: str
    detector_id: str
    title: str
    message: str
    severity: ApiAlertSeverity
    source_name: str
    window_index: int | None = None
    window_start_sec: float | None = None


class SessionSnapshotResponse(BaseModel):
    session: SessionSummaryResponse | None = None
    progress: SessionProgressResponse | None = None
    alerts: list[AlertEventResponse] = Field(default_factory=list)
    results: list[ResultEventResponse] = Field(default_factory=list)
    latest_result: ResultEventResponse | None = None
