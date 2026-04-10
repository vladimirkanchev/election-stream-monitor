"""Orchestration helpers that connect detectors, stores, and alert rules.

This module is the execution boundary between the registry and the session
runner. It is intentionally responsible for only a few things:

- select the detectors that apply to the current mode and suffix
- call them with the right slice context
- persist valid result rows
- evaluate alert rules from those rows
- isolate detector failures while surfacing persistence failures
"""

import inspect
from pathlib import Path

from analyzer_contract import AnalysisSlice, InputMode
from alert_rules import evaluate_alerts
from analyzer_registry import get_enabled_analyzers
from logger import format_log_context, get_logger
from session_models import ResultEvent
from stores import black_frame_store, blur_metrics_store

logger = get_logger(__name__)

STORE_REGISTRY = {
    "video_metrics": black_frame_store,
    "blur_metrics": blur_metrics_store,
}

REQUIRED_RESULT_FIELDS = {
    "analyzer",
    "source_type",
    "source_name",
    "timestamp_utc",
    "processing_sec",
}


class ProcessorPersistenceError(OSError):
    """Raised when a validated analyzer result cannot be persisted safely."""

    def __init__(
        self,
        *,
        detector_id: str,
        store_name: str,
        file_path: Path,
        cause: Exception,
    ) -> None:
        super().__init__(
            f"Failed to persist analyzer result for {detector_id} via {store_name} while processing {file_path}: {cause}"
        )
        self.detector_id = detector_id
        self.store_name = store_name
        self.file_path = file_path
        self.__cause__ = cause


def run_enabled_analyzers_bundle(
    file_path: Path,
    prefix: str,
    mode: InputMode,
    session_id: str,
    selected_analyzers: set[str] | None = None,
    persist_to_store: bool = True,
    analysis_slice: AnalysisSlice | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Run analyzers and return a session-friendly results/alerts bundle."""
    results: list[dict[str, object]] = []
    alerts: list[dict[str, object]] = []
    current_item = _resolve_current_item_name(analysis_slice, file_path)

    for registration in _iter_matching_registrations(
        mode=mode,
        file_path=file_path,
        selected_analyzers=selected_analyzers,
    ):

        try:
            row = _run_analyzer(
                registration.analyzer,
                file_path=file_path,
                prefix=prefix,
                analysis_slice=analysis_slice,
            )
        except Exception:  # pragma: no cover - asserted via tests
            logger.exception(
                "Analyzer %s failed for %s [%s]",
                registration.name,
                file_path,
                _build_execution_log_context(
                    session_id=session_id,
                    source_kind=mode,
                    current_item=current_item,
                    detector_id=registration.name,
                ),
            )
            continue

        if not _is_valid_result_row(row):
            logger.warning(
                "Analyzer %s returned a malformed row for %s: %r [%s]",
                registration.name,
                file_path,
                row,
                _build_execution_log_context(
                    session_id=session_id,
                    source_kind=mode,
                    current_item=current_item,
                    detector_id=registration.name,
                ),
            )
            continue

        logger.info("%s analysis result: %s", registration.name, row)

        if persist_to_store:
            _persist_result_row(
                session_id=session_id,
                source_kind=mode,
                current_item=current_item,
                detector_id=registration.name,
                store_name=registration.store_name,
                row=row,
                file_path=file_path,
            )

        results.append(
            ResultEvent(
                session_id=session_id,
                detector_id=registration.name,
                payload=row,
            ).to_dict()
        )
        alerts.extend(
            alert.to_dict()
            for alert in evaluate_alerts(session_id, registration.name, row)
        )

    return {"results": results, "alerts": alerts}


def _iter_matching_registrations(
    *,
    mode: InputMode,
    file_path: Path,
    selected_analyzers: set[str] | None,
):
    """Yield only the registrations that match the current run configuration."""
    suffix = file_path.suffix.lower()
    for registration in get_enabled_analyzers(mode):
        if selected_analyzers is not None and registration.name not in selected_analyzers:
            continue
        if suffix not in registration.supported_suffixes:
            continue
        yield registration


def _run_analyzer(
    analyzer,
    file_path: Path,
    prefix: str,
    analysis_slice: AnalysisSlice | None,
) -> dict[str, object]:
    """Call one analyzer while only passing supported keyword arguments."""
    kwargs: dict[str, object] = {
        "file_path": file_path,
        "prefix": prefix,
    }
    if analysis_slice is not None:
        kwargs.update(
            {
                "source_group": analysis_slice.source_group,
                "source_name": analysis_slice.source_name,
                "window_index": analysis_slice.window_index,
                "window_start_sec": analysis_slice.window_start_sec,
                "window_duration_sec": analysis_slice.window_duration_sec,
            }
        )

    accepted = inspect.signature(analyzer).parameters
    filtered_kwargs = {
        key: value
        for key, value in kwargs.items()
        if key in accepted
    }
    return analyzer(**filtered_kwargs)


def _is_valid_result_row(row: object) -> bool:
    """Return True when an analyzer row includes the base shared fields."""
    return (
        isinstance(row, dict)
        and bool(row)
        and REQUIRED_RESULT_FIELDS.issubset(row.keys())
    )


def _persist_result_row(
    *,
    session_id: str,
    source_kind: InputMode,
    current_item: str,
    detector_id: str,
    store_name: str,
    row: dict[str, object],
    file_path: Path,
) -> None:
    """Persist one validated row or raise a session-fatal persistence error."""
    try:
        store = STORE_REGISTRY[store_name]
        store.add_row(row)
    except Exception as error:
        logger.exception(
            "Store write failed for analyzer %s (%s) while processing %s [%s]",
            detector_id,
            store_name,
            file_path,
            _build_execution_log_context(
                session_id=session_id,
                source_kind=source_kind,
                current_item=current_item,
                detector_id=detector_id,
            ),
        )
        raise ProcessorPersistenceError(
            detector_id=detector_id,
            store_name=store_name,
            file_path=file_path,
            cause=error,
        ) from error


def _resolve_current_item_name(
    analysis_slice: AnalysisSlice | None,
    file_path: Path,
) -> str:
    """Return the best current-item label for logging context."""
    if analysis_slice is not None:
        return analysis_slice.source_name
    return file_path.name


def _build_execution_log_context(
    *,
    session_id: str,
    source_kind: InputMode,
    current_item: str,
    detector_id: str,
) -> str:
    """Build consistent processor log context for one detector execution path."""
    return format_log_context(
        session_id=session_id,
        source_kind=source_kind,
        current_item=current_item,
        detector_id=detector_id,
    )


def run_enabled_analyzers(
    file_path: Path,
    prefix: str,
    mode: InputMode,
) -> list[dict]:
    """Run all enabled analyzers for one file and persist their outputs.

    The registry decides which analyzers are active for the supplied mode.
    Matching analyzers are executed one by one, and each result row is written
    to the store declared by the analyzer registration.

    Args:
        file_path: Input file to analyze.
        prefix: Logical input prefix used by the current run.
        mode: Active input mode, such as ``video_segments`` or ``api_stream``.

    Returns:
        A list of analyzer result rows produced for this file.
    """
    bundle = run_enabled_analyzers_bundle(
        file_path=file_path,
        prefix=prefix,
        mode=mode,
        session_id="standalone-run",
        persist_to_store=True,
    )
    return [dict(event["payload"]) for event in bundle["results"]]


def process_video_file(file_path: Path, prefix: str, mode: InputMode) -> list[dict]:
    """Process one local video input using the analyzers enabled for its mode."""
    return run_enabled_analyzers(file_path=file_path, prefix=prefix, mode=mode)
