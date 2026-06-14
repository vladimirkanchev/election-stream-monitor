"""Catalog shaping helpers for the explicit detector registry."""

from collections.abc import Sequence

from analyzer_contract import AnalyzerRegistration, DetectorCatalogEntry


def build_detector_catalog(
    registrations: Sequence[AnalyzerRegistration],
) -> list[DetectorCatalogEntry]:
    """Return frontend-facing detector metadata for explicit registrations."""
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
