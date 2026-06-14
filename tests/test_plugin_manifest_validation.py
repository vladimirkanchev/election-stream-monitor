"""Tests for the small future-facing plugin manifest validation contract."""

from analyzer_contract import (
    PluginManifestValidationError,
    validate_plugin_manifest,
)
from alert_rules import list_available_alert_rules
from detectors.registry import list_available_detectors


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
