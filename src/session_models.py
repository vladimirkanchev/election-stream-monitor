"""Lightweight session-domain models for the local frontend bridge."""

from dataclasses import asdict, dataclass, field
from typing import Literal
from time import gmtime, strftime

from analyzer_contract import InputMode

SessionStatus = Literal[
    "pending",
    "running",
    "cancelling",
    "cancelled",
    "completed",
    "failed",
]
EventSeverity = Literal["info", "warning"]

ALLOWED_SESSION_STATUS_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    "pending": {"pending", "running", "cancelled", "failed"},
    "running": {"running", "cancelled", "completed", "failed"},
    "cancelling": {"cancelling", "cancelled", "failed"},
    "cancelled": {"cancelled"},
    "completed": {"completed"},
    "failed": {"failed"},
}


class InvalidSessionTransitionError(ValueError):
    """Raised when the session state machine receives an impossible transition."""


class InvalidSessionProgressError(ValueError):
    """Raised when persisted session progress violates session invariants."""


@dataclass(frozen=True)
class SessionMetadata:
    """Summary information about one local monitoring session."""

    session_id: str
    mode: InputMode
    input_path: str
    selected_detectors: list[str]
    status: SessionStatus

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable dictionary."""
        return asdict(self)

    def validate(self) -> None:
        """Assert simple metadata invariants before persistence."""
        if not self.session_id:
            raise InvalidSessionTransitionError("session metadata requires a session_id")

    def transition_to(self, status: SessionStatus) -> "SessionMetadata":
        """Return a new metadata object after validating the requested transition."""
        validate_session_status_transition(self.status, status)
        return SessionMetadata(
            session_id=self.session_id,
            mode=self.mode,
            input_path=self.input_path,
            selected_detectors=self.selected_detectors,
            status=status,
        )


@dataclass(frozen=True)
class SessionProgress:
    """Incremental progress written while a session is running."""

    session_id: str
    status: SessionStatus
    processed_count: int
    total_count: int
    current_item: str | None
    latest_result_detector: str | None
    alert_count: int
    last_updated_utc: str
    latest_result_detectors: list[str] = field(default_factory=list)
    status_reason: str | None = None
    status_detail: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable dictionary."""
        return asdict(self)

    def validate(self) -> None:
        """Assert progress invariants before persistence."""
        if self.processed_count < 0 or self.total_count < 0:
            raise InvalidSessionProgressError("session progress counts must be non-negative")
        if self.processed_count > self.total_count:
            raise InvalidSessionProgressError(
                "session progress cannot report more processed items than total items"
            )
        if self.alert_count < 0:
            raise InvalidSessionProgressError("session progress alert_count must be non-negative")
        if self.status == "pending" and self.processed_count != 0:
            raise InvalidSessionProgressError(
                "pending session progress cannot report processed items"
            )
        if self.status == "completed" and self.processed_count != self.total_count:
            raise InvalidSessionProgressError(
                "completed session progress must report all items as processed"
            )
        if self.latest_result_detectors and self.latest_result_detector is None:
            raise InvalidSessionProgressError(
                "latest_result_detector is required when latest_result_detectors is populated"
            )
        if (
            self.latest_result_detector is not None
            and self.latest_result_detectors
            and self.latest_result_detector != self.latest_result_detectors[-1]
        ):
            raise InvalidSessionProgressError(
                "latest_result_detector must match the last detector in latest_result_detectors"
            )

    @classmethod
    def initial(cls, session_id: str, total_count: int) -> "SessionProgress":
        """Create the first progress payload for a new session."""
        return cls(
            session_id=session_id,
            status="pending",
            processed_count=0,
            total_count=total_count,
            current_item=None,
            latest_result_detector=None,
            alert_count=0,
            last_updated_utc=strftime("%Y-%m-%d %H:%M:%S", gmtime()),
            latest_result_detectors=[],
            status_reason="pending",
            status_detail=None,
        )


@dataclass(frozen=True)
class ResultEvent:
    """One analyzer result persisted for the frontend/session layer."""

    session_id: str
    detector_id: str
    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable dictionary."""
        return asdict(self)


@dataclass(frozen=True)
class AlertEvent:
    """One alert event derived from analyzer output."""

    session_id: str
    timestamp_utc: str
    detector_id: str
    title: str
    message: str
    severity: EventSeverity
    source_name: str
    window_index: int | None = None
    window_start_sec: float | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable dictionary."""
        return asdict(self)


