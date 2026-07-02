"""Shared session-domain models for durable session state.

These dataclasses and parsers define the storage-neutral session shapes used
by the file-backed store, the PostgreSQL store, and the snapshot read model
consumed by API, CLI, and bridge code.
"""

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

# Persisted session metadata uses this lifecycle map as the backend source of
# truth. Route-level responses may still surface transient summaries such as
# `cancelling` before `session.json` settles to a terminal state.
TERMINAL_SESSION_STATUSES: set[SessionStatus] = {"cancelled", "completed", "failed"}

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


class InvalidResultEventError(ValueError):
    """Raised when persisted detector-result rows violate shared invariants."""


_RESULT_PAYLOAD_HINT_VALIDATORS: tuple[
    tuple[str, type[object] | tuple[type[object], ...], str],
    ...,
] = (
    ("timestamp_utc", str, "result payload timestamp_utc must be a string when present"),
    ("detector_name", str, "result payload detector_name must be a string when present"),
    ("source_name", str, "result payload source_name must be a string when present"),
    ("window_index", int, "result payload window_index must be an int when present"),
    (
        "window_start_sec",
        (int, float),
        "result payload window_start_sec must be numeric when present",
    ),
    ("title", str, "result payload title must be a string when present"),
    ("message", str, "result payload message must be a string when present"),
    ("severity", str, "result payload severity must be a string when present"),
)


@dataclass(frozen=True)
class SessionMetadata:
    """Stable metadata persisted for one monitoring session."""

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
    """Latest-only progress snapshot for one session.

    This is a durable polling read model, not a progress-event history.
    """

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
    """One append-ordered durable detector result row.

    The contract stays intentionally small: `session_id` ties the row to a
    session, `detector_id` names the detector, and `payload` holds detector
    facts plus any shared timing or source hints.
    """

    session_id: str
    detector_id: str
    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable dictionary."""
        return asdict(self)

    def validate(self) -> None:
        """Assert the minimal durable result-event contract before persistence."""
        if not self.session_id:
            raise InvalidResultEventError("result event requires a session_id")
        if not self.detector_id:
            raise InvalidResultEventError("result event requires a detector_id")
        if not isinstance(self.payload, dict):
            raise InvalidResultEventError("result event payload must be a dictionary")

        for field_name, expected_type, error_message in _RESULT_PAYLOAD_HINT_VALIDATORS:
            _validate_optional_result_payload_field(
                self.payload,
                field_name,
                expected_type,
                error_message=error_message,
            )


@dataclass(frozen=True)
class AlertEvent:
    """One persisted alert event derived from detector output and rule policy."""

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
    """Return a valid result-event payload or ``None`` when corrupted."""
    if not isinstance(payload, dict):
        return None
    try:
        result_event = ResultEvent(
            session_id=payload["session_id"],
            detector_id=payload["detector_id"],
            payload=payload["payload"],
        )
    except (KeyError, TypeError, ValueError):
        return None

    try:
        result_event.validate()
    except InvalidResultEventError:
        return None
    return result_event.to_dict()


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


def _validate_optional_result_payload_field(
    payload: dict[str, object],
    field_name: str,
    expected_type: type[object] | tuple[type[object], ...],
    *,
    error_message: str,
) -> None:
    """Raise when one optional shared result-payload hint has the wrong type."""
    value = payload.get(field_name)
    if value is not None and not isinstance(value, expected_type):
        raise InvalidResultEventError(error_message)
