"""Command-line entrypoint for detector-lab evaluations."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
_VIDEO_FILE_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "media" / "video_files"
_NORMAL_BASELINE_CLIP_DIR = (
    REPO_ROOT / "tests" / "fixtures" / "media" / "election_clips" / "normal_baseline"
)
_FIXTURE_CATALOG_FILE = REPO_ROOT / "tests" / "fixtures" / "media" / "fixture_catalog.json"


def ensure_src_on_path() -> None:
    """Make direct ``python -m detector_lab.cli`` runs work from the repo root."""
    src_root = REPO_ROOT / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))


def build_parser() -> argparse.ArgumentParser:
    """Build the detector-lab CLI argument parser."""
    ensure_src_on_path()
    from detector_lab.algorithms import list_algorithm_ids

    parser = argparse.ArgumentParser(
        description="Evaluate detector/rule algorithms on local media and write CSV metrics.",
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--input", type=Path, help="Local media file or folder.")
    input_group.add_argument(
        "--fixture-set",
        choices=("test_video_files", "normal_baseline_video_files", "all_video_files"),
        default=None,
        help="Run one built-in detector-lab fixture set instead of a single input.",
    )
    parser.add_argument(
        "--mode",
        choices=("video_files", "video_segments"),
        default="video_files",
        help="Input mode used for production-compatible slice discovery.",
    )
    algorithm_group = parser.add_mutually_exclusive_group()
    algorithm_group.add_argument(
        "--algorithms",
        nargs="+",
        choices=list_algorithm_ids(),
        default=None,
        help="Algorithm ids to evaluate. Defaults to all production baseline algorithms.",
    )
    algorithm_group.add_argument(
        "--detectors",
        nargs="+",
        choices=("video_blur", "video_metrics"),
        default=None,
        help="Shortcut for production algorithms by detector id. Do not combine with --algorithms.",
    )
    algorithm_group.add_argument(
        "--all-algorithms",
        action="store_true",
        help="Run all registered detector-lab algorithms instead of the production baseline defaults.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("detector_lab/output/eval.csv"),
        help="CSV output path.",
    )
    parser.add_argument(
        "--start-window",
        type=int,
        default=0,
        help="Optional zero-based window index to start from.",
    )
    parser.add_argument(
        "--max-windows",
        type=int,
        default=None,
        help="Optional limit for large videos or long segment folders.",
    )
    parser.add_argument(
        "--split-output",
        action="store_true",
        help="When used with --fixture-set, write one CSV per input clip.",
    )
    return parser


def main() -> int:
    """Run the requested detector-lab evaluation and report what was written."""
    ensure_src_on_path()
    from detector_lab.algorithms import (
        DEFAULT_ALGORITHM_IDS,
        algorithm_ids_for_detectors,
        list_algorithm_ids,
        resolve_algorithm_specs,
    )
    from detector_lab.runner import (
        DetectorLabBatchConfig,
        DetectorLabSplitBatchConfig,
        DetectorLabConfig,
        run_detector_lab,
        run_detector_lab_batch,
        run_detector_lab_batch_split,
    )
    from detector_lab.reporting import count_rows_for_output_profile

    args = build_parser().parse_args()
    algorithm_ids = _resolve_algorithm_ids(
        configured_algorithm_ids=args.algorithms,
        detector_ids=args.detectors,
        include_all_algorithms=args.all_algorithms,
        default_algorithm_ids=DEFAULT_ALGORITHM_IDS,
        algorithm_ids_for_detectors=algorithm_ids_for_detectors,
        all_algorithm_ids=list_algorithm_ids(),
    )

    if args.fixture_set is not None:
        input_paths = _resolve_fixture_set_paths(args.fixture_set)
        _validate_fixture_set_mode(args.fixture_set, args.mode)
        output_profile = _resolve_fixture_set_output_profile(
            algorithm_ids=algorithm_ids,
            resolve_algorithm_specs=resolve_algorithm_specs,
        )
        if args.split_output:
            output_dir = _resolve_split_output_dir(args.output, fixture_set=args.fixture_set)
            outputs = run_detector_lab_batch_split(
                DetectorLabSplitBatchConfig(
                    input_paths=input_paths,
                    mode=args.mode,
                    output_dir=output_dir,
                    algorithm_ids=tuple(algorithm_ids),
                    start_window=args.start_window,
                    max_windows=args.max_windows,
                    output_profile=output_profile,
                )
            )
            print(
                f"Wrote {len(outputs)} split detector evaluation files for {len(input_paths)} inputs to {output_dir}"
            )
            return 0
        rows = run_detector_lab_batch(
            DetectorLabBatchConfig(
                input_paths=input_paths,
                mode=args.mode,
                output_csv=args.output,
                algorithm_ids=tuple(algorithm_ids),
                start_window=args.start_window,
                max_windows=args.max_windows,
                output_profile=output_profile,
            )
        )
        written_row_count = count_rows_for_output_profile(
            rows,
            output_profile=output_profile,
        )
        print(
            f"Wrote {written_row_count} merged detector evaluation rows for {len(input_paths)} inputs to {args.output}"
        )
        return 0

    rows = run_detector_lab(
        DetectorLabConfig(
            input_path=args.input,
            mode=args.mode,
            output_csv=args.output,
            algorithm_ids=tuple(algorithm_ids),
            start_window=args.start_window,
            max_windows=args.max_windows,
        )
    )
    print(f"Wrote {len(rows)} detector evaluation rows to {args.output}")
    return 0


def _resolve_algorithm_ids(
    *,
    configured_algorithm_ids: list[str] | None,
    detector_ids: list[str] | None,
    include_all_algorithms: bool,
    default_algorithm_ids: tuple[str, ...],
    algorithm_ids_for_detectors: Callable[[tuple[str, ...]], tuple[str, ...]],
    all_algorithm_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """Resolve algorithm ids after CLI shortcut expansion."""
    if include_all_algorithms:
        return all_algorithm_ids
    if detector_ids is not None:
        return algorithm_ids_for_detectors(tuple(detector_ids))
    if configured_algorithm_ids is not None:
        return tuple(configured_algorithm_ids)
    return default_algorithm_ids


def _resolve_fixture_set_output_profile(
    *,
    algorithm_ids: tuple[str, ...],
    resolve_algorithm_specs: Callable[[tuple[str, ...]], tuple[object, ...]],
) -> str:
    """Choose the safe fixture-set export profile for the selected algorithms.

    Compact merged fixture exports only work when there is at most one algorithm
    per detector id and every algorithm maps to the production blur/black pair.
    If detector ids repeat or custom detector ids are present, keep the full
    export so rows do not overwrite one another or disappear from compact merges.
    """
    specs = resolve_algorithm_specs(algorithm_ids)
    detector_counts = Counter(getattr(spec, "detector_id") for spec in specs)
    if any(count > 1 for count in detector_counts.values()):
        return "full"
    if any(
        getattr(spec, "detector_id") not in {"video_blur", "video_metrics"}
        for spec in specs
    ):
        return "full"
    return "production_fixture_compact"


def _resolve_fixture_set_paths(fixture_set: str) -> tuple[Path, ...]:
    """Return the concrete input paths for one built-in detector-lab fixture set."""
    if fixture_set == "test_video_files":
        valid_catalog_paths = _load_valid_catalog_video_file_paths()
        legacy_short_paths = (
            _VIDEO_FILE_FIXTURE_DIR / "black_trigger.mp4",
            _VIDEO_FILE_FIXTURE_DIR / "blur_trigger.mp4",
        )
        resolved_paths = [
            path
            for path in (*valid_catalog_paths, *legacy_short_paths)
            if path.exists()
        ]
        return tuple(sorted(dict.fromkeys(resolved_paths)))
    if fixture_set == "normal_baseline_video_files":
        return tuple(sorted(_NORMAL_BASELINE_CLIP_DIR.glob("*.mp4")))
    if fixture_set == "all_video_files":
        return tuple(
            sorted(
                dict.fromkeys(
                    (
                        *_resolve_fixture_set_paths("test_video_files"),
                        *_resolve_fixture_set_paths("normal_baseline_video_files"),
                    )
                )
            )
        )
    raise ValueError(f"Unknown detector-lab fixture set: {fixture_set}")


def _validate_fixture_set_mode(fixture_set: str, mode: str) -> None:
    """Reject incompatible mode and fixture-set combinations early."""
    if fixture_set in {"test_video_files", "normal_baseline_video_files", "all_video_files"} and mode != "video_files":
        raise ValueError(f"Fixture set '{fixture_set}' requires --mode video_files")


def _resolve_split_output_dir(output_path: Path, *, fixture_set: str) -> Path:
    """Return the directory used for one-per-input fixture-set CSV outputs."""
    if output_path.suffix.lower() == ".csv":
        return output_path.parent / f"{output_path.stem}_{fixture_set}"
    return output_path


def _load_valid_catalog_video_file_paths() -> tuple[Path, ...]:
    """Return checked-in MP4 fixture paths marked as valid in the fixture catalog."""
    if not _FIXTURE_CATALOG_FILE.exists():
        return tuple()

    payload = json.loads(_FIXTURE_CATALOG_FILE.read_text(encoding="utf-8"))
    rows = payload.get("video_files", [])
    if not isinstance(rows, list):
        return tuple()

    paths: list[Path] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("validity") != "valid":
            continue
        fixture_path = row.get("path")
        if not isinstance(fixture_path, str):
            continue
        paths.append(REPO_ROOT / "tests" / "fixtures" / "media" / fixture_path)
    return tuple(paths)


if __name__ == "__main__":
    raise SystemExit(main())
