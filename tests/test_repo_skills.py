"""Deterministic contract tests for repo-local Codex skills.

This file is the main behavior-facing harness for the local skill layer. It
checks inventory, routing boundaries, representative scenarios, and fixed
output-shape snapshots without live model calls.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from tests.repo_skill_expectations import (
    AMBIGUOUS_BOUNDARY_EXPECTATIONS,
    ARCHIVED_SKILL_REACTIVATION_SNIPPETS,
    BOUNDARY_SNIPPETS_BY_SKILL,
    COMMON_SECTIONS,
    DISCOVERY_DESCRIPTION_EXPECTATIONS,
    EXPECTED_SKILLS,
    EXPLICIT_HANDOFF_EXPECTATIONS,
    HISTORICAL_RETIRED_SKILLS_HEADING,
    MANUAL_PROMPT_EVALUATION_PRIMARY_SKILLS,
    MERGED_SKILL_MODE_MARKERS,
    PLANNING_CLOSURE_PROFILE_EXPECTATIONS,
    PLANNING_CLOSURE_SPECIALISTS,
    REAL_INCIDENT_REGRESSIONS,
    RETIRED_SKILL_SURVIVORS,
    RISKY_CHANGE_ROUTING_ORDER,
    RISKY_CHANGE_ROUTING_REQUIRED_SNIPPETS,
    SCENARIO_EXPECTATIONS,
    SNAPSHOT_EXPECTATIONS,
    expected_skill_files,
)
from tests.skill_test_support import (
    ARCHIVED_SKILLS_ROOT,
    MANUAL_PROMPT_EVALUATIONS_PATH,
    REPOSITORY_ROOT,
    SKILL_SECTION_ORDER,
    SKILLS_ROOT,
    ScenarioExpectation,
    SnapshotExpectation,
    assert_all_snippets_absent,
    assert_all_snippets_present,
    assert_contains_in_order,
    extract_colon_headings,
    extract_headings,
    extract_just_recipes,
    extract_repository_references,
    list_archived_skill_files,
    list_just_recipes,
    list_skill_files,
    load_all_skills,
    load_manual_prompt_evaluation_cases,
    load_skill,
    load_skill_file,
    load_snapshot,
    resolve_repository_reference,
    snapshot_heading_matches_skill_text,
)

AGENTS_PATH = Path(__file__).resolve().parent.parent / "AGENTS.md"
DOCS_INDEX_PATH = Path(__file__).resolve().parent.parent / "docs" / "README.md"
JUSTFILE_PATH = REPOSITORY_ROOT / "justfile"
INVENTORY_PATH = SKILLS_ROOT / "INVENTORY.md"
TEST_POLICY_PATH = Path(__file__).resolve().parent / "repo_skill_expectations.py"


def test_expected_skill_directories_exist() -> None:
    actual_skill_names = set(load_all_skills())
    assert actual_skill_names == EXPECTED_SKILLS


def test_discovery_expectations_cover_each_active_skill_once() -> None:
    """Keep each active skill assigned to one explicit discovery seam."""
    assert set(DISCOVERY_DESCRIPTION_EXPECTATIONS) == EXPECTED_SKILLS

    primary_phrases = [
        primary_phrase
        for primary_phrase, _excluded_phrases in DISCOVERY_DESCRIPTION_EXPECTATIONS.values()
    ]
    duplicate_phrases = [
        phrase for phrase, count in Counter(primary_phrases).items() if count > 1
    ]
    assert not duplicate_phrases, f"Duplicate primary seam phrases: {duplicate_phrases}"


def test_manual_prompt_evaluation_catalog_keeps_routing_coverage() -> None:
    """Keep the manual routing sample representative without testing a model."""
    cases = load_manual_prompt_evaluation_cases()
    case_ids = [case.case_id for case in cases]
    primary_skills = {case.primary_skill for case in cases}

    assert MANUAL_PROMPT_EVALUATIONS_PATH.exists()
    assert 5 <= len(cases) <= 8
    assert len(case_ids) == len(set(case_ids))
    assert primary_skills == MANUAL_PROMPT_EVALUATION_PRIMARY_SKILLS
    assert primary_skills <= EXPECTED_SKILLS

    for case in cases:
        assert case.case_id
        assert case.prompt
        assert case.required_properties
        assert case.avoided_behavior
        assert case.primary_skill not in case.prompt


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


@pytest.mark.parametrize("skill_name", sorted(EXPECTED_SKILLS))
def test_discovery_descriptions_keep_size_and_routing_boundaries(
    skill_name: str,
) -> None:
    skill = load_skill(skill_name)
    description = skill.description.strip().strip('"')
    primary_phrase, excluded_phrases = DISCOVERY_DESCRIPTION_EXPECTATIONS[skill_name]

    assert len(description.splitlines()) == 1
    assert 100 <= len(description) <= 200
    assert primary_phrase in description
    for excluded_phrase in excluded_phrases:
        assert excluded_phrase in description


@pytest.mark.parametrize(
    ("profile", "required_concepts"),
    PLANNING_CLOSURE_PROFILE_EXPECTATIONS.items(),
)
def test_planning_closure_profiles_keep_their_required_concepts(
    profile: str,
    required_concepts: tuple[str, ...],
) -> None:
    """Keep proportional closure without fixing the planner's full wording."""
    skill = load_skill("task-planning-evaluation")

    assert profile
    assert assert_contains_in_order(skill.body, required_concepts)


