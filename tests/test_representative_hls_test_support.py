"""Support and catalog guards for representative MP4/HLS fixtures.

These tests keep the representative media catalogs usable for both engineers
and AI-assisted contributors by checking a few simple contracts:
- fixture paths resolve
- exported HLS folders stay readable
- promoted entries stay aligned across manifest, expectations, and truth
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from tests.e2e_session_test_support import load_ground_truth_cases
from tests.representative_hls_test_support import (
    REPRESENTATIVE_EXPECTATIONS_PATH,
    REPRESENTATIVE_MANIFEST_PATH,
    assert_representative_hls_expectation_matches_mp4,
    build_local_hls_routes,
    read_representative_local_hls_fixture,
    representative_expected_case,
    representative_hls_fixture_dir_from_mp4_fixture,
    representative_hls_subset_from_ground_truth_fixture,
    representative_video_file_subset_from_ground_truth_fixture,
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


def _representative_hls_ground_truth_cases() -> dict[str, dict[str, object]]:
    """Return representative HLS exact-truth cases keyed by case id."""
    return {
        case["id"]: case
        for case in load_ground_truth_cases("representative_local_hls_cases")
    }


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
    return {
        case["id"]: case
        for case in load_ground_truth_cases("representative_local_video_file_cases")
    }


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
    return {case["id"]: case for case in expected["cases"]}


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


def _timeline_semantics(
    timeline: list[dict[str, object]],
) -> list[tuple[object, object, object, object]]:
    """Normalize timeline entries so cross-catalog comparison stays simple."""
    return [
        (
            entry["kind"],
            entry["segment_start_index"],
            entry["segment_end_index"],
            entry["expected_effect"],
        )
        for entry in timeline
    ]


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
    fixture_dir = representative_hls_fixture_dir_from_mp4_fixture(
        "stable_docs__black_strong_mid_12s"
    )

    assert fixture_dir.name == "stable_docs__black_strong_mid_12s"
    assert (fixture_dir / "index.m3u8").exists()


def test_local_hls_fixture_reader_returns_playlist_summary() -> None:
    """The HLS fixture reader should expose a stable playlist summary."""
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
    case = representative_expected_case("wide_observer__black_strong_start_12s_hls")

    assert case["source_mp4_path"] == (
        "local_files/black_screen/wide_observer__black_strong_start_12s.mp4"
    )
    assert case["segment_count"] == 1320


@pytest.mark.parametrize(
    ("fixture_id", "expected_segment_count"),
    REPRESENTATIVE_HLS_SEGMENT_COUNTS,
)
def test_mp4_fixture_resolves_to_cataloged_hls_folder_for_representative_hls_cases(
    fixture_id: str,
    expected_segment_count: int,
) -> None:
    """Representative MP4 fixture ids should resolve to usable HLS folders."""
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
        assert expected_case["path"] == manifest_case["path"]
        assert expected_case["mode"] == manifest_case["mode"] == "video_segments"
        assert expected_case["source_id"] == manifest_case["source_id"]
        assert expected_case["source_mp4_path"] == manifest_case["source_mp4_path"]
        assert expected_case["playlist_path"] == manifest_case["playlist_path"]
        assert expected_case["segment_count"] == manifest_case["segment_count"]
        assert expected_case["assertion_tier"] == manifest_case["assertion_tier"]
        assert expected_case["expected"] == manifest_case["expected"]
        assert (
            _timeline_semantics(expected_case["approximate_artifact_timeline_by_segment"])
            == _timeline_semantics(manifest_case["approximate_artifact_timeline_by_segment"])
        )
        assert ground_truth_case["fixture"]["fixture_id"] == fixture_id
        assert set(ground_truth_case["selected_detectors"]).issubset(
            expected_case["selected_detectors"]
        )


def test_every_promoted_representative_hls_ground_truth_id_resolves() -> None:
    """Every promoted HLS truth reference should resolve to a real case."""
    ground_truth_case_ids = set(_representative_hls_ground_truth_cases())
    manifest_truth_ids = {
        case["exact_ground_truth_case_id"] for case in _promoted_manifest_cases().values()
    }
    expected_truth_ids = {
        case["exact_ground_truth_case_id"] for case in _promoted_expected_cases().values()
    }

    assert manifest_truth_ids
    assert manifest_truth_ids == expected_truth_ids
    assert manifest_truth_ids.issubset(ground_truth_case_ids)


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
