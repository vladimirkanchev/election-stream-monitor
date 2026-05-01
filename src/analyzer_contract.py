"""Shared detector, slice, and plugin metadata contracts.

The goal of this module is stability. Frontend code, local bridge helpers, and
future backend/service layers should be able to rely on these types even as new
analyzers are added.

Even though the project does not support dynamic plugin loading yet, this
module already defines the metadata contracts that built-in detectors, future
user extensions, and transport layers should agree on.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NotRequired, Protocol, TypedDict


class AnalyzerResult(TypedDict):
    """Base metadata shape expected in every analyzer result.

    Concrete analyzers may add more keys, but these shared fields should always
    be present so the processor and stores can handle results consistently.
    """

    analyzer: str
    source_type: str
    source_group: NotRequired[str]
    source_name: str
    window_index: NotRequired[int | None]
    window_start_sec: NotRequired[float | None]
    window_duration_sec: NotRequired[float | None]
    timestamp_utc: str
    processing_sec: float
    duration_sec: NotRequired[float]
    sample_count: NotRequired[int]
    sharpness_p10: NotRequired[float]
    sharpness_p90: NotRequired[float]
    blur_score: NotRequired[float]
    blur_detected: NotRequired[bool]
    threshold_used: NotRequired[float]
    window_size: NotRequired[int]
    consecutive_blurry_windows: NotRequired[int]
    black_detected: NotRequired[bool]
    black_segment_count: NotRequired[int]
    total_black_sec: NotRequired[float]
    longest_black_sec: NotRequired[float]
    black_ratio: NotRequired[float]
    picture_threshold_used: NotRequired[float]
    pixel_threshold_used: NotRequired[float]
    min_duration_sec: NotRequired[float]


class DetectorCatalogEntry(TypedDict):
    """Frontend-facing detector metadata exported from the analyzer registry.

    This is the catalog shape consumed by setup UI and bridge normalization.
    """

    id: str
    display_name: str
    description: str
    category: str
    origin: str
    status: str
    default_rule_id: str | None
    default_selected: bool
    produces_alerts: bool
    supported_modes: list[str]
    supported_suffixes: list[str]


class AlertRuleCatalogEntry(TypedDict):
    """Frontend-ready metadata for one alert rule registration."""

    id: str
    detector_id: str
    display_name: str
    description: str
    origin: str
    status: str


# pylint: disable=too-few-public-methods
class Analyzer(Protocol):
    """Callable contract for analyzers that process one input file at a time."""

    def __call__(
        self,
        file_path: Path,
        prefix: str | None = None,
        source_group: str | None = None,
        source_name: str | None = None,
        window_index: int | None = None,
        window_start_sec: float | None = None,
        window_duration_sec: float | None = None,
    ) -> AnalyzerResult:
        """Analyze one file and return a standardized result dictionary."""


StoreName = Literal["video_metrics", "blur_metrics"]
InputMode = Literal["video_segments", "video_files", "api_stream"]
DetectorStatus = Literal["core", "optional", "experimental"]
DetectorOrigin = Literal["built_in", "user"]
DetectorCategory = Literal["quality", "visibility", "stability"]
PluginOrigin = Literal["built_in", "user"]


class PluginManifest(TypedDict):
    """Manifest shape reserved for future plugin loading and validation.

    The runtime does not discover external plugins yet. This manifest exists so
    built-in and future user-owned extension bundles can already share one
    explicit validation contract.
    """

    plugin_id: str
    display_name: str
    origin: PluginOrigin
    detector_ids: list[str]
    rule_ids: list[str]
    enabled_by_default: bool


class PluginManifestValidationError(ValueError):
    """Raised when a plugin manifest violates current correctness/security rules."""


@dataclass(frozen=True)
class AnalyzerRegistration:
    """Registry entry describing one enabled analyzer.

    Each registration links a callable analyzer with the input modes, file
    suffixes, output store, and frontend-facing metadata it supports.
    """

    name: str
    analyzer: Analyzer
    store_name: StoreName
    supported_modes: tuple[InputMode, ...]
    supported_suffixes: tuple[str, ...]
    display_name: str
    description: str
    category: DetectorCategory = "quality"
    origin: DetectorOrigin = "built_in"
    status: DetectorStatus = "core"
    default_rule_id: str | None = None
    default_selected: bool = False
    produces_alerts: bool = False


@dataclass(frozen=True)
class AnalysisSlice:
    """One temporal slice processed by analyzers.

    `.ts` inputs naturally map to one slice per file. `.mp4` inputs can be
    expanded into fixed-duration windows so detectors and alert rules operate
    on the same temporal model.

    The `source_name` is the user-facing slice identity that later appears in
    result rows, alerts, progress, and playback alignment.
    """

    file_path: Path
    source_group: str
    source_name: str
    window_index: int | None = None
    window_start_sec: float | None = None
    window_duration_sec: float | None = None


def validate_plugin_manifest(
    manifest: PluginManifest,
    *,
    existing_detector_ids: set[str] | None = None,
    existing_rule_ids: set[str] | None = None,
) -> PluginManifest:
    """Validate one plugin manifest before any dynamic loading is attempted.

    The validator intentionally enforces ownership and collision rules early so
    future user- or agent-authored plugins cannot silently override built-in
    detector or rule ids.
    """
    plugin_id = manifest.get("plugin_id", "").strip()
    display_name = manifest.get("display_name", "").strip()
    origin = manifest.get("origin")
    detector_ids = _normalize_manifest_id_list(
        manifest.get("detector_ids"),
        label="detector_ids",
    )
    rule_ids = _normalize_manifest_id_list(
        manifest.get("rule_ids"),
        label="rule_ids",
    )
    enabled_by_default = manifest.get("enabled_by_default")

    if not plugin_id:
        raise PluginManifestValidationError("Plugin manifest requires a non-empty plugin_id.")
    if not display_name:
        raise PluginManifestValidationError("Plugin manifest requires a display_name.")
    if origin not in ("built_in", "user"):
        raise PluginManifestValidationError("Plugin manifest requires an explicit built_in or user origin.")
    if not isinstance(enabled_by_default, bool):
        raise PluginManifestValidationError("Plugin manifest requires enabled_by_default to be boolean.")

    _raise_on_duplicate_ids(
        detector_ids,
        existing_ids=existing_detector_ids or set(),
        label="detector",
    )
    _raise_on_duplicate_ids(
        rule_ids,
        existing_ids=existing_rule_ids or set(),
        label="rule",
    )

    if origin == "user" and enabled_by_default:
        raise PluginManifestValidationError(
            "User plugins must be disabled by default until explicitly enabled."
        )

    return PluginManifest(
        plugin_id=plugin_id,
        display_name=display_name,
        origin=origin,
        detector_ids=detector_ids,
        rule_ids=rule_ids,
        enabled_by_default=enabled_by_default,
    )


def _raise_on_duplicate_ids(
    ids: list[str],
    *,
    existing_ids: set[str],
    label: str,
) -> None:
    """Raise when one manifest reuses ids internally or collides with existing ids."""
    duplicate_ids = {item for item in ids if ids.count(item) > 1}
    if duplicate_ids:
        raise PluginManifestValidationError(
            f"Plugin manifest contains duplicate {label} ids: {sorted(duplicate_ids)}"
        )

    conflicting_ids = sorted(existing_ids.intersection(ids))
    if conflicting_ids:
        raise PluginManifestValidationError(
            f"Plugin manifest {label} ids conflict with existing registrations: {conflicting_ids}"
        )


def _normalize_manifest_id_list(value: object, *, label: str) -> list[str]:
    """Normalize one manifest id list by requiring and trimming non-empty strings."""
    if not isinstance(value, list):
        raise PluginManifestValidationError(
            f"Plugin manifest {label} must be a list of non-empty strings."
        )

    normalized_ids: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise PluginManifestValidationError(
                f"Plugin manifest {label} must be a list of non-empty strings."
            )
        normalized_ids.append(item.strip())

    return normalized_ids
