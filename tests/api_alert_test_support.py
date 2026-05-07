"""Shared helpers for FastAPI alert-route tests.

This module owns only small response-payload builders for the alert-route
slice. Keeping the common error shapes here makes the route tests read like
boundary scenarios instead of long literal-comparison fixtures.

It intentionally covers both the raw alert routes and the grouped incident
routes because they share the same FastAPI error envelope.
"""

from collections.abc import Mapping


def build_session_not_found_payload(session_id: str) -> dict[str, str]:
    """Return the stable API payload for one alert-route not-found response."""
    return {
        "detail": "Session not found",
        "error_code": "session_not_found",
        "status_reason": "session_not_found",
        "status_detail": f"No persisted session snapshot found for session_id={session_id}",
    }


def build_validation_error_payload(detail: str) -> dict[str, str]:
    """Return the stable API payload for one alert-route validation failure."""
    return {
        "detail": detail,
        "error_code": "validation_failed",
        "status_reason": "validation_failed",
        "status_detail": detail,
    }


def assert_request_validation_payload(
    payload: Mapping[str, object],
    *,
    field_name: str,
) -> None:
    """Assert the repo's stable FastAPI validation-envelope shape."""
    assert payload["detail"] == "Request validation failed"
    assert payload["error_code"] == "validation_failed"
    assert payload["status_reason"] == "validation_failed"
    status_detail = payload.get("status_detail")
    assert isinstance(status_detail, str)
    assert field_name in status_detail
