"""Deterministic catalog guards for representative MP4/HLS fixtures.

They validate manifest identity, broad-intent metadata, transport-specific
subset descriptors, and exact-truth references without opening media. Tests
that inspect local HLS exports skip when those optional assets are absent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import pytest

from tests.representative_hls_test_support import (
    REPRESENTATIVE_EXPECTATIONS_PATH,
    REPRESENTATIVE_MANIFEST_PATH,
    assert_representative_hls_expectation_matches_mp4,
    build_local_hls_routes,
    read_representative_local_hls_fixture,
    representative_expected_case,
    representative_hls_fixture_dir_from_mp4_fixture,
    representative_hls_manifest_fixture,
    representative_hls_manifest_fixture_for_expected_case,
    representative_hls_ground_truth_cases,
    representative_hls_subset_from_ground_truth_fixture,
    representative_hls_subset,
    representative_mp4_manifest_fixture,
    representative_mp4_manifest_fixture_for_hls,
    representative_video_file_ground_truth_cases,
    representative_video_file_subset_from_ground_truth_fixture,
    representative_video_file_subset,
    require_representative_local_hls,
)

REPRESENTATIVE_HLS_SEGMENT_COUNTS = (
    ("crowded_ballot__compression_strong_repeated_3x20s", 154),
    ("messy_activity__compression_strong_mid_45s", 151),
    ("crowded_ballot__gblur_strong_mid_20s", 152),
    ("stable_docs__lowres_moderate_start_30s", 1320),
)


@dataclass(frozen=True)
class ConfidenceFixtureExpectation:
    """Manifest/expectation pair used by representative MP4 confidence lanes."""

    fixture_id: str
    expectation_id: str


def _require_local_hls_exports(*fixture_ids: str) -> None:
    """Skip file-backed HLS checks when local representative exports are absent."""
    require_representative_local_hls(*fixture_ids)


def _load_representative_json(path) -> dict[str, Any]:
    """Load one representative catalog document."""
    return json.loads(path.read_text(encoding="utf-8"))


def _promoted_manifest_cases() -> dict[str, dict[str, object]]:
    """Return promoted representative HLS manifest entries keyed by fixture id."""
    manifest = _load_representative_json(REPRESENTATIVE_MANIFEST_PATH)
    return {
        entry["id"]: entry
        for entry in manifest["local_hls_fixtures"]
        if "exact_ground_truth_case_id" in entry
    }


def _promoted_expected_cases() -> dict[str, dict[str, object]]:
    """Return promoted HLS expectation entries keyed by fixture id."""
    expected = _load_representative_json(REPRESENTATIVE_EXPECTATIONS_PATH)
    return {
        case["id"][: -len("_hls")]: case
        for case in expected["cases"]
        if case["id"].endswith("_hls") and "exact_ground_truth_case_id" in case
    }


def _cases_by_unique_id(
    cases: list[dict[str, object]],
    *,
    catalog_name: str,
) -> dict[str, dict[str, object]]:
    """Index catalog cases while preserving duplicate-id failures."""
    case_ids = [case["id"] for case in cases]
    assert len(case_ids) == len(set(case_ids)), f"Duplicate IDs in {catalog_name}"
    return {case["id"]: case for case in cases}


def _representative_hls_ground_truth_cases() -> dict[str, dict[str, object]]:
    """Return representative HLS exact-truth cases keyed by case id."""
    return _cases_by_unique_id(
        representative_hls_ground_truth_cases(),
        catalog_name="representative HLS ground truth",
    )


def _promoted_mp4_blur_manifest_cases() -> dict[str, dict[str, object]]:
    """Return promoted MP4 blur-positive manifest entries keyed by fixture id."""
    manifest = _load_representative_json(REPRESENTATIVE_MANIFEST_PATH)
    fixture_groups = ("source_fixtures", "derived_fixtures")
    return {
        entry["id"]: entry
        for fixture_group in fixture_groups
        for entry in manifest[fixture_group]
        if entry.get("exact_ground_truth_case_id", "").startswith("representative_mp4_")
        and entry["expected"]["blur_alert"] == "expected"
    }


def _promoted_mp4_expected_cases() -> dict[str, dict[str, object]]:
    """Return promoted MP4 blur-positive expectation entries keyed by case id."""
    expected = _load_representative_json(REPRESENTATIVE_EXPECTATIONS_PATH)
    return {
        case["id"]: case
        for case in expected["cases"]
        if case.get("exact_ground_truth_case_id", "").startswith("representative_mp4_")
        and case["expected"]["blur_alert"] == "expected"
    }


def _representative_mp4_ground_truth_cases() -> dict[str, dict[str, object]]:
    """Return representative MP4 exact-truth cases keyed by case id."""
    return _cases_by_unique_id(
        representative_video_file_ground_truth_cases(),
        catalog_name="representative MP4 ground truth",
    )


def _representative_exact_truth_cases() -> dict[str, dict[str, object]]:
    """Return every representative exact-runtime case keyed by its stable id."""
    return _cases_by_unique_id(
        [
            *representative_hls_ground_truth_cases(),
            *representative_video_file_ground_truth_cases(),
        ],
        catalog_name="combined representative ground truth",
    )


def _representative_local_file_manifest_cases() -> dict[str, dict[str, object]]:
    """Return all representative MP4 manifest entries keyed by fixture id."""
    manifest = _load_representative_json(REPRESENTATIVE_MANIFEST_PATH)
    fixture_groups = ("source_fixtures", "derived_fixtures")
    return {
        entry["id"]: entry
        for fixture_group in fixture_groups
        for entry in manifest[fixture_group]
    }


def _representative_expected_cases_by_id() -> dict[str, dict[str, object]]:
    """Return every representative expectation entry keyed by id."""
    expected = _load_representative_json(REPRESENTATIVE_EXPECTATIONS_PATH)
    return _cases_by_unique_id(
        expected["cases"],
        catalog_name="representative expectations",
    )


def _assert_relative_catalog_path(path: str, *, root: str) -> None:
    """Assert one catalog path stays inside its declared representative root."""
    parsed_path = PurePosixPath(path)
    assert not parsed_path.is_absolute()
    assert ".." not in parsed_path.parts
    assert parsed_path.parts[0] == root


def _mp4_confidence_fixture_expectations() -> tuple[ConfidenceFixtureExpectation, ...]:
    """Return the fixture/expectation pairs exercised by capped and soak MP4 lanes."""
    return (
        ConfidenceFixtureExpectation(
            fixture_id="wide_observer__black_strong_start_12s",
            expectation_id="wide_observer__black_strong_start_12s",
        ),
        ConfidenceFixtureExpectation(
            fixture_id="messy_activity__compression_strong_mid_45s",
            expectation_id="messy_activity__compression_strong_mid_45s",
        ),
        ConfidenceFixtureExpectation(
            fixture_id="stable_docs",
            expectation_id="stable_docs__source_baseline",
        ),
        ConfidenceFixtureExpectation(
            fixture_id="crowded_ballot__gblur_strong_mid_20s",
            expectation_id="crowded_ballot__gblur_strong_mid_20s",
        ),
    )


def _assert_subset_contained_by_segment_timeline(
    *,
    subset_start: int,
    subset_end: int,
    timeline: list[dict[str, object]],
    failure_context: str,
) -> None:
    """Assert that one promoted HLS subset fits inside a declared segment timeline."""
    assert any(
        entry["segment_start_index"] <= subset_start
        and subset_end <= entry["segment_end_index"]
        for entry in timeline
    ), failure_context


def _assert_subset_contained_by_second_intervals(
    *,
    subset_start: int,
    subset_end: int,
    intervals: list[dict[str, object]],
    failure_context: str,
) -> None:
    """Assert that one promoted MP4 subset fits inside a declared artifact interval."""
    assert any(
        float(interval["start_seconds"]) <= subset_start
        and subset_end < float(interval["start_seconds"]) + float(interval["duration_seconds"])
        for interval in intervals
    ), failure_context


def _assert_mp4_confidence_metadata_contract(
    manifest_case: dict[str, object],
    expected_case: dict[str, object],
) -> None:
    """Assert the shared catalog contract for one representative MP4 confidence case.

    Source fixtures and derived fixtures use slightly different manifest shapes,
    so this helper locks the overlap that confidence-lane tests rely on.
    """
    assert expected_case["mode"] == "video_files"
    assert manifest_case["path"] == expected_case["path"]
    assert expected_case["assertion_tier"]

    if "mode" in manifest_case:
        assert manifest_case["mode"] == "video_files"
        assert manifest_case["source_id"] == expected_case["source_id"]
        assert manifest_case["assertion_tier"]
        return

    assert manifest_case["id"] == expected_case["source_id"]
    assert manifest_case["role"]
    assert manifest_case["expected_baseline_alerts"]


def test_mp4_fixture_resolves_to_cataloged_hls_folder() -> None:
    """A representative MP4 fixture id should resolve to the matching HLS folder."""
    _require_local_hls_exports("stable_docs__black_strong_mid_12s")
    fixture_dir = representative_hls_fixture_dir_from_mp4_fixture(
        "stable_docs__black_strong_mid_12s"
    )

    assert fixture_dir.name == "stable_docs__black_strong_mid_12s"
    assert (fixture_dir / "index.m3u8").exists()


@pytest.mark.parametrize(
    ("fixture_id", "fixture_group"),
    [
        ("stable_docs", "source"),
        ("stable_docs__black_strong_mid_12s", "derived"),
    ],
)
def test_mp4_manifest_lookup_preserves_source_and_derived_identity_shapes(
    fixture_id: str,
    fixture_group: str,
) -> None:
    """The manifest should remain the identity owner for both MP4 fixture shapes."""
    fixture = representative_mp4_manifest_fixture(fixture_id)

    assert fixture["id"] == fixture_id
    assert fixture["path"].startswith("local_files/")
    if fixture_group == "source":
        assert fixture["source_file"]
        assert fixture["expected_baseline_alerts"]
        assert "artifact" not in fixture
    else:
        assert fixture["source_id"]
        assert fixture["artifact"]["type"]
        assert "expected_baseline_alerts" not in fixture


def test_unknown_hls_identity_is_a_catalog_error_not_an_asset_skip() -> None:
    """Unknown fixture IDs should fail before optional local-asset checks."""
    with pytest.raises(KeyError, match="No representative local HLS fixture"):
        require_representative_local_hls("not-cataloged")


def test_representative_manifest_identity_namespaces_and_summary_stay_consistent() -> None:
    """Catalog identities and summary counts should remain metadata-only facts."""
    manifest = _load_representative_json(REPRESENTATIVE_MANIFEST_PATH)
    source_fixtures = manifest["source_fixtures"]
    derived_fixtures = manifest["derived_fixtures"]
    hls_fixtures = manifest["local_hls_fixtures"]
    source_ids = {fixture["id"] for fixture in source_fixtures}
    artifact_types = {fixture["artifact"]["type"] for fixture in derived_fixtures}

    for fixtures in (source_fixtures, derived_fixtures, hls_fixtures):
        fixture_ids = [fixture["id"] for fixture in fixtures]
        assert len(fixture_ids) == len(set(fixture_ids))

    for fixture in source_fixtures:
        _assert_relative_catalog_path(fixture["path"], root="local_files")
        assert PurePosixPath(fixture["path"]).name == fixture["source_file"]

    for fixture in derived_fixtures:
        _assert_relative_catalog_path(fixture["path"], root="local_files")
        assert fixture["mode"] == "video_files"
        assert fixture["source_id"] in source_ids

    for fixture in hls_fixtures:
        _assert_relative_catalog_path(fixture["path"], root="local_hls")
        _assert_relative_catalog_path(fixture["playlist_path"], root="local_hls")
        _assert_relative_catalog_path(fixture["source_mp4_path"], root="local_files")
        assert fixture["source_id"] in source_ids
        assert fixture["playlist_path"] == f"{fixture['path']}/index.m3u8"

    summary = manifest["summary"]
    assert summary["source_fixture_count"] == len(source_fixtures)
    assert summary["derived_fixture_count"] == len(derived_fixtures)
    assert summary["total_mp4_count"] == len(source_fixtures) + len(derived_fixtures)
    assert summary["local_hls_fixture_count"] == len(hls_fixtures)
    assert set(summary["artifact_types"]) == artifact_types
    assert not set(summary["current_detector_artifacts"]) & set(
        summary["future_quality_artifacts"]
    )
    assert set(summary["current_detector_artifacts"]) | set(
        summary["future_quality_artifacts"]
    ) == artifact_types


def test_representative_expectations_use_declared_values_and_cataloged_identity() -> None:
    """Intent rows should resolve to one manifest identity without reading media."""
    manifest = _load_representative_json(REPRESENTATIVE_MANIFEST_PATH)
    expected = _load_representative_json(REPRESENTATIVE_EXPECTATIONS_PATH)
    source_fixtures = {fixture["id"]: fixture for fixture in manifest["source_fixtures"]}
    mp4_fixtures = {
        fixture["id"]: fixture
        for fixture_group in ("source_fixtures", "derived_fixtures")
        for fixture in manifest[fixture_group]
    }
    hls_fixtures = {fixture["id"]: fixture for fixture in manifest["local_hls_fixtures"]}
    allowed_values = set(expected["expectation_values"])
    cases = _representative_expected_cases_by_id().values()

    for case in cases:
        assert set(case["expected"]) == {
            "black_screen_alert",
            "blur_alert",
            "quality_degradation",
        }
        assert set(case["expected"].values()).issubset(allowed_values)
        assert case["selected_detectors"]
        assert len(case["selected_detectors"]) == len(set(case["selected_detectors"]))

        if case["id"].endswith("_hls"):
            fixture = hls_fixtures[case["id"][: -len("_hls")]]
        else:
            fixture = mp4_fixtures.get(case["id"])
            if fixture is None:
                fixture = source_fixtures[case["source_id"]]
            assert case["path"] == fixture["path"]
            assert case["mode"] == "video_files"
            assert case["source_id"] == fixture.get("source_id", fixture["id"])

        if "assertion_tier" in fixture:
            assert case["assertion_tier"] == fixture["assertion_tier"]
        else:
            assert case["assertion_tier"] == "source_negative_baseline"
            assert fixture["expected_baseline_alerts"] == {
                "black_screen": case["expected"]["black_screen_alert"],
                "blur": case["expected"]["blur_alert"],
            }
            assert case["expected"]["quality_degradation"] == "not_expected"


def test_every_hls_manifest_identity_references_its_canonical_mp4_path() -> None:
    """Every derived HLS fixture should point to its canonical MP4 manifest entry."""
    manifest = _load_representative_json(REPRESENTATIVE_MANIFEST_PATH)

    for hls_fixture in manifest["local_hls_fixtures"]:
        fixture_id = hls_fixture["id"]
        mp4_fixture = representative_mp4_manifest_fixture_for_hls(fixture_id)

        assert representative_hls_manifest_fixture(fixture_id) == hls_fixture
        assert hls_fixture["source_mp4_path"] == mp4_fixture["path"]
        assert hls_fixture["source_id"] == mp4_fixture.get("source_id", mp4_fixture["id"])
        assert hls_fixture["path"] == f"local_hls/{fixture_id}"
        assert representative_hls_fixture_dir_from_mp4_fixture(fixture_id).name == fixture_id


def test_promoted_subset_descriptors_keep_transport_specific_indices_and_sources() -> None:
    """Exact-truth subsets should resolve through their canonical transport identities."""
    for case in _representative_hls_ground_truth_cases().values():
        subset = representative_hls_subset_from_ground_truth_fixture(case["fixture"])
        hls_fixture = representative_hls_manifest_fixture(subset.fixture_id)
        mp4_fixture = representative_mp4_manifest_fixture_for_hls(subset.fixture_id)

        assert hls_fixture["source_mp4_path"] == mp4_fixture["path"]

    for case in _representative_mp4_ground_truth_cases().values():
        subset = representative_video_file_subset_from_ground_truth_fixture(case["fixture"])

        assert representative_mp4_manifest_fixture(subset.fixture_id)["id"] == subset.fixture_id


@pytest.mark.parametrize(
    ("builder", "index_name"),
    [
        (representative_hls_subset, "segment_indices"),
        (representative_video_file_subset, "window_indices"),
    ],
)
@pytest.mark.parametrize("indices", [[], [2, 1], [1, 1], [-1]])
def test_representative_subset_builders_reject_ambiguous_indices(
    builder,
    index_name: str,
    indices: list[int],
) -> None:
    """Subset descriptors should not silently reorder or repair reviewed indices."""
    with pytest.raises(ValueError, match="indices"):
        builder(
            fixture_id="stable_docs__black_strong_mid_12s",
            subset_name="reviewed_subset",
            **{index_name: indices},
        )


def test_local_hls_fixture_reader_returns_playlist_summary() -> None:
    """The HLS fixture reader should expose a stable playlist summary."""
    _require_local_hls_exports("stable_docs__black_strong_mid_12s")
    fixture = read_representative_local_hls_fixture("stable_docs__black_strong_mid_12s")

    assert fixture["playlist_path"].name == "index.m3u8"
    assert fixture["segment_count"] == 152
    assert fixture["segment_names"][0] == "segment_0000.ts"
    assert "#EXTM3U" in fixture["playlist_text"]


def test_hls_expectation_matches_mp4_intent_for_stable_black_case() -> None:
    """The derived HLS expectation should stay aligned with the source MP4 intent."""
    assert_representative_hls_expectation_matches_mp4("stable_docs__black_strong_mid_12s")


def test_hls_expectation_matches_mp4_intent_for_wide_observer_black_case() -> None:
    """A startup-blackout HLS expectation should match the MP4 fixture intent."""
    assert_representative_hls_expectation_matches_mp4(
        "wide_observer__black_strong_start_12s"
    )


def test_wide_observer_hls_expectation_points_back_to_source_mp4() -> None:
    """A cataloged HLS expectation should keep a direct source MP4 reference."""
    fixture = representative_hls_manifest_fixture_for_expected_case(
        "wide_observer__black_strong_start_12s_hls"
    )

    assert fixture["source_mp4_path"] == (
        "local_files/black_screen/wide_observer__black_strong_start_12s.mp4"
    )
    assert fixture["segment_count"] == 1320


@pytest.mark.parametrize(
    ("fixture_id", "expected_segment_count"),
    REPRESENTATIVE_HLS_SEGMENT_COUNTS,
)
def test_mp4_fixture_resolves_to_cataloged_hls_folder_for_representative_hls_cases(
    fixture_id: str,
    expected_segment_count: int,
) -> None:
    """Representative MP4 fixture ids should resolve to usable HLS folders."""
    _require_local_hls_exports(fixture_id)
    fixture_dir = representative_hls_fixture_dir_from_mp4_fixture(fixture_id)

    assert fixture_dir.name == fixture_id
    assert (fixture_dir / "index.m3u8").exists()
    assert len(list(fixture_dir.glob("segment_*.ts"))) == expected_segment_count


@pytest.mark.parametrize(
    ("fixture_id", "expected_segment_count"),
    REPRESENTATIVE_HLS_SEGMENT_COUNTS,
)
def test_local_hls_fixture_reader_returns_playlist_summary_for_representative_cases(
    fixture_id: str,
    expected_segment_count: int,
) -> None:
    """Representative HLS fixtures should expose stable playlist summaries."""
    _require_local_hls_exports(fixture_id)
    fixture = read_representative_local_hls_fixture(fixture_id)

    assert fixture["fixture_id"] == fixture_id
    assert fixture["playlist_path"].name == "index.m3u8"
    assert fixture["segment_count"] == expected_segment_count
    assert fixture["segment_names"][0] == "segment_0000.ts"
    assert "#EXTM3U" in fixture["playlist_text"]


@pytest.mark.parametrize(
    "fixture_id",
    [
        "crowded_ballot__compression_strong_repeated_3x20s",
        "messy_activity__compression_strong_mid_45s",
        "crowded_ballot__gblur_strong_mid_20s",
    ],
)
def test_hls_expectation_matches_mp4_intent_for_representative_cases(
    fixture_id: str,
) -> None:
    """Representative HLS expectations should stay aligned with the source MP4 intent."""
    assert_representative_hls_expectation_matches_mp4(fixture_id)


def test_lowres_mp4_and_hls_expectations_are_intentionally_split_for_now() -> None:
    """The low-res MP4 blur promotion should stay explicit until HLS is promoted too."""
    mp4_case = representative_expected_case("stable_docs__lowres_moderate_start_30s")
    hls_case = representative_expected_case("stable_docs__lowres_moderate_start_30s_hls")

    assert mp4_case["expected"]["blur_alert"] == "expected"
    assert hls_case["expected"]["blur_alert"] == "borderline_or_metric_only"


@pytest.mark.parametrize(
    "fixture_id",
    [
        "crowded_ballot__compression_strong_repeated_3x20s",
        "messy_activity__compression_strong_mid_45s",
        "crowded_ballot__gblur_strong_mid_20s",
        "stable_docs__lowres_moderate_start_30s",
    ],
)
def test_hls_routes_include_playlist_and_first_segment_for_representative_cases(
    fixture_id: str,
) -> None:
    """Representative HLS folders should build route maps for local HTTP tests."""
    _require_local_hls_exports(fixture_id)
    fixture = read_representative_local_hls_fixture(fixture_id)
    routes = build_local_hls_routes(fixture["fixture_dir"])

    assert "/live/index.m3u8" in routes
    assert f"/live/{fixture['segment_names'][0]}" in routes


def test_promoted_representative_hls_metadata_stays_consistent_across_catalogs() -> None:
    """Promoted HLS entries should agree across manifest, expectations, and truth."""
    manifest_cases = _promoted_manifest_cases()
    expected_cases = _promoted_expected_cases()
    ground_truth_cases = _representative_hls_ground_truth_cases()

    assert manifest_cases
    assert manifest_cases.keys() == expected_cases.keys()

    for fixture_id, manifest_case in manifest_cases.items():
        expected_case = expected_cases[fixture_id]
        ground_truth_case = ground_truth_cases[manifest_case["exact_ground_truth_case_id"]]

        assert expected_case["exact_ground_truth_case_id"] == manifest_case["exact_ground_truth_case_id"]
        assert expected_case["assertion_tier"] == manifest_case["assertion_tier"]
        assert expected_case["expected"] == manifest_case["expected"]
        assert (
            representative_hls_manifest_fixture_for_expected_case(expected_case["id"])
            == manifest_case
        )
        assert ground_truth_case["fixture"]["fixture_id"] == fixture_id
        assert set(ground_truth_case["selected_detectors"]).issubset(
            expected_case["selected_detectors"]
        )


def test_catalog_exact_truth_references_resolve_to_matching_runtime_cases() -> None:
    """Catalog-linked exact truth should identify one reviewed runtime subset."""
    manifest = _load_representative_json(REPRESENTATIVE_MANIFEST_PATH)
    expected_cases = _representative_expected_cases_by_id()
    ground_truth_cases = _representative_exact_truth_cases()
    manifest_entries = [
        *manifest["source_fixtures"],
        *manifest["derived_fixtures"],
        *manifest["local_hls_fixtures"],
    ]
    manifest_references = {
        entry["exact_ground_truth_case_id"]: entry
        for entry in manifest_entries
        if "exact_ground_truth_case_id" in entry
    }
    expected_references = {
        case["exact_ground_truth_case_id"]: case
        for case in expected_cases.values()
        if "exact_ground_truth_case_id" in case
    }

    assert manifest_references
    assert manifest_references.keys() == expected_references.keys()
    assert len(manifest_references) == sum(
        "exact_ground_truth_case_id" in entry for entry in manifest_entries
    )
    assert len(expected_references) == sum(
        "exact_ground_truth_case_id" in case for case in expected_cases.values()
    )

    for truth_id, manifest_entry in manifest_references.items():
        truth_case = ground_truth_cases[truth_id]
        expected_case = expected_references[truth_id]
        fixture = truth_case["fixture"]
        truth = truth_case["ground_truth"]

        assert fixture["fixture_id"] == manifest_entry["id"]
        assert truth_case["mode"] == manifest_entry["mode"]
        assert set(truth_case["selected_detectors"]).issubset(
            expected_case["selected_detectors"]
        )
        assert truth["session_status"] == truth["progress_status"] == "completed"

        if fixture["kind"] == "representative_local_hls_subset":
            subset = representative_hls_subset_from_ground_truth_fixture(fixture)
            assert truth["processed_count"] == truth["result_count"] == subset.segment_count
        else:
            subset = representative_video_file_subset_from_ground_truth_fixture(fixture)
            assert truth["processed_count"] == truth["result_count"] == subset.window_count


def test_promoted_representative_hls_subset_range_stays_inside_declared_timeline() -> None:
    """Every promoted exact HLS subset should fit inside one declared timeline range."""
    manifest_cases = _promoted_manifest_cases()
    ground_truth_cases = _representative_hls_ground_truth_cases()

    for ground_truth_case in ground_truth_cases.values():
        subset = representative_hls_subset_from_ground_truth_fixture(ground_truth_case["fixture"])
        timeline = manifest_cases[subset.fixture_id]["approximate_artifact_timeline_by_segment"]
        subset_start = min(subset.segment_indices)
        subset_end = max(subset.segment_indices)

        _assert_subset_contained_by_segment_timeline(
            subset_start=subset_start,
            subset_end=subset_end,
            timeline=timeline,
            failure_context=(
            f"Promoted subset {ground_truth_case['id']!r} spans {subset_start}-{subset_end}, "
            f"which is not contained by any declared representative timeline window."
            ),
        )


def test_promoted_representative_mp4_blur_truth_stays_consistent_with_catalogs() -> None:
    """Promoted exact MP4 blur truth should resolve across catalogs and stay timeline-contained."""
    manifest_cases = _promoted_mp4_blur_manifest_cases()
    expected_cases = _promoted_mp4_expected_cases()
    ground_truth_cases = _representative_mp4_ground_truth_cases()

    assert manifest_cases

    for fixture_id, manifest_case in manifest_cases.items():
        assert fixture_id in expected_cases
        expected_case = expected_cases[fixture_id]
        ground_truth_case_id = manifest_case["exact_ground_truth_case_id"]

        assert expected_case["exact_ground_truth_case_id"] == ground_truth_case_id
        assert expected_case["path"] == manifest_case["path"]
        assert expected_case["mode"] == manifest_case["mode"] == "video_files"
        assert expected_case["source_id"] == manifest_case["source_id"]
        assert expected_case["expected"]["blur_alert"] == "expected"
        assert ground_truth_case_id in ground_truth_cases

        subset = representative_video_file_subset_from_ground_truth_fixture(
            ground_truth_cases[ground_truth_case_id]["fixture"]
        )
        subset_start = min(subset.window_indices)
        subset_end = max(subset.window_indices)

        _assert_subset_contained_by_second_intervals(
            subset_start=subset_start,
            subset_end=subset_end,
            intervals=manifest_case["artifact"]["intervals"],
            failure_context=(
            f"Promoted MP4 blur subset {ground_truth_case_id!r} spans "
            f"{subset_start}-{subset_end}, which is outside the declared artifact timeline."
            ),
        )


def test_representative_mp4_confidence_fixtures_have_catalog_and_confidence_metadata() -> None:
    """Every soak/capped MP4 fixture should resolve across catalogs with a clear tier."""
    manifest_cases = _representative_local_file_manifest_cases()
    expected_cases = _representative_expected_cases_by_id()

    for case in _mp4_confidence_fixture_expectations():
        assert case.fixture_id in manifest_cases
        assert case.expectation_id in expected_cases

        _assert_mp4_confidence_metadata_contract(
            manifest_cases[case.fixture_id],
            expected_cases[case.expectation_id],
        )