def test_planning_closure_delegates_to_specialist_owners() -> None:
    """Keep validation, docs, and branch decisions outside planning itself."""
    skill = load_skill("task-planning-evaluation")

    for specialist in PLANNING_CLOSURE_SPECIALISTS:
        assert specialist in skill.body
    assert "stay with their specialist owners" in skill.body


@pytest.mark.parametrize(
    ("skill_name", "boundary_snippets"),
    BOUNDARY_SNIPPETS_BY_SKILL,
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


@pytest.mark.parametrize(
    ("skill_name", "_overlap_case", "required_snippets", "excluded_snippets"),
    AMBIGUOUS_BOUNDARY_EXPECTATIONS,
)
def test_ambiguous_prompts_still_point_to_the_intended_skill_boundary(
    skill_name: str,
    _overlap_case: str,
    required_snippets: tuple[str, ...],
    excluded_snippets: tuple[str, ...],
) -> None:
    skill = load_skill(skill_name)
    assert_all_snippets_present(skill.text, required_snippets)
    assert_all_snippets_absent(skill.text, excluded_snippets)


@pytest.mark.parametrize(
    ("skill_name", "handoff_snippet"),
    EXPLICIT_HANDOFF_EXPECTATIONS,
)
def test_explicit_skill_handoffs_remain_intentional(
    skill_name: str,
    handoff_snippet: str,
) -> None:
    skill = load_skill(skill_name)
    assert handoff_snippet in skill.body


@pytest.mark.parametrize(
    ("skill_name", "required_mode_markers"),
    MERGED_SKILL_MODE_MARKERS,
)
def test_merged_skill_families_keep_their_distinct_modes(
    skill_name: str,
    required_mode_markers: tuple[str, ...],
) -> None:
    skill = load_skill(skill_name)
    assert_all_snippets_present(skill.text, required_mode_markers)


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
    assert list_skill_files() == expected_skill_files(SKILLS_ROOT)


def test_explicit_skill_repository_references_resolve() -> None:
    """Keep active and archived skill links routed to tracked repository files."""
    unresolved_references = []
    skill_paths = [
        *(SKILLS_ROOT / relative_path for relative_path in list_skill_files()),
        *list_archived_skill_files(),
    ]

    for skill_path in skill_paths:
        skill = load_skill_file(skill_path)
        for reference in extract_repository_references(skill.text):
            resolved_path = resolve_repository_reference(skill.path, reference)
            if not resolved_path.is_relative_to(REPOSITORY_ROOT) or not resolved_path.exists():
                unresolved_references.append(f"{skill.path}: {reference}")

    assert not unresolved_references, "Unresolved skill references:\n" + "\n".join(
        unresolved_references
    )


def test_explicit_skill_just_recipes_exist() -> None:
    """Keep skill validation commands aligned with the local recipe owner."""
    available_recipes = list_just_recipes(JUSTFILE_PATH)
    missing_recipes = []
    skill_paths = [
        *(SKILLS_ROOT / relative_path for relative_path in list_skill_files()),
        *list_archived_skill_files(),
    ]

    for skill_path in skill_paths:
        skill = load_skill_file(skill_path)
        for recipe in extract_just_recipes(skill.text):
            if recipe not in available_recipes:
                missing_recipes.append(f"{skill.path}: just {recipe}")

    assert not missing_recipes, "Missing just recipes:\n" + "\n".join(missing_recipes)


def test_repo_skill_recipe_stays_available_and_deterministic() -> None:
    """Keep the harness entrypoint separate from product validation lanes."""
    justfile_text = JUSTFILE_PATH.read_text(encoding="utf-8")

    assert "test-repo-skills" in list_just_recipes(JUSTFILE_PATH)
    recipe_body = _just_recipe_body(justfile_text, "test-repo-skills")
    assert "{{pytest_env_prefix}}" in recipe_body
    assert "{{venv_pytest}}" in recipe_body
    assert "{{pytest_base_flags}}" in recipe_body
    assert "tests/test_repo_skills.py" in recipe_body


def test_retired_skill_directories_stay_absent() -> None:
    """Keep merged skills out of both active and deferred discovery roots."""
    for retired_skill in RETIRED_SKILL_SURVIVORS:
        assert not (SKILLS_ROOT / retired_skill).exists()
        assert not (ARCHIVED_SKILLS_ROOT / retired_skill).exists()


def test_retired_skill_names_remain_only_in_the_historical_inventory_record() -> None:
    """Keep former routing names out of active guidance and test evidence."""
    inventory_text = INVENTORY_PATH.read_text(encoding="utf-8")
    historical_record = _markdown_section(
        inventory_text,
        HISTORICAL_RETIRED_SKILLS_HEADING,
    )
    inventory_without_historical_record = inventory_text.replace(historical_record, "")

    for retired_skill, survivor in RETIRED_SKILL_SURVIVORS.items():
        assert retired_skill in historical_record
        assert survivor in historical_record
        assert retired_skill not in inventory_without_historical_record

    reference_paths = [
        AGENTS_PATH,
        DOCS_INDEX_PATH,
        REPOSITORY_ROOT / "docs" / "testing-and-validation.md",
        *(SKILLS_ROOT / relative_path for relative_path in list_skill_files()),
        *list_archived_skill_files(),
        *Path(__file__).resolve().parent.rglob("*.py"),
        *(Path(__file__).resolve().parent / "fixtures" / "skill_output_snapshots").glob("*.md"),
    ]
    stale_references = []
    for path in reference_paths:
        if path == TEST_POLICY_PATH:
            continue
        text = path.read_text(encoding="utf-8")
        for retired_skill in RETIRED_SKILL_SURVIVORS:
            if retired_skill in text:
                stale_references.append(f"{path}: {retired_skill}")

    assert not stale_references, "Retired skill references:\n" + "\n".join(
        stale_references
    )


def test_agents_md_risky_change_routing_stays_aligned() -> None:
    text = AGENTS_PATH.read_text(encoding="utf-8")

    assert_contains_in_order(
        text,
        RISKY_CHANGE_ROUTING_ORDER,
    )

    for snippet in RISKY_CHANGE_ROUTING_REQUIRED_SNIPPETS:
        assert snippet in text


def test_archived_specialists_stay_explicit_and_discoverable() -> None:
    text = DOCS_INDEX_PATH.read_text(encoding="utf-8")

    for snippet in ARCHIVED_SKILL_REACTIVATION_SNIPPETS:
        assert snippet in text


def _markdown_section(text: str, heading: str) -> str:
    """Return one second-level Markdown section, including its heading."""
    section_start = text.find(heading)
    assert section_start >= 0, f"Missing section: {heading}"
    next_section_start = text.find("\n## ", section_start + len(heading))
    if next_section_start < 0:
        return text[section_start:]
    return text[section_start:next_section_start]


def _just_recipe_body(text: str, recipe_name: str) -> str:
    """Return one recipe body without depending on neighboring recipe order."""
    match = re.search(
        rf"^{re.escape(recipe_name)}:\n((?:[ \t]+.*(?:\n|$))*)",
        text,
        flags=re.MULTILINE,
    )
    assert match is not None, f"Missing recipe: {recipe_name}"
    return match.group(1)
