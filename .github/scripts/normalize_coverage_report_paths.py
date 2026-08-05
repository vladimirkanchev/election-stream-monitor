"""Normalize CI coverage metadata to repository-relative paths before upload."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from xml.etree import ElementTree


class CoveragePathError(ValueError):
    """Raised when a report would expose a path outside the repository."""


def relative_path(value: str, repository_root: Path) -> str:
    """Return a portable repository-relative report path."""
    candidate = Path(value)
    if not candidate.is_absolute():
        if ".." in candidate.parts:
            raise CoveragePathError(
                f"Coverage report path escapes the repository: {value}"
            )
        return candidate.as_posix()

    try:
        return candidate.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError as error:
        raise CoveragePathError(
            f"Coverage report path is outside the repository: {value}"
        ) from error


def normalize_json_summary(report_path: Path, repository_root: Path) -> None:
    """Rewrite absolute file keys in a Vitest JSON-summary report."""
    report = json.loads(report_path.read_text())
    if not isinstance(report, dict):
        raise CoveragePathError("Coverage JSON summary must be an object.")

    normalized: dict[str, object] = {}
    for path, summary in report.items():
        if path == "total":
            normalized[path] = summary
            continue
        normalized_path = relative_path(path, repository_root)
        if normalized_path in normalized:
            raise CoveragePathError(
                f"Coverage JSON summary has duplicate relative path: {normalized_path}"
            )
        normalized[normalized_path] = summary

    report_path.write_text(json.dumps(normalized, indent=2) + "\n")


def normalize_lcov(report_path: Path, repository_root: Path) -> None:
    """Rewrite absolute source-file entries in an LCOV report."""
    normalized_lines = []
    for line in report_path.read_text().splitlines(keepends=True):
        if line.startswith("SF:"):
            suffix = "\n" if line.endswith("\n") else ""
            line = f"SF:{relative_path(line[3:].rstrip(), repository_root)}{suffix}"
        normalized_lines.append(line)
    report_path.write_text("".join(normalized_lines))


def normalize_cobertura(report_path: Path, repository_root: Path) -> None:
    """Rewrite absolute source and class paths in a Cobertura XML report."""
    tree = ElementTree.parse(report_path)
    root = tree.getroot()

    for source in root.findall(".//source"):
        if source.text:
            source.text = relative_path(source.text, repository_root)
    for class_element in root.findall(".//class"):
        filename = class_element.get("filename")
        if filename:
            class_element.set("filename", relative_path(filename, repository_root))

    tree.write(report_path, encoding="utf-8", xml_declaration=True)


def _normalize_if_present(
    report_path: Path,
    normalizer: Callable[[Path, Path], None],
    repository_root: Path,
    *,
    allow_missing: bool,
) -> None:
    if report_path.exists():
        normalizer(report_path, repository_root)
    elif not allow_missing:
        raise CoveragePathError(f"Coverage report does not exist: {report_path}")


def parse_args() -> argparse.Namespace:
    """Parse the narrow report paths produced by the coverage CI workflow."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--backend-xml", type=Path, required=True)
    parser.add_argument("--frontend-json", type=Path, required=True)
    parser.add_argument("--frontend-lcov", type=Path, required=True)
    parser.add_argument("--allow-missing", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Normalize approved reports while allowing partial failed-run output."""
    args = parse_args()
    repository_root = args.repository_root.resolve()

    _normalize_if_present(
        args.backend_xml,
        normalize_cobertura,
        repository_root,
        allow_missing=args.allow_missing,
    )
    _normalize_if_present(
        args.frontend_json,
        normalize_json_summary,
        repository_root,
        allow_missing=args.allow_missing,
    )
    _normalize_if_present(
        args.frontend_lcov,
        normalize_lcov,
        repository_root,
        allow_missing=args.allow_missing,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
