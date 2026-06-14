"""Tests for explicit detector registry ownership, catalog metadata, and shim behavior.

This suite serves two purposes:

- document which detectors are currently enabled for each input mode
- keep the explicit registry decision visible for future refactors
"""

from dataclasses import replace

import analyzer_registry
from alert_rules import list_available_alert_rules
from analyzer_registry import (
    get_enabled_analyzers as get_enabled_analyzers_compat,
    list_available_detectors as list_available_detectors_compat,
)
from detectors import registry as detector_registry
from detectors.registry import get_enabled_analyzers, list_available_detectors


EXPLICIT_PUBLIC_SURFACE = (
    "ENABLED_ANALYZERS",
    "get_enabled_analyzers",
    "list_available_detectors",
)

EXPECTED_REGISTRY_CONTRACT = {
    "video_metrics": {
        "supported_modes": ["video_segments", "video_files", "api_stream"],
        "supported_suffixes": [".ts", ".mp4"],
        "default_rule_id": "video_metrics.default_rule",
        "display_name": "Black Screen",
        "status": "core",
        "produces_alerts": True,
    },
    "video_blur": {
        "supported_modes": ["video_segments", "video_files", "api_stream"],
        "supported_suffixes": [".ts", ".mp4"],
        "default_rule_id": "video_blur.default_rule",
        "display_name": "Blur Check",
        "status": "optional",
        "produces_alerts": True,
    },
}


def test_video_segment_mode_enables_video_analyzers() -> None:
    """Video segment mode should expose both metric and blur analyzers."""
    registrations = get_enabled_analyzers("video_segments")

    assert [registration.name for registration in registrations] == [
        "video_metrics",
        "video_blur",
    ]
    assert registrations[0].store_name == "video_metrics"


def test_api_stream_mode_reuses_video_metrics_registration() -> None:
    """Future API stream mode should already map to video analyzers."""
    registrations = get_enabled_analyzers("api_stream")

    assert [registration.name for registration in registrations] == [
        "video_metrics",
        "video_blur",
    ]


def test_video_file_mode_reuses_video_detector_registrations() -> None:
    """Video file mode should expose the same built-in detector registrations."""
    registrations = get_enabled_analyzers("video_files")

    assert [registration.name for registration in registrations] == [
        "video_metrics",
        "video_blur",
    ]


def test_registration_exposes_detector_alias_for_future_extension_contracts() -> None:
    """Registrations should expose the detector callable through the new alias too."""
    registration = get_enabled_analyzers("video_segments")[0]

    assert registration.detector is registration.analyzer


def test_compatibility_wrapper_reexports_canonical_registry_helpers() -> None:
    """Older imports should stay aligned with the canonical detector registry."""
    assert get_enabled_analyzers_compat is detector_registry.get_enabled_analyzers
    assert list_available_detectors_compat is detector_registry.list_available_detectors

    compat_catalog = list_available_detectors_compat("video_segments")
    canonical_catalog = list_available_detectors("video_segments")

    assert compat_catalog == canonical_catalog


def test_compatibility_wrapper_exposes_only_the_registry_edge() -> None:
    """The shim should stay a narrow compatibility edge, not a second registry owner."""
    assert analyzer_registry.__all__ == EXPLICIT_PUBLIC_SURFACE
    assert analyzer_registry.ENABLED_ANALYZERS is detector_registry.ENABLED_ANALYZERS


def test_canonical_registry_exposes_only_the_explicit_public_surface() -> None:
    """The canonical registry should keep helper logic outside its public surface."""
    assert detector_registry.__all__ == EXPLICIT_PUBLIC_SURFACE


def test_list_available_detectors_returns_frontend_metadata() -> None:
    """Detector catalog export should expose the frontend-facing metadata contract."""
    detectors = list_available_detectors("video_segments")

    assert detectors[0]["id"] == "video_metrics"
    assert detectors[0]["display_name"] == "Black Screen"
    assert detectors[0]["description"]
    assert detectors[0]["origin"] == "built_in"
    assert detectors[0]["default_rule_id"] == "video_metrics.default_rule"
    assert detectors[0]["default_selected"] is False
    assert detectors[1]["id"] == "video_blur"


