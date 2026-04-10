"""Guidance for future agent-assisted detector generation.

This module is intentionally lightweight. It gives software agents and human
contributors one place to check what must change when a new detector is added.
"""

REQUIRED_UPDATE_AREAS = (
    "Analyzer code in src/detectors.py or a dedicated analyzer module.",
    "Analyzer registration in src/analyzer_registry.py.",
    "Output schema and file path in src/config.py when a new result type is needed.",
    "Store wiring in src/stores.py when a new CSV output target is introduced.",
    "Processor alert logic in src/processor.py if the detector should raise alerts.",
    "Tests under tests/ for analyzer logic, registry visibility, and routing behavior.",
    "Documentation updates in README.md, docs/adding-an-analyzer.md, and architecture docs when relevant.",
)


def get_detector_generation_notes() -> tuple[str, ...]:
    """Return the required update checklist for agent-generated detectors."""
    return REQUIRED_UPDATE_AREAS
