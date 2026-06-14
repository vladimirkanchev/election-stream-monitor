"""Shared contracts for production detectors, rules, and runtime rows.

This module keeps the detector-facing boundary explicit without adding a large
modeling layer. The important seam is:

- typed detector rows in memory
- mutable runtime rows for alert evaluation
- flat dictionaries at storage and transport boundaries
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator, Literal, Mapping, NotRequired, Protocol, TypeAlias, TypedDict, Union


class AnalyzerResult(TypedDict):
    """Legacy dict-style detector payload with the shared runtime fields."""

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
    motion_mean: NotRequired[float]
    motion_p90: NotRequired[float]
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


DetectorResult: TypeAlias = Union[AnalyzerResult, "AnalyzerRow"]


@dataclass(frozen=True)
class AnalyzerRow:
    """Typed detector row that still serializes to the flat runtime shape."""

    def to_dict(self) -> dict[str, object]:
        """Return a flat dictionary representation suitable for persistence."""
        return asdict(self)

    def __getitem__(self, key: str) -> object:
        """Provide light mapping-style access for existing detector callers."""
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        """Iterate over field names so row objects behave like mappings."""
        return iter(self.to_dict())

    def __len__(self) -> int:
        """Return the number of serialized row fields."""
        return len(self.to_dict())

    def get(self, key: str, default: object = None) -> object:
        """Return one field value using dict-style fallback semantics."""
        return self.to_dict().get(key, default)

    def keys(self):
        """Return serialized row keys for compatibility with dict-based code."""
        return self.to_dict().keys()


@dataclass(frozen=True)
class DetectorRowBase(AnalyzerRow):
    """Shared metadata carried by every production detector row."""

    analyzer: str
    source_type: str
    source_group: str
    source_name: str
    window_index: int | None
    window_start_sec: float | None
    window_duration_sec: float | None
    timestamp_utc: str
    processing_sec: float

    def shared_fields(self) -> dict[str, object]:
        """Return constructor-ready metadata for typed detector result rows."""
        return {
            "analyzer": self.analyzer,
            "source_type": self.source_type,
            "source_group": self.source_group,
            "source_name": self.source_name,
            "window_index": self.window_index,
            "window_start_sec": self.window_start_sec,
            "window_duration_sec": self.window_duration_sec,
            "timestamp_utc": self.timestamp_utc,
            "processing_sec": self.processing_sec,
        }


@dataclass(frozen=True)
class VideoMetricsRow(DetectorRowBase):
    """Typed production black-screen detector result row."""

    duration_sec: float
    black_detected: bool
    black_segment_count: int
    total_black_sec: float
    longest_black_sec: float
    black_ratio: float
    picture_threshold_used: float
    pixel_threshold_used: float
    min_duration_sec: float


@dataclass(frozen=True)
class VideoBlurRow(DetectorRowBase):
    """Typed production blur detector result row."""

    sample_count: int
    sharpness_p10: float
    sharpness_p90: float
    motion_mean: float
    motion_p90: float
    blur_score: float
    blur_detected: bool
    threshold_used: float
    window_size: int
    consecutive_blurry_windows: int


@dataclass
class RuntimeResultRow:
    """Mutable row shared between the processor, alert rules, and event shaping."""

    analyzer: str
    source_type: str
    source_name: str
    timestamp_utc: str
    processing_sec: float
    source_group: str | None = None
    window_index: int | None = None
    window_start_sec: float | None = None
    window_duration_sec: float | None = None
    extra_fields: dict[str, object] = field(default_factory=dict)

    _SHARED_FIELDS = (
        "analyzer",
        "source_type",
        "source_group",
        "source_name",
        "window_index",
        "window_start_sec",
        "window_duration_sec",
        "timestamp_utc",
        "processing_sec",
    )

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> "RuntimeResultRow | None":
        """Build one runtime row from any dict-like detector result."""
        required_fields = {
            "analyzer",
            "source_type",
            "source_name",
            "timestamp_utc",
            "processing_sec",
        }
        if not required_fields.issubset(row.keys()):
            return None

        shared_values = {field_name: row.get(field_name) for field_name in cls._SHARED_FIELDS}
        extra_fields = {
            key: value
            for key, value in row.items()
            if key not in cls._SHARED_FIELDS
        }
        return cls(
            analyzer=str(shared_values["analyzer"]),
            source_type=str(shared_values["source_type"]),
            source_group=(
                str(shared_values["source_group"])
                if shared_values["source_group"] not in (None, "")
                else None
            ),
            source_name=str(shared_values["source_name"]),
            window_index=shared_values["window_index"],
            window_start_sec=shared_values["window_start_sec"],
            window_duration_sec=shared_values["window_duration_sec"],
            timestamp_utc=str(shared_values["timestamp_utc"]),
            processing_sec=float(shared_values["processing_sec"]),
            extra_fields=extra_fields,
        )

    def clone(self) -> "RuntimeResultRow":
        """Return a detached copy for stateful rule evaluation."""
        return RuntimeResultRow.from_mapping(self.to_dict()) or RuntimeResultRow(
            analyzer=self.analyzer,
            source_type=self.source_type,
            source_group=self.source_group,
            source_name=self.source_name,
            window_index=self.window_index,
            window_start_sec=self.window_start_sec,
            window_duration_sec=self.window_duration_sec,
            timestamp_utc=self.timestamp_utc,
            processing_sec=self.processing_sec,
            extra_fields=dict(self.extra_fields),
        )

    def to_dict(self) -> dict[str, object]:
        """Return one flat dictionary for persistence and event payloads."""
        row = {
            "analyzer": self.analyzer,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "timestamp_utc": self.timestamp_utc,
            "processing_sec": self.processing_sec,
        }
        if self.source_group is not None:
            row["source_group"] = self.source_group
        if self.window_index is not None:
            row["window_index"] = self.window_index
        if self.window_start_sec is not None:
            row["window_start_sec"] = self.window_start_sec
        if self.window_duration_sec is not None:
            row["window_duration_sec"] = self.window_duration_sec
        row.update(self.extra_fields)
        return row

    def __getitem__(self, key: str) -> object:
        """Provide mapping-style access across shared and extra fields."""
        if key in self._SHARED_FIELDS:
            return getattr(self, key)
        return self.extra_fields[key]

    def __setitem__(self, key: str, value: object) -> None:
        """Store mutable rule/export annotations on the runtime row."""
        if key in self._SHARED_FIELDS:
            setattr(self, key, value)
            return
        self.extra_fields[key] = value

    def __iter__(self) -> Iterator[str]:
        """Iterate over flat row keys."""
        return iter(self.to_dict())

    def __len__(self) -> int:
        """Return the number of flat row fields."""
        return len(self.to_dict())

    def get(self, key: str, default: object = None) -> object:
        """Return one field value with dict-style default semantics."""
        if key in self._SHARED_FIELDS:
            value = getattr(self, key)
            return default if value is None else value
        return self.extra_fields.get(key, default)

    def keys(self):
        """Return flat row keys for compatibility with dict-based callers."""
        return self.to_dict().keys()

    def items(self):
        """Return flat row items for compatibility with mapping-style callers."""
        return self.to_dict().items()

    def copy(self) -> dict[str, object]:
        """Return a flat dict copy for compatibility with dict-based callers."""
        return self.to_dict()

    def update(self, values: Mapping[str, object]) -> None:
        """Apply a mapping of row annotations onto the runtime row."""
        for key, value in values.items():
            self[key] = value


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
class Detector(Protocol):
    """Callable contract for one production detector."""

    def __call__(
        self,
        file_path: Path,
        prefix: str | None = None,
        source_group: str | None = None,
        source_name: str | None = None,
        window_index: int | None = None,
        window_start_sec: float | None = None,
        window_duration_sec: float | None = None,
    ) -> DetectorResult:
        """Analyze one file and return a standardized typed row or dict."""


class Analyzer(Detector, Protocol):
    """Backward-compatible alias for older detector naming in the repo."""


StoreName = Literal["video_metrics", "blur_metrics"]
InputMode = Literal["video_segments", "video_files", "api_stream"]
DetectorStatus = Literal["core", "optional", "experimental"]
DetectorOrigin = Literal["built_in", "user"]
DetectorCategory = Literal["quality", "visibility", "stability"]
PluginOrigin = Literal["built_in", "user"]


class PluginManifest(TypedDict):
    """Reserved manifest shape for future plugin validation and loading."""

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
    """One enabled detector registration and its runtime metadata."""

    name: str
    analyzer: Detector
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

    @property
    def detector(self) -> Detector:
        """Return the registered detector using the future-facing name."""
        return self.analyzer


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


@dataclass(frozen=True)
class RuleEvaluationContext:
    """Minimal context passed into one rule evaluation."""

    session_id: str
    detector_id: str
    row: RuntimeResultRow


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
