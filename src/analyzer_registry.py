"""Registry of enabled analyzers for each supported input mode."""

from analyzer_contract import AnalyzerRegistration, DetectorCatalogEntry, InputMode
from detectors import analyze_video_blur, analyze_video_metrics

ENABLED_ANALYZERS: tuple[AnalyzerRegistration, ...] = (
    AnalyzerRegistration(
        name="video_metrics",
        analyzer=analyze_video_metrics,
        store_name="video_metrics",
        supported_modes=("video_segments", "video_files", "api_stream"),
        supported_suffixes=(".ts", ".mp4"),
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
        supported_modes=("video_segments", "video_files", "api_stream"),
        supported_suffixes=(".ts", ".mp4"),
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
    """Return the analyzer registrations enabled for a given input mode.

    Args:
        mode: Active runtime mode such as ``video_segments`` or ``api_stream``.

    Returns:
        A list of registrations that should be considered by the processor.
    """
    return [
        registration
        for registration in ENABLED_ANALYZERS
        if mode in registration.supported_modes
    ]


def list_available_detectors(
    mode: InputMode | None = None,
) -> list[DetectorCatalogEntry]:
    """Return frontend-friendly detector metadata.

    Args:
        mode: Optional mode filter. When omitted, all registered detectors are
            returned.

    Returns:
        A list of plain dictionaries that can be serialized for UI use.
    """
    registrations = (
        get_enabled_analyzers(mode) if mode is not None else list(ENABLED_ANALYZERS)
    )
    return [
        {
            "id": registration.name,
            "display_name": registration.display_name,
            "description": registration.description,
            "category": registration.category,
            "origin": registration.origin,
            "status": registration.status,
            "default_rule_id": registration.default_rule_id,
            "default_selected": registration.default_selected,
            "produces_alerts": registration.produces_alerts,
            "supported_modes": list(registration.supported_modes),
            "supported_suffixes": list(registration.supported_suffixes),
        }
        for registration in registrations
    ]