def validate_session_status_transition(
    current: SessionStatus,
    target: SessionStatus,
) -> None:
    """Raise when a requested session transition is not part of the allowed lifecycle."""
    if target not in ALLOWED_SESSION_STATUS_TRANSITIONS[current]:
        raise InvalidSessionTransitionError(
            f"Invalid session status transition: {current} -> {target}"
        )


def parse_session_metadata_payload(
    payload: object,
) -> dict[str, object] | None:
    """Return a valid session metadata payload or ``None`` when corrupted."""
    if not isinstance(payload, dict):
        return None
    selected_detectors = payload.get("selected_detectors")
    if not isinstance(selected_detectors, list):
        return None
    try:
        metadata = SessionMetadata(
            session_id=str(payload["session_id"]),
            mode=payload["mode"],
            input_path=str(payload["input_path"]),
            selected_detectors=selected_detectors,
            status=payload["status"],
        )
    except (KeyError, TypeError, ValueError):
        return None

    if (
        not metadata.session_id
        or not all(isinstance(item, str) for item in metadata.selected_detectors)
        or metadata.status not in ALLOWED_SESSION_STATUS_TRANSITIONS
    ):
        return None

    metadata.validate()
    return metadata.to_dict()


def parse_session_progress_payload(
    payload: object,
) -> dict[str, object] | None:
    """Return a valid session progress payload or ``None`` when corrupted."""
    if not isinstance(payload, dict):
        return None
    latest_result_detectors = payload.get("latest_result_detectors", [])
    if not isinstance(latest_result_detectors, list):
        return None
    try:
        progress = SessionProgress(
            session_id=str(payload["session_id"]),
            status=payload["status"],
            processed_count=int(payload["processed_count"]),
            total_count=int(payload["total_count"]),
            current_item=_coerce_optional_string(payload.get("current_item")),
            latest_result_detector=_coerce_optional_string(
                payload.get("latest_result_detector")
            ),
            alert_count=int(payload["alert_count"]),
            last_updated_utc=str(payload["last_updated_utc"]),
            latest_result_detectors=latest_result_detectors,
            status_reason=_coerce_optional_string(payload.get("status_reason")),
            status_detail=_coerce_optional_string(payload.get("status_detail")),
        )
    except (KeyError, TypeError, ValueError):
        return None

    if (
        progress.status not in ALLOWED_SESSION_STATUS_TRANSITIONS
        or not all(isinstance(item, str) for item in progress.latest_result_detectors)
    ):
        return None

    try:
        progress.validate()
    except InvalidSessionProgressError:
        return None
    return progress.to_dict()


def parse_result_event_payload(payload: object) -> dict[str, object] | None:
    """Return a valid result event payload or ``None`` when corrupted."""
    if not isinstance(payload, dict):
        return None
    session_id = payload.get("session_id")
    detector_id = payload.get("detector_id")
    result_payload = payload.get("payload")
    if (
        not isinstance(session_id, str)
        or not session_id
        or not isinstance(detector_id, str)
        or not detector_id
        or not isinstance(result_payload, dict)
    ):
        return None
    return {
        "session_id": session_id,
        "detector_id": detector_id,
        "payload": result_payload,
    }


def parse_alert_event_payload(payload: object) -> dict[str, object] | None:
    """Return a valid alert event payload or ``None`` when corrupted."""
    if not isinstance(payload, dict):
        return None
    required_text_fields = (
        "session_id",
        "timestamp_utc",
        "detector_id",
        "title",
        "message",
        "severity",
        "source_name",
    )
    if not all(isinstance(payload.get(field), str) and payload.get(field) for field in required_text_fields):
        return None
    if payload["severity"] not in ("info", "warning"):
        return None

    window_index = payload.get("window_index")
    if window_index is not None and not isinstance(window_index, int):
        return None
    window_start_sec = payload.get("window_start_sec")
    if window_start_sec is not None and not isinstance(window_start_sec, (int, float)):
        return None
    return {
        "session_id": payload["session_id"],
        "timestamp_utc": payload["timestamp_utc"],
        "detector_id": payload["detector_id"],
        "title": payload["title"],
        "message": payload["message"],
        "severity": payload["severity"],
        "source_name": payload["source_name"],
        "window_index": window_index,
        "window_start_sec": float(window_start_sec) if window_start_sec is not None else None,
    }


def _coerce_optional_string(value: object) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else None
