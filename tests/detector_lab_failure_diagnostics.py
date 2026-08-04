"""Best-effort, bounded diagnostics for checked-in detector-lab media failures.

Only allowlisted public fields and decoder versions may reach logs or CI
artifacts. Diagnostic failures never replace the original test failure.
"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

ARTIFACT_DIR_ENV = "ESM_DETECTOR_LAB_ARTIFACT_DIR"
MAX_DIAGNOSTIC_ROWS = 24
MAX_DIAGNOSTIC_BYTES = 64 * 1024
MAX_CSV_FILES = 12
MAX_CSV_BYTES = 512 * 1024
MAX_CSV_TOTAL_BYTES = 4 * 1024 * 1024
_SAFE_ROW_FIELDS = (
    "algorithm_id",
    "detector_id",
    "window_index",
    "window_start_sec",
    "practical_detected",
    "black_detected",
    "blur_detected",
    "practical_score",
    "practical_threshold",
    "guardrail_reason",
    "alert_count",
)


@dataclass(frozen=True)
class DetectorLabDiagnosticContext:
    """Allowlisted fixture identity and requested scope for one media run."""

    label: str
    fixture_id: str
    algorithm_ids: tuple[str, ...]
    max_windows: int


def _command_version(command: str) -> str | None:
    """Return one tool version line without exposing executable paths."""
    try:
        completed = subprocess.run(
            [command, "-version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.partition("\n")[0].strip() or None


def _environment_versions() -> dict[str, str | None]:
    """Return the allowlisted decoder environment projection."""
    try:
        import cv2
    except ImportError:
        opencv_version = None
    else:
        opencv_version = str(cv2.__version__)
    return {
        "python": sys.version.split()[0],
        "ffmpeg": _command_version("ffmpeg"),
        "ffprobe": _command_version("ffprobe"),
        "opencv": opencv_version,
    }


def _compact_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Project detector rows to the small public field allowlist."""
    return [
        {field_name: row[field_name] for field_name in _SAFE_ROW_FIELDS if field_name in row}
        for row in rows[:MAX_DIAGNOSTIC_ROWS]
    ]


def _counts_by_detector(rows: Sequence[Mapping[str, object]]) -> dict[str, int]:
    """Count returned rows by their stable detector identity."""
    counts: dict[str, int] = {}
    for row in rows:
        detector_id = row.get("detector_id")
        if isinstance(detector_id, str):
            counts[detector_id] = counts.get(detector_id, 0) + 1
    return counts