def test_registry_preserves_expected_detector_contracts() -> None:
    """The explicit registry should keep the shipped detector contract stable."""
    registrations = list(detector_registry.ENABLED_ANALYZERS)
    detectors = list_available_detectors()

    assert [registration.name for registration in registrations] == list(
        EXPECTED_REGISTRY_CONTRACT
    )
    assert [detector["id"] for detector in detectors] == list(
        EXPECTED_REGISTRY_CONTRACT
    )

    for registration, detector in zip(registrations, detectors, strict=True):
        expected = EXPECTED_REGISTRY_CONTRACT[registration.name]

        assert registration.name == detector["id"]
        assert detector["display_name"] == expected["display_name"]
        assert detector["status"] == expected["status"]
        assert detector["default_rule_id"] == expected["default_rule_id"]
        assert detector["produces_alerts"] is expected["produces_alerts"]
        assert detector["supported_modes"] == expected["supported_modes"]
        assert detector["supported_suffixes"] == expected["supported_suffixes"]
        assert registration.supported_modes == tuple(expected["supported_modes"])
        assert registration.supported_suffixes == tuple(expected["supported_suffixes"])
        assert registration.default_rule_id == expected["default_rule_id"]


def test_explicit_registry_owns_runtime_detector_metadata() -> None:
    """The explicit registry should keep detector ownership visible in one place."""
    registrations = get_enabled_analyzers("video_segments")
    detectors = list_available_detectors("video_segments")

    assert [registration.name for registration in registrations] == [
        detector["id"] for detector in detectors
    ]

    for registration, detector in zip(registrations, detectors, strict=True):
        assert callable(registration.detector)
        assert registration.store_name
        assert registration.supported_modes
        assert registration.supported_suffixes
        assert detector["supported_modes"] == list(registration.supported_modes)
        assert detector["supported_suffixes"] == list(registration.supported_suffixes)
        assert detector["default_rule_id"] == registration.default_rule_id
        assert detector["display_name"] == registration.display_name
        assert detector["description"] == registration.description


def test_detector_default_rules_point_to_existing_matching_rule_metadata() -> None:
    """Each built-in detector default rule should resolve to matching rule metadata."""
    detectors = list_available_detectors()
    rules_by_id = {
        rule["id"]: rule
        for rule in list_available_alert_rules()
    }

    for detector in detectors:
        default_rule_id = detector["default_rule_id"]
        assert default_rule_id is not None
        assert default_rule_id in rules_by_id
        assert rules_by_id[default_rule_id]["detector_id"] == detector["id"]


def test_list_available_detectors_preserves_null_default_rule_ids() -> None:
    """Detectors without a bundled default rule should expose a null linkage safely."""
    original_registrations = detector_registry.ENABLED_ANALYZERS
    registration = original_registrations[0]
    detector_registry.ENABLED_ANALYZERS = (
        replace(
            registration,
            name="custom_detector",
            display_name="Custom Detector",
            description="Detector without a bundled rule",
            default_rule_id=None,
            default_selected=False,
            produces_alerts=False,
        ),
    )
    try:
        detectors = list_available_detectors()
    finally:
        detector_registry.ENABLED_ANALYZERS = original_registrations

    assert detectors == [
        {
            "id": "custom_detector",
            "display_name": "Custom Detector",
            "description": "Detector without a bundled rule",
            "category": registration.category,
            "origin": registration.origin,
            "status": registration.status,
            "default_rule_id": None,
            "default_selected": False,
            "produces_alerts": False,
            "supported_modes": list(registration.supported_modes),
            "supported_suffixes": list(registration.supported_suffixes),
        }
    ]
