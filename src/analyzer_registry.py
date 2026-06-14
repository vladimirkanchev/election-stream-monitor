"""Compatibility re-exports for the canonical detector registry.

The canonical registry lives in ``src/detectors/registry.py``.
This module re-exports only the compatibility-facing registry edge.

Repo-internal code should prefer the canonical detector package directly.
"""

from detectors.registry import ENABLED_ANALYZERS, get_enabled_analyzers, list_available_detectors

__all__ = (
    "ENABLED_ANALYZERS",
    "get_enabled_analyzers",
    "list_available_detectors",
)
