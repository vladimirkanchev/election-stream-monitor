"""Logging helpers for the local monitoring runtime.

The project currently relies on structured context strings rather than a full
structured logging backend. These helpers keep the format compact while also
redacting source references that would otherwise leak full local paths, full
remote URLs, or payload-like metadata into logs.
"""

import logging
import os
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_LOG_LEVEL = "INFO"
REDACTED_PAYLOAD = "<redacted-payload>"
REDACTED_PATH_PREFIX = "<path:"
REDACTED_URL_SUFFIX = "/<redacted>"


def get_logger(name: str) -> logging.Logger:
    """Return a lazily configured module logger with the project format."""
    curr_logger = logging.getLogger(name)
    if not curr_logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        handler.setFormatter(formatter)
        curr_logger.addHandler(handler)
        level_name = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
        level = getattr(logging, level_name, logging.INFO)
        curr_logger.setLevel(level)
        curr_logger.propagate = False
    return curr_logger


logger = get_logger(__name__)


def format_log_context(**fields: object) -> str:
    """Return a compact `key=value` context string for non-empty logging fields.

    Values are sanitized before formatting so call sites can safely pass source
    paths, URLs, or payload-like objects without leaking their full contents.
    """
    parts: list[str] = []
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, str) and not value:
            continue
        parts.append(f"{key}={sanitize_log_value(key, value)!r}")
    return " ".join(parts)


def sanitize_log_value(key: str, value: object) -> object:
    """Redact sensitive source references and payload-like values for one field."""
    if isinstance(value, dict):
        return REDACTED_PAYLOAD
    if isinstance(value, (list, tuple)) and _looks_like_payload_collection(value):
        return REDACTED_PAYLOAD
    if not isinstance(value, str):
        return value

    lowered_key = key.lower()
    if lowered_key.endswith("_payload") or lowered_key == "payload":
        return REDACTED_PAYLOAD
    if lowered_key.endswith("_url") or lowered_key in {"input_url", "source_url"}:
        return redact_source_url(value)
    if lowered_key.endswith("_path") or lowered_key in {"input_path", "source_path"}:
        return redact_local_path(value)
    return value


def redact_source_url(url: str) -> str:
    """Keep only the URL origin in logs and redact the rest of the path/query."""
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.hostname:
        return "<redacted-url>"
    if parsed.port:
        return f"{parsed.scheme}://{parsed.hostname}:{parsed.port}{REDACTED_URL_SUFFIX}"
    return f"{parsed.scheme}://{parsed.hostname}{REDACTED_URL_SUFFIX}"


def redact_local_path(path_value: str) -> str:
    """Keep only the basename for local path-like values in logs."""
    path_name = Path(path_value.strip()).name or "<root>"
    return f"{REDACTED_PATH_PREFIX}{path_name}>"


def _looks_like_payload_collection(value: list[object] | tuple[object, ...]) -> bool:
    """Return whether a sequence looks like a collection of payload dictionaries."""
    return bool(value) and all(isinstance(item, dict) for item in value)
