"""Tests for detector catalog export and pre-loader plugin manifest validation.

This suite serves two purposes:

- document which detectors are currently enabled for each input mode
- lock in the metadata and security rules that future plugin loading must obey
"""

import analyzer_registry
from analyzer_contract import (
    PluginManifestValidationError,
    validate_plugin_manifest,
)
from analyzer_registry import get_enabled_analyzers, list_available_detectors
from alert_rules import list_available_alert_rules


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
    original_registrations = analyzer_registry.ENABLED_ANALYZERS
    registration = original_registrations[0]
    analyzer_registry.ENABLED_ANALYZERS = (
        registration.__class__(
            name="custom_detector",
            analyzer=registration.analyzer,
            store_name=registration.store_name,
            supported_modes=registration.supported_modes,
            supported_suffixes=registration.supported_suffixes,
            display_name="Custom Detector",
            description="Detector without a bundled rule",
            category=registration.category,
            origin=registration.origin,
            status=registration.status,
            default_rule_id=None,
            default_selected=False,
            produces_alerts=False,
        ),
    )
    try:
        detectors = list_available_detectors()
    finally:
        analyzer_registry.ENABLED_ANALYZERS = original_registrations

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


def test_validate_plugin_manifest_accepts_built_in_manifest_with_explicit_ownership() -> None:
    """Built-in plugin manifests should remain valid when ownership is explicit."""
    validated = validate_plugin_manifest(
        {
            "plugin_id": "built_in.quality_bundle",
            "display_name": "Quality Bundle",
            "origin": "built_in",
            "detector_ids": [" video_metrics ", "video_blur"],
            "rule_ids": ["video_metrics.default_rule", "video_blur.default_rule"],
            "enabled_by_default": True,
        }
    )

    assert validated["origin"] == "built_in"
    assert validated["detector_ids"] == ["video_metrics", "video_blur"]
    assert validated["rule_ids"] == [
        "video_metrics.default_rule",
        "video_blur.default_rule",
    ]


def test_validate_plugin_manifest_rejects_missing_explicit_origin() -> None:
    """Future plugin manifests should not be accepted without explicit ownership metadata."""
    try:
        validate_plugin_manifest(
            {
                "plugin_id": "user.custom_bundle",
                "display_name": "Custom Bundle",
                "detector_ids": ["custom.detector"],
                "rule_ids": ["custom.detector.default_rule"],
                "enabled_by_default": False,
            }
        )
    except PluginManifestValidationError as error:
        assert "explicit built_in or user origin" in str(error)
    else:
        raise AssertionError("Expected manifest validation to fail without origin")


def test_validate_plugin_manifest_rejects_duplicate_detector_ids() -> None:
    """One manifest should not be allowed to register the same detector id twice."""
    try:
        validate_plugin_manifest(
            {
                "plugin_id": "user.custom_bundle",
                "display_name": "Custom Bundle",
                "origin": "user",
                "detector_ids": ["custom.detector", " custom.detector "],
                "rule_ids": ["custom.detector.default_rule"],
                "enabled_by_default": False,
            }
        )
    except PluginManifestValidationError as error:
        assert "duplicate detector ids" in str(error)
    else:
        raise AssertionError("Expected duplicate detector ids to be rejected")


def test_validate_plugin_manifest_rejects_conflicts_with_existing_registrations() -> None:
    """User plugins should not be able to override built-in detector or rule ids silently."""
    try:
        validate_plugin_manifest(
            {
                "plugin_id": "user.conflicting_bundle",
                "display_name": "Conflicting Bundle",
                "origin": "user",
                "detector_ids": ["video_metrics"],
                "rule_ids": ["video_metrics.default_rule"],
                "enabled_by_default": False,
            },
            existing_detector_ids={detector["id"] for detector in list_available_detectors()},
            existing_rule_ids={rule["id"] for rule in list_available_alert_rules()},
        )
    except PluginManifestValidationError as error:
        assert "conflict with existing registrations" in str(error)
    else:
        raise AssertionError("Expected conflicting ids to be rejected")


def test_validate_plugin_manifest_rejects_user_plugins_enabled_by_default() -> None:
    """User plugins should require an explicit trust step before activation."""
    try:
        validate_plugin_manifest(
            {
                "plugin_id": "user.custom_bundle",
                "display_name": "Custom Bundle",
                "origin": "user",
                "detector_ids": ["custom.detector"],
                "rule_ids": ["custom.detector.default_rule"],
                "enabled_by_default": True,
            }
        )
    except PluginManifestValidationError as error:
        assert "disabled by default" in str(error)
    else:
        raise AssertionError("Expected enabled-by-default user plugin to be rejected")


def test_validate_plugin_manifest_rejects_duplicate_rule_ids() -> None:
    """One manifest should not be allowed to register the same rule id twice."""
    try:
        validate_plugin_manifest(
            {
                "plugin_id": "user.custom_bundle",
                "display_name": "Custom Bundle",
                "origin": "user",
                "detector_ids": ["custom.detector"],
                "rule_ids": ["custom.rule", " custom.rule "],
                "enabled_by_default": False,
            }
        )
    except PluginManifestValidationError as error:
        assert "duplicate rule ids" in str(error)
    else:
        raise AssertionError("Expected duplicate rule ids to be rejected")


def test_validate_plugin_manifest_rejects_blank_detector_ids() -> None:
    """Plugin manifests should reject blank detector identifiers after trimming."""
    try:
        validate_plugin_manifest(
            {
                "plugin_id": "user.custom_bundle",
                "display_name": "Custom Bundle",
                "origin": "user",
                "detector_ids": ["   "],
                "rule_ids": ["custom.rule"],
                "enabled_by_default": False,
            }
        )
    except PluginManifestValidationError as error:
        assert "detector_ids must be a list of non-empty strings" in str(error)
    else:
        raise AssertionError("Expected blank detector ids to be rejected")
