"""Shared support for representative media session tests.

The helpers in this module keep the representative test suites on one compact
fixture model:

- the manifest owns MP4/HLS identity and source relationships
- expectations stay broad intent while ground-truth cases own reviewed exact output
- tests run reviewed subsets instead of replaying full fixtures by default
- `video_segments`, `api_stream`, and reviewed `video_files` lanes reuse the
  same subset descriptors
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from functools import lru_cache
from pathlib import Path
import shutil

import pytest

from analyzer_contract import AnalysisSlice
import session_runner as session_runner_module
from session_io import read_session_snapshot
from session_runner import run_local_session
from stream_loader import build_api_stream_temp_session_dir
from tests.e2e_session_test_support import (
    configure_session_output,
    install_isolated_csv_stores,
    load_ground_truth_cases,
    run_and_read_local_session,
)
from tests.local_hls_test_support import _serve_local_hls
from tests.session_runner_api_stream_test_support import _configure_http_hls_runner_test


REPRESENTATIVE_MEDIA_DIR = Path(__file__).parent / "fixtures" / "media" / "representative"
REPRESENTATIVE_LOCAL_FILES_DIR = REPRESENTATIVE_MEDIA_DIR / "local_files"
REPRESENTATIVE_MANIFEST_PATH = REPRESENTATIVE_MEDIA_DIR / "manifest.json"
REPRESENTATIVE_EXPECTATIONS_PATH = REPRESENTATIVE_MEDIA_DIR / "expected_results.json"


@dataclass(frozen=True, slots=True)
class RepresentativeHlsSubset:
    """One reviewed HLS subset cut from a larger representative fixture."""

    fixture_id: str
    subset_name: str
    segment_indices: tuple[int, ...]

    @property
    def segment_count(self) -> int:
        return len(self.segment_indices)

    @property
    def expected_source_names(self) -> list[str]:
        """Return playlist-ordered source names expected in persisted results."""
        return [f"segment_{segment_index:04d}.ts" for segment_index in self.segment_indices]


@dataclass(frozen=True, slots=True)
class RepresentativeVideoFileSubset:
    """One reviewed window subset taken from a larger representative MP4."""

    fixture_id: str
    subset_name: str
    window_indices: tuple[int, ...]

    @property
    def window_count(self) -> int:
        return len(self.window_indices)

    @property
    def fixture_path(self) -> Path:
        return representative_local_file_path(self.fixture_id)

    @property
    def expected_source_names(self) -> list[str]:
        """Return runtime-style source names for the reviewed windows."""
        file_name = self.fixture_path.name
        return [
            f"{file_name} @ {window_index // 60:02d}:{window_index % 60:02d}"
            for window_index in self.window_indices
        ]


@lru_cache(maxsize=1)
def _load_representative_manifest() -> dict[str, object]:
    """Load the representative media catalog once per test process."""
    return json.loads(REPRESENTATIVE_MANIFEST_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_representative_expectations() -> dict[str, object]:
    """Load the representative expectation catalog once per test process."""
    return json.loads(REPRESENTATIVE_EXPECTATIONS_PATH.read_text(encoding="utf-8"))


def representative_mp4_manifest_fixture(fixture_id: str) -> dict[str, object]:
    """Return one source or derived MP4 fixture from the canonical manifest."""
    manifest = _load_representative_manifest()
    for fixture_group in ("source_fixtures", "derived_fixtures"):
        for fixture in manifest[fixture_group]:
            if fixture["id"] == fixture_id:
                return fixture
    raise KeyError(f"No representative MP4 fixture is cataloged for {fixture_id!r}")


def representative_hls_manifest_fixture(fixture_id: str) -> dict[str, object]:
    """Return one derived HLS fixture from the canonical manifest."""
    for fixture in _load_representative_manifest()["local_hls_fixtures"]:
        if fixture["id"] == fixture_id:
            return fixture
    raise KeyError(f"No representative local HLS fixture is cataloged for {fixture_id!r}")


def representative_hls_manifest_fixture_for_expected_case(
    expected_case_id: str,
) -> dict[str, object]:
    """Resolve one HLS expectation row to its canonical manifest fixture."""
    suffix = "_hls"
    if not expected_case_id.endswith(suffix):
        raise ValueError(f"Representative expectation is not an HLS case: {expected_case_id!r}")
    return representative_hls_manifest_fixture(expected_case_id[: -len(suffix)])


def representative_mp4_manifest_fixture_for_hls(hls_fixture_id: str) -> dict[str, object]:
    """Resolve an HLS export to its source or matching derived MP4 fixture."""
    hls_fixture = representative_hls_manifest_fixture(hls_fixture_id)
    try:
        return representative_mp4_manifest_fixture(hls_fixture_id)
    except KeyError:
        return representative_mp4_manifest_fixture(hls_fixture["source_id"])


def representative_hls_fixture_dir(fixture_id: str) -> Path:
    """Resolve one cataloged HLS fixture directory through the canonical manifest."""
    fixture = representative_hls_manifest_fixture(fixture_id)
    return REPRESENTATIVE_MEDIA_DIR / fixture["path"]


def representative_local_file_path(fixture_id: str) -> Path:
    """Resolve one cataloged MP4 path through the canonical manifest."""
    return REPRESENTATIVE_MEDIA_DIR / representative_mp4_manifest_fixture(fixture_id)["path"]


def representative_hls_fixture_dir_from_mp4_fixture(mp4_fixture_id: str) -> Path:
    """Resolve the sibling HLS export for one representative MP4 fixture id."""
    hls_fixture = representative_hls_manifest_fixture(mp4_fixture_id)
    mp4_fixture = representative_mp4_manifest_fixture_for_hls(mp4_fixture_id)
    if hls_fixture["source_mp4_path"] != mp4_fixture["path"]:
        raise ValueError(
            f"Representative HLS fixture {mp4_fixture_id!r} does not reference its "
            "cataloged MP4 path"
        )
    return representative_hls_fixture_dir(mp4_fixture_id)


def read_representative_local_hls_fixture(fixture_id: str) -> dict[str, object]:
    """Read one representative HLS fixture into a small filesystem summary."""
    fixture_dir = representative_hls_fixture_dir(fixture_id)
    playlist_path = fixture_dir / "index.m3u8"
    if not playlist_path.exists():
        raise FileNotFoundError(f"Missing representative local HLS playlist: {playlist_path}")

    segment_paths = sorted(fixture_dir.glob("segment_*.ts"))
    playlist_text = playlist_path.read_text(encoding="utf-8")
    return {
        "fixture_id": fixture_id,
        "fixture_dir": fixture_dir,
        "playlist_path": playlist_path,
        "playlist_text": playlist_text,
        "segment_paths": segment_paths,
        "segment_names": [segment_path.name for segment_path in segment_paths],
        "segment_count": len(segment_paths),
    }


def representative_expected_case(case_id: str) -> dict[str, object]:
    """Return one representative broad-intent entry by id."""
    cases = _load_representative_expectations()["cases"]
    for case in cases:
        if case["id"] == case_id:
            return case
    raise KeyError(f"Representative expectation case is not defined: {case_id!r}")


def representative_hls_ground_truth_cases() -> list[dict[str, object]]:
    """Return reviewed representative HLS exact-runtime cases."""
    return load_ground_truth_cases("representative_local_hls_cases")


def representative_video_file_ground_truth_cases() -> list[dict[str, object]]:
    """Return reviewed representative MP4 exact-runtime cases."""
    return load_ground_truth_cases("representative_local_video_file_cases")


def assert_representative_hls_expectation_matches_mp4(mp4_fixture_id: str) -> None:
    """Assert that the derived HLS case preserves the source MP4 intent contract."""
    mp4_case = representative_expected_case(mp4_fixture_id)
    hls_case = representative_expected_case(f"{mp4_fixture_id}_hls")
    hls_fixture = representative_hls_manifest_fixture_for_expected_case(hls_case["id"])
    mp4_fixture = representative_mp4_manifest_fixture_for_hls(hls_fixture["id"])

    assert hls_fixture["source_mp4_path"] == mp4_fixture["path"]
    assert hls_case["expected"] == mp4_case["expected"]
    assert hls_case["assertion_tier"] == mp4_case["assertion_tier"]


def require_representative_local_hls(*fixture_ids: str) -> None:
    """Skip for missing cataloged local HLS assets; unknown IDs remain errors."""
    missing = [
        fixture_id
        for fixture_id in fixture_ids
        if not (representative_hls_fixture_dir(fixture_id) / "index.m3u8").exists()
    ]
    if missing:
        pytest.skip(
            "Representative local HLS fixture(s) are not available: "
            + ", ".join(sorted(missing))
        )


def require_representative_local_files(*fixture_ids: str) -> None:
    """Skip for missing cataloged local MP4 assets; unknown IDs remain errors."""
    missing = [
        fixture_id
        for fixture_id in fixture_ids
        if not representative_local_file_path(fixture_id).exists()
    ]
    if missing:
        pytest.skip(
            "Representative local MP4 fixture(s) are not available: "
            + ", ".join(sorted(missing))
        )


def representative_hls_subset(
    *,
    fixture_id: str,
    subset_name: str,
    segment_indices: Sequence[int],
) -> RepresentativeHlsSubset:
    """Build one validated representative HLS segment subset."""
    fixture_id, subset_name, indices = _validated_subset_fields(
        fixture_id=fixture_id,
        subset_name=subset_name,
        indices=segment_indices,
        index_label="segment",
    )
    return RepresentativeHlsSubset(
        fixture_id=fixture_id,
        subset_name=subset_name,
        segment_indices=indices,
    )


def representative_video_file_subset(
    *,
    fixture_id: str,
    subset_name: str,
    window_indices: Sequence[int],
) -> RepresentativeVideoFileSubset:
    """Build one validated representative MP4 detector-window subset."""
    fixture_id, subset_name, indices = _validated_subset_fields(
        fixture_id=fixture_id,
        subset_name=subset_name,
        indices=window_indices,
        index_label="window",
    )
    return RepresentativeVideoFileSubset(
        fixture_id=fixture_id,
        subset_name=subset_name,
        window_indices=indices,
    )


def _validated_subset_fields(
    *,
    fixture_id: str,
    subset_name: str,
    indices: Sequence[int],
    index_label: str,
) -> tuple[str, str, tuple[int, ...]]:
    """Validate the identity and ordered transport-specific indices of a subset."""
    if not fixture_id.strip() or not subset_name.strip():
        raise ValueError("Representative subset requires nonblank fixture_id and subset_name")

    normalized_indices = tuple(indices)
    if not normalized_indices or any(
        not isinstance(index, int) or isinstance(index, bool)
        for index in normalized_indices
    ):
        raise ValueError(
            f"Representative {index_label} subset requires one or more integer indices"
        )
    if normalized_indices != tuple(sorted(set(normalized_indices))) or normalized_indices[0] < 0:
        raise ValueError(
            f"Representative {index_label} subset indices must be nonnegative, unique, and ascending"
        )

    return fixture_id, subset_name, normalized_indices


def build_playlist_subset(
    tmp_path: Path,
    *,
    fixture_id: str,
    subset_name: str,
    segment_indices: list[int],
) -> Path:
    """Materialize a reviewed playlist subset from a larger HLS fixture.

    The folder-based `video_segments` seam only needs playlist order plus the
    referenced `.ts` files. Copying the reviewed subset keeps test cost down
    while preserving the real processing path.
    """
    subset = representative_hls_subset(
        fixture_id=fixture_id,
        subset_name=subset_name,
        segment_indices=segment_indices,
    )
    require_representative_local_hls(subset.fixture_id)

    source_dir = representative_hls_fixture_dir(subset.fixture_id)
    subset_dir = tmp_path / subset.subset_name
    subset_dir.mkdir(parents=True, exist_ok=True)

    playlist_lines = ["#EXTM3U"]
    for segment_index in subset.segment_indices:
        source_name = f"segment_{segment_index:04d}.ts"
        source_path = source_dir / source_name
        if not source_path.exists():
            raise FileNotFoundError(
                f"Representative HLS segment is missing: {source_path}"
            )
        shutil.copy2(source_path, subset_dir / source_name)
        playlist_lines.extend(["#EXTINF:2.0,", source_name])

    playlist_lines.append("#EXT-X-ENDLIST")
    (subset_dir / "index.m3u8").write_text(
        "\n".join(playlist_lines),
        encoding="utf-8",
    )
    return subset_dir


def build_playlist_subset_from_descriptor(
    tmp_path: Path,
    *,
    subset: RepresentativeHlsSubset,
) -> Path:
    """Build a playlist subset from a normalized HLS subset descriptor."""
    return build_playlist_subset(
        tmp_path,
        fixture_id=subset.fixture_id,
        subset_name=subset.subset_name,
        segment_indices=list(subset.segment_indices),
    )


def representative_hls_subset_from_ground_truth_fixture(
    fixture: Mapping[str, object],
) -> RepresentativeHlsSubset:
    """Parse one representative HLS subset from ground-truth fixture metadata."""
    if fixture.get("kind") != "representative_local_hls_subset":
        raise ValueError(
            "Unsupported representative HLS ground-truth fixture kind: "
            f"{fixture.get('kind')!r}"
        )

    fixture_id = fixture.get("fixture_id")
    subset_name = fixture.get("subset_name")
    segment_indices = fixture.get("segment_indices")
    if not isinstance(fixture_id, str) or not isinstance(subset_name, str):
        raise ValueError("Representative HLS ground-truth fixture is missing fixture metadata")
    if not isinstance(segment_indices, list) or not all(
        isinstance(index, int) and not isinstance(index, bool) for index in segment_indices
    ):
        raise ValueError(
            "Representative HLS ground-truth fixture must define integer segment indices"
        )

    subset = representative_hls_subset(
        fixture_id=fixture_id,
        subset_name=subset_name,
        segment_indices=segment_indices,
    )
    representative_hls_manifest_fixture(subset.fixture_id)
    representative_mp4_manifest_fixture_for_hls(subset.fixture_id)
    return subset


def representative_video_file_subset_from_ground_truth_fixture(
    fixture: Mapping[str, object],
) -> RepresentativeVideoFileSubset:
    """Parse one representative MP4 subset from ground-truth fixture metadata."""
    if fixture.get("kind") != "representative_local_video_file_subset":
        raise ValueError(
            "Unsupported representative video-file ground-truth fixture kind: "
            f"{fixture.get('kind')!r}"
        )

    fixture_id = fixture.get("fixture_id")
    subset_name = fixture.get("subset_name")
    window_indices = fixture.get("window_indices")
    if not isinstance(fixture_id, str) or not isinstance(subset_name, str):
        raise ValueError("Representative video-file ground-truth fixture is missing metadata")
    if not isinstance(window_indices, list) or not all(
        isinstance(index, int) and not isinstance(index, bool) for index in window_indices
    ):
        raise ValueError(
            "Representative video-file ground-truth fixture must define integer window indices"
        )

    subset = representative_video_file_subset(
        fixture_id=fixture_id,
        subset_name=subset_name,
        window_indices=window_indices,
    )
    representative_mp4_manifest_fixture(subset.fixture_id)
    return subset


def build_playlist_subset_from_ground_truth_fixture(
    tmp_path: Path,
    *,
    fixture: dict[str, object],
) -> Path:
    """Build a reviewed HLS playlist subset from a ground-truth fixture descriptor."""
    return build_playlist_subset_from_descriptor(
        tmp_path,
        subset=representative_hls_subset_from_ground_truth_fixture(fixture),
    )


def run_video_segments_subset_session(
    monkeypatch,
    tmp_path: Path,
    *,
    subset: RepresentativeHlsSubset,
    selected_detectors: list[str],
) -> tuple[object, dict[str, object]]:
    """Run one reviewed HLS subset through the real `video_segments` seam."""
    configure_session_output(monkeypatch, tmp_path)
    install_isolated_csv_stores(monkeypatch, tmp_path)
    input_path = build_playlist_subset_from_descriptor(tmp_path, subset=subset)
    return run_and_read_local_session(
        mode="video_segments",
        input_path=input_path,
        selected_detectors=selected_detectors,
        session_id=f"representative-video-segments-{subset.subset_name}",
    )


def run_video_files_subset_session(
    monkeypatch,
    tmp_path: Path,
    *,
    subset: RepresentativeVideoFileSubset,
    selected_detectors: list[str],
) -> tuple[object, dict[str, object]]:
    """Run one reviewed MP4 subset through the real `video_files` seam.

    The representative MP4 fixtures can be much larger than the reviewed
    artifact windows we currently trust. Patching slice discovery keeps this
    lane focused on those windows while still exercising the real session path
    end to end.
    """
    configure_session_output(monkeypatch, tmp_path)
    install_isolated_csv_stores(monkeypatch, tmp_path)
    require_representative_local_files(subset.fixture_id)
    input_path = subset.fixture_path

    def _discover_reviewed_windows(mode, discovered_input_path, session_id=None):
        """Replace default slice discovery with the reviewed subset only."""
        _ = session_id
        assert mode == "video_files"
        assert Path(discovered_input_path) == input_path
        return [
            AnalysisSlice(
                file_path=input_path,
                source_group=input_path.name,
                source_name=source_name,
                window_index=window_index,
                window_start_sec=float(window_index),
                window_duration_sec=1.0,
            )
            for window_index, source_name in zip(
                subset.window_indices,
                subset.expected_source_names,
                strict=True,
            )
        ]

    monkeypatch.setattr(
        session_runner_module,
        "discover_input_slices",
        _discover_reviewed_windows,
    )
    return run_and_read_local_session(
        mode="video_files",
        input_path=input_path,
        selected_detectors=selected_detectors,
        session_id=f"representative-video-files-{subset.subset_name}",
    )


def run_api_stream_subset_session(
    monkeypatch,
    tmp_path: Path,
    *,
    subset: RepresentativeHlsSubset,
    selected_detectors: list[str],
) -> tuple[object, dict[str, object]]:
    """Run one reviewed HLS subset through the real `api_stream` seam."""
    session_id = f"representative-api-stream-{subset.subset_name}"
    _configure_http_hls_runner_test(
        monkeypatch,
        tmp_path,
        session_id=session_id,
    )
    install_isolated_csv_stores(monkeypatch, tmp_path)
    playlist_dir = build_playlist_subset_from_descriptor(tmp_path, subset=subset)
    routes = build_local_hls_routes(playlist_dir)

    with _serve_local_hls(routes) as base_url:
        metadata = run_local_session(
            mode="api_stream",
            input_path=f"{base_url}/live/index.m3u8",
            selected_detectors=selected_detectors,
            session_id=session_id,
        )

    snapshot = read_session_snapshot(metadata.session_id)
    return metadata, snapshot


def assert_api_stream_temp_dir_cleaned(session_id: str) -> None:
    """Assert that a completed `api_stream` run leaves no temp media behind."""
    temp_dir = build_api_stream_temp_session_dir(session_id)
    if not temp_dir.exists():
        return
    assert not any(temp_dir.iterdir())


def build_local_hls_routes(
    playlist_dir: Path,
    *,
    prefix: str = "/live",
) -> dict[str, tuple[int, str | bytes, str]]:
    """Build static HTTP routes for one local HLS playlist folder.

    The representative `api_stream` suites use this to exercise the real
    loader seam without introducing a second fixture-server abstraction.
    """
    playlist_path = playlist_dir / "index.m3u8"
    if not playlist_path.exists():
        raise FileNotFoundError(f"Missing local HLS playlist: {playlist_path}")

    routes: dict[str, tuple[int, str | bytes, str]] = {
        f"{prefix}/index.m3u8": (
            200,
            playlist_path.read_text(encoding="utf-8"),
            "application/vnd.apple.mpegurl",
        )
    }
    for segment_path in sorted(playlist_dir.glob("segment_*.ts")):
        routes[f"{prefix}/{segment_path.name}"] = (
            200,
            segment_path.read_bytes(),
            "video/mp2t",
        )
    return routes


def range_indices(start: int, end_inclusive: int) -> list[int]:
    """Return an inclusive integer range as a list."""
    return list(range(start, end_inclusive + 1))


def merge_index_groups(*groups: list[int]) -> list[int]:
    """Merge multiple index groups into one sorted unique list."""
    return sorted({index for group in groups for index in group})


def detector_payloads(
    snapshot: dict[str, object],
    detector_id: str,
) -> list[dict[str, object]]:
    """Return persisted result payloads for one detector."""
    return [
        event["payload"]
        for event in snapshot["results"]
        if event["detector_id"] == detector_id
    ]


def detector_alerts(
    snapshot: dict[str, object],
    detector_id: str,
) -> list[dict[str, object]]:
    """Return persisted alerts for one detector."""
    return [
        alert
        for alert in snapshot["alerts"]
        if alert["detector_id"] == detector_id
    ]
