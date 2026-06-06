"""CSV export shaping for detector-lab evaluation rows.

The detector lab deliberately keeps reporting separate from execution. This
module owns the flat CSV contract, ground-truth summary lookup, and the compact
fixture-oriented export profile used for quick visual review.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from detector_lab.contracts import (
    DetectorMetricRow,
    LabAlgorithmSpec,
    LabEvaluationOutputProfile,
    LabEvaluationRow,
    field_names_for_output_profile,
    normalize_input_path,
)
from session_models import AlertEvent


_GROUND_TRUTH_FILE = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "media"
    / "ground_truth.json"
)
_VIDEO_FILE_SECOND_LABELS_FILE = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "media"
    / "video_file_second_labels.json"
)
_MEDIA_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "media"
)
_GROUND_TRUTH_CACHE_FILE = (
    Path(__file__).resolve().parents[1]
    / "detector_lab"
    / "output"
    / "ground_truth_stream_cache.json"
)
_GROUND_TRUTH_SUMMARY_SCHEMA_VERSION = "ground_truth_summary_v4"
_SECOND_LABEL_LEGEND = "0=normal,1=black,2=blur,3=motion_blur,9=unknown"
_DETECTOR_ROW_EXPORT_FIELDS: tuple[str, ...] = (
    "source_group",
    "source_name",
    "window_index",
    "window_start_sec",
    "window_duration_sec",
    "sample_count",
    "sharpness_p10",
    "sharpness_p90",
    "motion_mean",
    "motion_p90",
    "absolute_blur",
    "dynamic_blur",
    "edge_density",
    "mean_edge_strength",
    "texture_energy",
    "structure_strength",
    "medium_scale_edge_density",
    "coarse_scale_edge_density",
    "medium_scale_texture_energy",
    "coarse_scale_texture_energy",
    "edge_persistence",
    "texture_retention",
    "multiscale_structure_strength",
    "motion_blur_method",
    "optical_flow_mean",
    "optical_flow_p90",
    "optical_flow_coherence",
    "fine_scale_motion_energy",
    "medium_scale_motion_energy",
    "coarse_scale_motion_energy",
    "motion_persistence",
    "motion_coherence",
    "motion_incoherence_penalty",
    "blur_blend_id",
    "blur_score",
    "blur_detected",
    "threshold_used",
    "black_detected",
    "black_segment_count",
    "total_black_sec",
    "longest_black_sec",
    "black_ratio",
    "processing_sec",
    "practical_score",
    "practical_threshold",
    "practical_detected",
    "guardrail_reason",
)


def _load_video_file_second_labels() -> dict[str, list[int]]:
    """Load per-second labels for checked-in video-file fixtures."""
    if not _VIDEO_FILE_SECOND_LABELS_FILE.exists():
        return {}

    payload = json.loads(_VIDEO_FILE_SECOND_LABELS_FILE.read_text(encoding="utf-8"))
    rows = payload.get("video_files", [])
    if not isinstance(rows, list):
        return {}

    labels_by_path: dict[str, list[int]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        fixture_path = row.get("path")
        labels = row.get("labels_by_second")
        if not fixture_path or not isinstance(labels, list):
            continue
        labels_by_path[str(fixture_path)] = [int(label) for label in labels]
    return labels_by_path


def _build_label_only_summary(second_labels: list[int]) -> str:
    """Serialize a compact summary for fixtures that only have per-second labels."""
    payload = {
        "per_second_label_legend": _SECOND_LABEL_LEGEND,
        "per_second_labels": ",".join(str(label) for label in second_labels),
    }
    return json.dumps(payload, separators=(",", ":"))


def _load_ground_truth_rows() -> dict[str, str]:
    """Load compact ground-truth summaries keyed by fixture-relative path."""
    second_labels_by_fixture = _load_video_file_second_labels()
    summaries: dict[str, str] = {
        fixture_path: _build_label_only_summary(second_labels)
        for fixture_path, second_labels in second_labels_by_fixture.items()
    }

    if not _GROUND_TRUTH_FILE.exists():
        return summaries

    data = json.loads(_GROUND_TRUTH_FILE.read_text(encoding="utf-8"))
    for case in data.get("local_session_cases", []):
        fixture = case.get("fixture", {})
        fixture_path = fixture.get("path")
        ground_truth = case.get("ground_truth", {})
        if not fixture_path or not isinstance(ground_truth, dict):
            continue
        payload = {
            "case_id": case.get("id", ""),
            "expected_alert_count": ground_truth.get("alert_count", ""),
            "expected_blur_true_count": (
                ground_truth.get("detector_true_counts", {}).get("video_blur", "")
            ),
            "expected_black_true_count": (
                ground_truth.get("detector_true_counts", {}).get("video_metrics", "")
            ),
            "expected_alert_detectors": [
                alert.get("detector_id", "")
                for alert in ground_truth.get("alerts", [])
            ],
        }
        second_labels = second_labels_by_fixture.get(str(fixture_path))
        if second_labels is not None:
            payload["per_second_label_legend"] = _SECOND_LABEL_LEGEND
            payload["per_second_labels"] = ",".join(str(label) for label in second_labels)
        summaries[str(fixture_path)] = json.dumps(payload, separators=(",", ":"))
    return summaries


GROUND_TRUTH_BY_FIXTURE = _load_ground_truth_rows()


def build_ground_truth_lookup(
    input_paths: Iterable[Path],
    *,
    cache_path: Path = _GROUND_TRUTH_CACHE_FILE,
) -> dict[str, str]:
    """Return cached ground-truth summaries for the requested input paths."""
    normalized_inputs = {
        normalize_input_path(input_path): input_path for input_path in input_paths
    }
    cached_rows = _load_ground_truth_cache(cache_path)
    updated = False

    for normalized_path, input_path in normalized_inputs.items():
        if normalized_path in cached_rows:
            continue
        cached_rows[normalized_path] = _resolve_ground_truth_summary(input_path)
        updated = True

    if updated:
        _write_ground_truth_cache(cache_path, cached_rows)

    return {
        normalized_path: cached_rows.get(normalized_path, "")
        for normalized_path in normalized_inputs
    }


def write_eval_csv(
    output_csv: Path,
    rows: list[LabEvaluationRow],
    *,
    output_profile: LabEvaluationOutputProfile = "full",
) -> None:
    """Write evaluation rows using the selected detector-lab field order."""
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    field_names = field_names_for_output_profile(output_profile)
    rows_to_write = _rows_for_output_profile(rows, output_profile=output_profile)
    with output_csv.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(
            file_handle,
            fieldnames=field_names,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows_to_write)


def count_rows_for_output_profile(
    rows: list[LabEvaluationRow],
    *,
    output_profile: LabEvaluationOutputProfile,
) -> int:
    """Return how many rows one export profile will actually write."""
    return len(_rows_for_output_profile(rows, output_profile=output_profile))


def build_eval_row(
    *,
    spec: LabAlgorithmSpec,
    input_path: Path,
    ground_truth_summary: str,
    row: DetectorMetricRow,
    alerts: list[AlertEvent],
) -> LabEvaluationRow:
    """Map one detector row plus alerts into the detector-lab export shape."""
    export_row: LabEvaluationRow = {
        "algorithm_id": spec.algorithm_id,
        "detector_id": spec.detector_id,
        "rule_detector_id": spec.rule_detector_id or "",
        "input_path": normalize_input_path(input_path),
        "ground_truth_summary": ground_truth_summary,
        "alert_count": len(alerts),
        "alert_titles": _join_alert_titles(alerts),
        "alert_messages": _join_alert_messages(alerts),
    }
    export_row.update(_copy_detector_row_fields(row))
    return export_row


def _copy_detector_row_fields(row: DetectorMetricRow) -> dict[str, object]:
    """Copy detector-owned export fields, defaulting missing ones to ``""``."""
    return {field_name: row.get(field_name, "") for field_name in _DETECTOR_ROW_EXPORT_FIELDS}


def _rows_for_output_profile(
    rows: list[LabEvaluationRow],
    *,
    output_profile: LabEvaluationOutputProfile,
) -> list[dict[str, object]]:
    """Return rows shaped for the selected export profile."""
    if output_profile == "full":
        return rows
    if output_profile == "production_fixture_compact":
        return _merge_production_fixture_rows(rows)
    raise ValueError(f"Unknown detector-lab output profile: {output_profile}")


def _merge_production_fixture_rows(rows: list[LabEvaluationRow]) -> list[dict[str, object]]:
    """Collapse blur and black rows into one compact row per analyzed window."""
    merged_by_window: dict[tuple[str, object, object], dict[str, object]] = {}
    ordered_window_keys: list[tuple[str, object, object]] = []

    for row in rows:
        window_key = (row["input_path"], row["window_index"], row["source_name"])
        if window_key not in merged_by_window:
            merged_by_window[window_key] = {
                "input_path": row["input_path"],
                "ground_truth_summary": row["ground_truth_summary"],
                "source_name": row["source_name"],
                "window_index": row["window_index"],
                "window_start_sec": row["window_start_sec"],
                "window_duration_sec": row["window_duration_sec"],
                "blur_algorithm_id": "",
                "blur_sample_count": "",
                "blur_sharpness_p10": "",
                "blur_sharpness_p90": "",
                "blur_motion_mean": "",
                "blur_motion_p90": "",
                "blur_absolute_blur": "",
                "blur_dynamic_blur": "",
                "blur_edge_density": "",
                "blur_mean_edge_strength": "",
                "blur_texture_energy": "",
                "blur_structure_strength": "",
                "blur_medium_scale_edge_density": "",
                "blur_coarse_scale_edge_density": "",
                "blur_medium_scale_texture_energy": "",
                "blur_coarse_scale_texture_energy": "",
                "blur_edge_persistence": "",
                "blur_texture_retention": "",
                "blur_multiscale_structure_strength": "",
                "blur_motion_blur_method": "",
                "blur_optical_flow_mean": "",
                "blur_optical_flow_p90": "",
                "blur_optical_flow_coherence": "",
                "blur_fine_scale_motion_energy": "",
                "blur_medium_scale_motion_energy": "",
                "blur_coarse_scale_motion_energy": "",
                "blur_motion_persistence": "",
                "blur_motion_coherence": "",
                "blur_motion_incoherence_penalty": "",
                "blur_blend_id": "",
                "blur_score": "",
                "blur_detected": "",
                "blur_threshold_used": "",
                "blur_alert_count": "",
                "blur_alert_titles": "",
                "blur_processing_sec": "",
                "black_algorithm_id": "",
                "black_detected": "",
                "black_segment_count": "",
                "black_total_sec": "",
                "black_longest_sec": "",
                "black_ratio": "",
                "black_alert_count": "",
                "black_alert_titles": "",
                "black_processing_sec": "",
            }
            ordered_window_keys.append(window_key)

        merged_row = merged_by_window[window_key]
        detector_id = row["detector_id"]
        if detector_id == "video_blur":
            merged_row.update(
                {
                    "blur_algorithm_id": row["algorithm_id"],
                    "blur_sample_count": row["sample_count"],
                    "blur_sharpness_p10": row["sharpness_p10"],
                    "blur_sharpness_p90": row["sharpness_p90"],
                    "blur_motion_mean": row["motion_mean"],
                    "blur_motion_p90": row["motion_p90"],
                    "blur_absolute_blur": row["absolute_blur"],
                    "blur_dynamic_blur": row["dynamic_blur"],
                    "blur_edge_density": row["edge_density"],
                    "blur_mean_edge_strength": row["mean_edge_strength"],
                    "blur_texture_energy": row["texture_energy"],
                    "blur_structure_strength": row["structure_strength"],
                    "blur_medium_scale_edge_density": row["medium_scale_edge_density"],
                    "blur_coarse_scale_edge_density": row["coarse_scale_edge_density"],
                    "blur_medium_scale_texture_energy": row["medium_scale_texture_energy"],
                    "blur_coarse_scale_texture_energy": row["coarse_scale_texture_energy"],
                    "blur_edge_persistence": row["edge_persistence"],
                    "blur_texture_retention": row["texture_retention"],
                    "blur_multiscale_structure_strength": row["multiscale_structure_strength"],
                    "blur_motion_blur_method": row["motion_blur_method"],
                    "blur_optical_flow_mean": row["optical_flow_mean"],
                    "blur_optical_flow_p90": row["optical_flow_p90"],
                    "blur_optical_flow_coherence": row["optical_flow_coherence"],
                    "blur_fine_scale_motion_energy": row["fine_scale_motion_energy"],
                    "blur_medium_scale_motion_energy": row["medium_scale_motion_energy"],
                    "blur_coarse_scale_motion_energy": row["coarse_scale_motion_energy"],
                    "blur_motion_persistence": row["motion_persistence"],
                    "blur_motion_coherence": row["motion_coherence"],
                    "blur_motion_incoherence_penalty": row["motion_incoherence_penalty"],
                    "blur_blend_id": row["blur_blend_id"],
                    "blur_score": row["blur_score"],
                    "blur_detected": row["blur_detected"],
                    "blur_threshold_used": row["threshold_used"],
                    "blur_alert_count": row["alert_count"],
                    "blur_alert_titles": row["alert_titles"],
                    "blur_processing_sec": row["processing_sec"],
                }
            )
        elif detector_id == "video_metrics":
            merged_row.update(
                {
                    "black_algorithm_id": row["algorithm_id"],
                    "black_detected": row["black_detected"],
                    "black_segment_count": row["black_segment_count"],
                    "black_total_sec": row["total_black_sec"],
                    "black_longest_sec": row["longest_black_sec"],
                    "black_ratio": row["black_ratio"],
                    "black_alert_count": row["alert_count"],
                    "black_alert_titles": row["alert_titles"],
                    "black_processing_sec": row["processing_sec"],
                }
            )

    merged_rows: list[dict[str, object]] = []
    for row_index, window_key in enumerate(ordered_window_keys, start=1):
        merged_row = merged_by_window[window_key]
        merged_row["row_index"] = row_index
        merged_rows.append(merged_row)
    return merged_rows


def _join_alert_titles(alerts: list[AlertEvent]) -> str:
    """Join alert titles for one CSV cell."""
    return "; ".join(alert.title for alert in alerts)


def _join_alert_messages(alerts: list[AlertEvent]) -> str:
    """Join alert messages for one CSV cell."""
    return " | ".join(alert.message for alert in alerts)


def _resolve_ground_truth_summary(input_path: Path) -> str:
    """Return the compact ground-truth summary for a known fixture path."""
    try:
        fixture_relative = str(input_path.resolve().relative_to(_MEDIA_FIXTURE_ROOT))
    except ValueError:
        fixture_relative = str(input_path)
        if "tests/fixtures/media/" in fixture_relative:
            fixture_relative = fixture_relative.split("tests/fixtures/media/", 1)[1]
    return GROUND_TRUTH_BY_FIXTURE.get(fixture_relative, "")


def _load_ground_truth_cache(cache_path: Path) -> dict[str, str]:
    """Load the persisted input-path ground-truth lookup, if it exists."""
    if not cache_path.exists():
        return {}

    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    if payload.get("schema_version") != _GROUND_TRUTH_SUMMARY_SCHEMA_VERSION:
        return {}
    summaries = payload.get("summaries")
    if not isinstance(summaries, dict):
        return {}
    return {str(path): str(summary) for path, summary in summaries.items()}


def _write_ground_truth_cache(cache_path: Path, rows: dict[str, str]) -> None:
    """Persist a serialized-input-path to summary mapping."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "schema_version": _GROUND_TRUTH_SUMMARY_SCHEMA_VERSION,
                "summaries": rows,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
