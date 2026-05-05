"""Deterministic tests for repo-local Codex skills.

These tests intentionally avoid API keys or live model calls. They check that
the current skills stay structurally valid, scenario-aware, and clearly
separated in purpose.
"""

from __future__ import annotations

import pytest

from tests.skill_test_support import (
    SKILLS_ROOT,
    SKILL_SECTION_ORDER,
    ScenarioExpectation,
    SnapshotExpectation,
    assert_contains_in_order,
    extract_colon_headings,
    extract_headings,
    list_skill_files,
    load_all_skills,
    load_snapshot,
    load_skill,
    snapshot_heading_matches_skill_text,
)


EXPECTED_SKILLS = {
    "incident-timeline",
    "root-cause-suggestion",
    "summarization",
    "test-coverage-gaps",
}

COMMON_SECTIONS = [
    "## Default approach",
    "## Output shape",
    "## Avoid",
]

SCENARIO_EXPECTATIONS = [
    ScenarioExpectation(
        skill_name="summarization",
        required_snippets=(
            "What it is",
            "What changed",
            "Why it matters",
            "Contract/lifecycle/operator impact",
            "Next safest action",
        ),
    ),
    ScenarioExpectation(
        skill_name="incident-timeline",
        required_snippets=(
            "Observed facts",
            "Reconstructed sequence",
            "first session snapshot persisted",
            "Frontend events",
            "Terminal state",
        ),
    ),
    ScenarioExpectation(
        skill_name="test-coverage-gaps",
        required_snippets=(
            "contract gap",
            "Cheapest useful test",
            "existing nearby test files",
        ),
    ),
    ScenarioExpectation(
        skill_name="root-cause-suggestion",
        required_snippets=(
            "Most likely root cause",
            "GitHub policy/state",
            "Cheapest next validation",
        ),
    ),
]

REAL_INCIDENT_REGRESSIONS = [
    ("incident-timeline", "session starts but UI falls back to idle"),
    ("incident-timeline", "branch protection / CI merge incidents"),
    ("root-cause-suggestion", "session start succeeded but first read 404s"),
    ("root-cause-suggestion", "PR is green but merge remains blocked"),
]

SNAPSHOT_EXPECTATIONS = [
    SnapshotExpectation(
        skill_name="summarization",
        snapshot_name="summarization_mcp_direction.md",
        required_order=(
            "What it is:",
            "What changed or What is happening:",
            "Why it matters:",
            "Contract/lifecycle/operator impact:",
            "Next safest action:",
        ),
    ),
    SnapshotExpectation(
        skill_name="incident-timeline",
        snapshot_name="incident_timeline_ui_idle.md",
        required_order=(
            "Observed facts:",
            "Reconstructed sequence:",
            "Trigger:",
            "First visible symptom:",
            "Backend events:",
            "Frontend events:",
            "Persistence/session-file events:",
            "Terminal state:",
            "Unknowns still left:",
        ),
    ),
    SnapshotExpectation(
        skill_name="test-coverage-gaps",
        snapshot_name="test_coverage_gaps_bridge_contract.md",
        required_order=(
            "Gap:",
            "Why it matters:",
            "Best test layer:",
            "Cheapest useful test:",
        ),
    ),
    SnapshotExpectation(
        skill_name="root-cause-suggestion",
        snapshot_name="root_cause_pr_blocked.md",
        required_order=(
            "Most likely root cause:",
            "Confidence:",
            "Evidence for it:",
            "Evidence against it:",
            "Cheapest next validation:",
        ),
    ),
]


def test_expected_skill_directories_exist() -> None:
    actual_skill_names = set(load_all_skills())
    assert actual_skill_names == EXPECTED_SKILLS


@pytest.mark.parametrize("skill_name", sorted(EXPECTED_SKILLS))
def test_each_skill_has_required_frontmatter_and_sections(skill_name: str) -> None:
    skill = load_skill(skill_name)

    assert skill.name == skill_name
    assert skill.description

    headings = extract_headings(skill.body)
    assert headings
    assert headings[0] == f"# {' '.join(part.capitalize() for part in skill_name.split('-'))}"

    for required_heading in COMMON_SECTIONS:
        assert required_heading in headings


@pytest.mark.parametrize("skill_name", sorted(EXPECTED_SKILLS))
def test_skill_sections_stay_in_readable_order(skill_name: str) -> None:
    skill = load_skill(skill_name)
    assert assert_contains_in_order(skill.body, SKILL_SECTION_ORDER)


@pytest.mark.parametrize(
    ("skill_name", "boundary_snippets"),
    [
        (
            "summarization",
            [
                "Use `incident-timeline`",
                "Use `root-cause-suggestion`",
                "Use `test-coverage-gaps`",
            ],
        ),
        (
            "incident-timeline",
            [
                "Use this before `root-cause-suggestion`",
                "Hand off to `root-cause-suggestion`",
            ],
        ),
        (
            "test-coverage-gaps",
            [
                "Use this after the behavior or incident is already understood",
                "use `summarization` or `incident-timeline` first",
            ],
        ),
        (
            "root-cause-suggestion",
            [
                "If event order is still unclear, use `incident-timeline` first.",
                "If the user mainly wants ordered reconstruction, use `incident-timeline` instead.",
            ],
        ),
    ],
)
def test_skill_boundaries_are_explicit(
    skill_name: str,
    boundary_snippets: list[str],
) -> None:
    skill = load_skill(skill_name)
    for snippet in boundary_snippets:
        assert snippet in skill.body


@pytest.mark.parametrize("expectation", SCENARIO_EXPECTATIONS)
def test_golden_scenarios_are_supported_by_skill_content(
    expectation: ScenarioExpectation,
) -> None:
    skill = load_skill(expectation.skill_name)
    for snippet in expectation.required_snippets:
        assert snippet in skill.text


@pytest.mark.parametrize(("skill_name", "incident_text"), REAL_INCIDENT_REGRESSIONS)
def test_real_repo_incident_examples_remain_covered(
    skill_name: str,
    incident_text: str,
) -> None:
    skill = load_skill(skill_name)
    assert incident_text in skill.text


@pytest.mark.parametrize("expectation", SNAPSHOT_EXPECTATIONS)
def test_snapshot_expected_outputs_stay_stable(
    expectation: SnapshotExpectation,
) -> None:
    snapshot_text = load_snapshot(expectation.snapshot_name)

    assert snapshot_text
    assert assert_contains_in_order(snapshot_text, list(expectation.required_order))


@pytest.mark.parametrize("expectation", SNAPSHOT_EXPECTATIONS)
def test_snapshot_outputs_match_skill_intent(
    expectation: SnapshotExpectation,
) -> None:
    skill = load_skill(expectation.skill_name)
    snapshot_text = load_snapshot(expectation.snapshot_name)

    for heading in extract_colon_headings(snapshot_text):
        assert snapshot_heading_matches_skill_text(skill.text, heading)


def test_skill_root_stays_small_and_repo_local() -> None:
    assert list_skill_files() == [
        SKILLS_ROOT.joinpath("incident-timeline", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("root-cause-suggestion", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("summarization", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("test-coverage-gaps", "SKILL.md").relative_to(SKILLS_ROOT),
    ]
