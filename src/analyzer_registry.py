"""Backward-compatible wrapper around ``detectors.registry``.

Repo-internal code should prefer the canonical detector package directly.
"""

from detectors.registry import ENABLED_ANALYZERS, get_enabled_analyzers, list_available_detectors