def build_failure_diagnostic(
    context: DetectorLabDiagnosticContext,
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Build one bounded report without paths, failures, or raw metric payloads."""
    requested_row_count = context.max_windows * len(context.algorithm_ids)
    return {
        "fixture": {"id": context.fixture_id, "label": context.label},
        "environment": _environment_versions(),
        "expected": {
            "algorithm_ids": list(context.algorithm_ids),
            "algorithm_count": len(context.algorithm_ids),
            "max_windows": context.max_windows,
            "requested_row_count": requested_row_count,
        },
        "actual": {
            "row_count": len(rows),
            "detector_row_counts": _counts_by_detector(rows),
            "rows": _compact_rows(rows),
            "rows_truncated": len(rows) > MAX_DIAGNOSTIC_ROWS,
        },
    }


def _persist_failure_diagnostic(context: DetectorLabDiagnosticContext, diagnostic: dict[str, object]) -> None:
    """Persist a bounded report only when CI requested detector-lab artifacts."""
    artifact_dir = os.environ.get(ARTIFACT_DIR_ENV, "").strip()
    if not artifact_dir:
        return

    serialized = f"{json.dumps(diagnostic, indent=2, sort_keys=True)}\n".encode()
    if len(serialized) > MAX_DIAGNOSTIC_BYTES:
        print("[detector-lab] failure diagnostic omitted: size limit exceeded")
        return

    artifact_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", context.label).strip("-")
    output_path = Path(artifact_dir) / f"{artifact_name or 'unknown'}.failure.json"
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(serialized)
    except OSError:
        print("[detector-lab] failure diagnostic could not be persisted")


def persist_csv_artifact(output_csv: Path) -> bool:
    """Persist one safe CSV projection when configured and within artifact bounds."""
    artifact_dir_value = os.environ.get(ARTIFACT_DIR_ENV, "").strip()
    if not artifact_dir_value:
        return False

    artifact_dir = Path(artifact_dir_value)
    destination = artifact_dir / output_csv.name
    try:
        source_size = output_csv.stat().st_size
    except OSError:
        print("[detector-lab] CSV artifact could not be inspected")
        return False

    if source_size > MAX_CSV_BYTES:
        print("[detector-lab] CSV artifact omitted: file size limit exceeded")
        return False

    try:
        with output_csv.open(encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            if not reader.fieldnames or not set(reader.fieldnames) & set(_SAFE_ROW_FIELDS):
                print("[detector-lab] CSV artifact omitted: no reviewed fields")
                return False

            serialized_csv = StringIO(newline="")
            writer = csv.DictWriter(serialized_csv, fieldnames=_SAFE_ROW_FIELDS)
            writer.writeheader()
            writer.writerows(
                {
                    field_name: row.get(field_name, "") or ""
                    for field_name in _SAFE_ROW_FIELDS
                }
                for row in reader
            )
        serialized = serialized_csv.getvalue().encode()
    except (csv.Error, OSError, UnicodeError):
        print("[detector-lab] CSV artifact could not be sanitized")
        return False

    if len(serialized) > MAX_CSV_BYTES:
        print("[detector-lab] CSV artifact omitted: file size limit exceeded")
        return False

    try:
        existing_csvs = tuple(artifact_dir.glob("*.csv")) if artifact_dir.exists() else ()
        other_csvs = tuple(path for path in existing_csvs if path != destination)
        total_size = sum(path.stat().st_size for path in other_csvs)
    except OSError:
        print("[detector-lab] CSV artifact could not be inspected")
        return False
    if len(other_csvs) >= MAX_CSV_FILES:
        print("[detector-lab] CSV artifact omitted: file count limit exceeded")
        return False
    if total_size + len(serialized) > MAX_CSV_TOTAL_BYTES:
        print("[detector-lab] CSV artifact omitted: total size limit exceeded")
        return False

    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(serialized)
    except OSError:
        print("[detector-lab] CSV artifact could not be persisted")
        return False
    return True


def emit_failure_diagnostic(
    context: DetectorLabDiagnosticContext,
    rows: Sequence[Mapping[str, object]],
) -> None:
    """Print and optionally persist the safe detector-lab failure projection."""
    diagnostic = build_failure_diagnostic(context, rows)
    serialized = json.dumps(diagnostic, sort_keys=True)
    if len(serialized.encode()) > MAX_DIAGNOSTIC_BYTES:
        print("[detector-lab] failure diagnostic omitted: size limit exceeded")
        return
    print(f"[detector-lab] failure diagnostics: {serialized}")
    _persist_failure_diagnostic(context, diagnostic)


def emit_failure_diagnostic_safely(
    context: DetectorLabDiagnosticContext,
    rows: Sequence[Mapping[str, object]],
) -> None:
    """Keep best-effort diagnostics from replacing the original test failure."""
    try:
        emit_failure_diagnostic(context, rows)
    except Exception:
        print("[detector-lab] failure diagnostic could not be generated")


@contextmanager
def emit_failure_diagnostic_on_error(
    context: DetectorLabDiagnosticContext,
    rows: Sequence[Mapping[str, object]],
) -> Generator[None, None, None]:
    """Emit best-effort evidence while preserving the original test failure."""
    try:
        yield
    except Exception:
        emit_failure_diagnostic_safely(context, rows)
        raise
