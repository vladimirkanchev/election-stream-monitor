"""Tests for exporting the detector catalog from the canonical registry.

This keeps the small JSON export CLI aligned with the same metadata contract
used by the API route, session CLI, and frontend detector picker.
"""

import json

import export_detector_catalog
from detectors.registry import list_available_detectors


def _run_export_catalog(monkeypatch, output_path) -> list[dict[str, object]]:
    """Run the export CLI and return the written detector catalog."""
    monkeypatch.setattr(
        "sys.argv",
        [
            "export_detector_catalog.py",
            "--output",
            str(output_path),
        ],
    )

    export_detector_catalog.main()
    return json.loads(output_path.read_text(encoding="utf-8"))


def test_export_detector_catalog_writes_canonical_registry_json(
    monkeypatch,
    tmp_path,
) -> None:
    """The export CLI should write the same catalog exposed by the registry."""
    output_path = tmp_path / "frontend" / "detectors.json"
    assert _run_export_catalog(monkeypatch, output_path) == list_available_detectors()
