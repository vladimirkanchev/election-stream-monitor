"""Canonical registry of enabled production detectors.

This module keeps runtime detector ownership explicit. It owns:

- detector identifiers
- detector callable wiring
- supported input modes and file suffixes
- result store targets
- frontend-facing detector catalog metadata
- default alert-rule linkage

It does not implement detector logic or dynamic plugin discovery.
"""

from analyzer_contract import AnalyzerRegistration, DetectorCatalogEntry, InputMode

from .black_screen import analyze_video_metrics
from .blur import analyze_video_blur
from .catalog import build_detector_catalog

__all__ = (
    "ENABLED_ANALYZERS",
    "get_enabled_analyzers",
    "list_available_detectors",
)

_VIDEO_MODES: tuple[InputMode, ...] = (
    "video_segments",
    "video_files",
    "api_stream",
)
_VIDEO_SUFFIXES = (".ts", ".mp4")

# Keep registrations declarative so the runtime surface stays easy to scan.
ENABLED_ANALYZERS: tuple[AnalyzerRegistration, ...] = (
    AnalyzerRegistration(
        name="video_metrics",
        analyzer=analyze_video_metrics,
        store_name="video_metrics",
        supported_modes=_VIDEO_MODES,
        supported_suffixes=_VIDEO_SUFFIXES,
        display_name="Black Screen",
        description="Warns when a video chunk or file stays nearly black for too long.",
        category="quality",
        status="core",
        default_rule_id="video_metrics.default_rule",
        default_selected=False,
        produces_alerts=True,
    ),
    AnalyzerRegistration(
        name="video_blur",
        analyzer=analyze_video_blur,
        store_name="blur_metrics",
        supported_modes=_VIDEO_MODES,
        supported_suffixes=_VIDEO_SUFFIXES,
        display_name="Blur Check",
        description="Flags blurry video using rolling frame samples and normalized blur scoring.",
        category="quality",
        status="optional",
        default_rule_id="video_blur.default_rule",
        default_selected=False,
        produces_alerts=True,
    ),
)


def get_enabled_analyzers(mode: InputMode) -> list[AnalyzerRegistration]:
    """Return the detector registrations enabled for one input mode."""
    return [
        registration
        for registration in ENABLED_ANALYZERS
        if mode in registration.supported_modes
    ]


def list_available_detectors(
    mode: InputMode | None = None,
) -> list[DetectorCatalogEntry]:
    """Return frontend-facing detector metadata."""
    registrations = (
        get_enabled_analyzers(mode) if mode is not None else list(ENABLED_ANALYZERS)
    )
    return build_detector_catalog(registrations)
