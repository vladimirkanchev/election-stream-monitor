"""Deterministic tests for repo-local Codex skills.

These tests avoid API keys and live model calls. They protect the repo-local
skill layer by checking:

- inventory and structure
- ownership boundaries and explicit handoffs
- bidirectional boundary checks for nearby skill pairs
- workflow-owner guidance for planning depth, validation lanes, docs routing,
  and branch readiness
- representative scenarios and fixed output snapshots
- recently merged skill shapes that should stay distinct
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
    "alert-backend-parity-review",
    "architecture-diagram-review",
    "branch-pr-readiness",
    "ci-failure-triage",
    "dependency-change-review",
    "detector-rule-review",
    "docs-alignment",
    "docs-drift-check",
    "fastapi-mcp-security-review",
    "fixture-environment-safety",
    "frontend-bridge-review",
    "incident-timeline",
    "manual-validation-planner",
    "persistence-backend-review",
    "readme-alignment-review",
    "root-cause-suggestion",
    "security-surface-review",
    "summarization",
    "task-planning-evaluation",
    "test-strategy-review",
}

COMMON_SECTIONS = [
    "## Default approach",
    "## Output shape",
    "## Avoid",
]

SCENARIO_EXPECTATIONS = [
    ScenarioExpectation(
        skill_name="alert-backend-parity-review",
        required_snippets=(
            "Parity surface",
            "file-backed versus PostgreSQL-backed",
            "Main parity risk",
            "security-surface-review",
        ),
    ),
    ScenarioExpectation(
        skill_name="persistence-backend-review",
        required_snippets=(
            "Persistence surface",
            "Default versus opt-in behavior",
            "metadata, latest progress, ordered results, cancel intent",
            "detached-worker backend agreement",
            "just test-session-store",
        ),
    ),
    ScenarioExpectation(
        skill_name="fastapi-mcp-security-review",
        required_snippets=(
            "Checklist gaps",
            "share mode",
            "MCP tool exposure",
            "dependency exposure",
            "Best validation lane",
        ),
    ),
    ScenarioExpectation(
        skill_name="security-surface-review",
        required_snippets=(
            "Security surface",
            "local-first advanced-prototype stage",
            "MCP `stdio` local tooling",
        ),
    ),
    ScenarioExpectation(
        skill_name="branch-pr-readiness",
        required_snippets=(
            "Recommended commit shape",
            "Recommended PR shape",
            "Readiness summary",
            "one coherent PR",
            "follow-up extraction hint",
            "commit grouping",
            "does the branch still have one primary user-visible or maintainer-visible outcome?",
        ),
    ),
    ScenarioExpectation(
        skill_name="test-strategy-review",
        required_snippets=(
            "Strong tests",
            "Weak or low-value tests",
            "environment-coupled tests",
            "validation-lane chooser",
            "Closest owning boundary",
            "Recommended lane",
            "Best first command",
            "focused harness lanes",
            "contract gap",
        ),
    ),
    ScenarioExpectation(
        skill_name="dependency-change-review",
        required_snippets=(
            "Most likely classification",
            "intentional, incidental, or branch drift",
            "`pyproject.toml`",
        ),
    ),
    ScenarioExpectation(
        skill_name="summarization",
        required_snippets=(
            "What changed",
            "Behavior impact",
            "behavior-preserving",
        ),
    ),
    ScenarioExpectation(
        skill_name="fixture-environment-safety",
        required_snippets=(
            "CI safety assessment",
            "local-only research assets",
            "missing `.venv`",
        ),
    ),
    ScenarioExpectation(
        skill_name="manual-validation-planner",
        required_snippets=(
            "Validation target",
            "Electron",
            "playback",
            "Best follow-up automation",
        ),
    ),
    ScenarioExpectation(
        skill_name="frontend-bridge-review",
        required_snippets=(
            "Ownership assessment",
            "renderer, preload, Electron main, or backend",
            "UI/runtime impact",
            "manual-validation-planner",
        ),
    ),
    ScenarioExpectation(
        skill_name="detector-rule-review",
        required_snippets=(
            "Findings",
            "Boundary assessment",
            "runtime versus `detector_lab` boundary",
        ),
    ),
    ScenarioExpectation(
        skill_name="task-planning-evaluation",
        required_snippets=(
            "Importance",
            "Recommended phase",
            "current local-first advanced-prototype stage",
        ),
    ),
    ScenarioExpectation(
        skill_name="docs-alignment",
        required_snippets=(
            "Drift summary",
            "docs-owner hint",
            "public-contract check",
            "docs/contracts.md",
            "Prefer one owner, not three copies.",
            "Recommended updates",
            "low-value repetition",
        ),
    ),
    ScenarioExpectation(
        skill_name="docs-drift-check",
        required_snippets=(
            "Drift class",
            "no real drift",
            "wording drift",
            "behavior drift",
            "contract drift",
            "workflow drift",
            "Current accuracy",
            "What should move with it",
        ),
    ),
    ScenarioExpectation(
        skill_name="architecture-diagram-review",
        required_snippets=(
            "Diagram rating",
            "Visual quality",
            "Flow arrow review",
            "Boundary review",
            "Arrow-origin check",
            "Arrow-end check",
            "Stage honesty",
            "local-first advanced-prototype stage",
        ),
    ),
    ScenarioExpectation(
        skill_name="readme-alignment-review",
        required_snippets=(
            "README fit",
            "keep here",
            "shrink here",
            "move to deeper docs",
            "Stage honesty",
            "Heavy-section warning",
            "local-first advanced-prototype stage",
        ),
    ),
    ScenarioExpectation(
        skill_name="branch-pr-readiness",
        required_snippets=(
            "Drift assessment",
            "Recommended PR shape",
            "Merged-vs-main state",
            "branch-end closure",
            "contract-sensitive work moved with the owning docs and nearby tests",
            "move to a follow-up branch",
            "Treat these as strong split signals",
            "the PR description needs \"also\" more than once to justify the branch",
        ),
    ),
    ScenarioExpectation(
        skill_name="ci-failure-triage",
        required_snippets=(
            "Most likely failure class",
            "Smallest local reproduction",
            "CI or policy drift",
        ),
    ),
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
        skill_name="root-cause-suggestion",
        required_snippets=(
            "Most likely root cause",
            "GitHub policy/state",
            "Cheapest next validation",
        ),
    ),
]

REAL_INCIDENT_REGRESSIONS = [
    ("alert-backend-parity-review", "a session-alert store refactor may have changed file versus PostgreSQL grouped-incident behavior"),
    ("alert-backend-parity-review", "an alerts-router auth change needs review for whether it touched store parity or only access policy"),
    ("persistence-backend-review", "a session-store branch may have changed file versus PostgreSQL snapshot semantics"),
    ("persistence-backend-review", "a detached worker may no longer inherit the same store backend as the parent"),
    ("fastapi-mcp-security-review", "a FastAPI route branch may have widened `share` mode beyond the intended boundary"),
    ("fastapi-mcp-security-review", "an MCP tool update may have drifted outside the read-only local tooling model"),
    ("security-surface-review", "a FastAPI route change may have drifted outside the intended auth or rate-limit boundary"),
    ("security-surface-review", "an `api_stream` trust policy change needs review for boundary clarity rather than full platform redesign"),
    ("branch-pr-readiness", "a harness branch needs to know whether 2 or 3 commits is the cleanest shape"),
    ("branch-pr-readiness", "a mixed worktree needs to be split into one runtime PR and one detector-lab PR"),
    ("test-strategy-review", "detector-lab tests feel over-specific and need a trim pass"),
    ("test-strategy-review", "a test file has many small threshold cases that may be better merged into parameterized coverage"),
    ("dependency-change-review", "`pyproject.toml` and `uv.lock` changed during harness work and it is unclear whether they belong"),
    ("dependency-change-review", "a code-only branch picked up dependency-file noise after local installs"),
    ("summarization", "a detector-lab refactor needs a short explanation of the new family split and whether behavior changed"),
    ("summarization", "a harness branch needs a PR-ready summary that includes docs and tests but avoids a file-by-file dump"),
    ("branch-pr-readiness", "a workflow branch has passing focused tests but unclear commit, docs, or cleanup readiness"),
    ("branch-pr-readiness", "a stacked PR sequence merged remotely and the final branch needs a clear merge-readiness summary"),
    ("branch-pr-readiness", "docs and tests changed only because the branch widened and now may need to move with different code"),
    ("docs-alignment", "`practical_alerts.py` docstrings no longer match the newer evaluation-context shape"),
    ("docs-alignment", "a production runtime module docstring still sounds dict-shaped after typed-row refactors"),
    ("fixture-environment-safety", "a detector-lab test unexpectedly depends on local baseline clips that are not committed"),
    ("fixture-environment-safety", "an HTTP/HLS test fails only because local sockets are unavailable in the environment"),
    ("frontend-bridge-review", "a session-polling hook change may have blurred renderer versus bridge responsibilities"),
    ("frontend-bridge-review", "a preload contract change needs review for normalization drift and test gaps"),
    ("manual-validation-planner", "before merge, what should I click locally after touching playback status and alert rendering?"),
    ("manual-validation-planner", "a FastAPI share-mode change needs a small manual smoke plan rather than a full release checklist"),
    ("detector-rule-review", "a blur-rule refactor needs review for behavior risk and test gaps"),
    ("detector-rule-review", "`detector_lab` motion-blur work may be drifting toward production responsibilities"),
    ("test-strategy-review", "a blur-rule tweak needs `test-alert-rules` rather than the whole suite"),
    ("test-strategy-review", "an HLS loader change should use `test-hls` before `ci-local`"),
    ("task-planning-evaluation", "deciding whether to work on detectors, CI, harness, or docs next"),
    ("task-planning-evaluation", "building a 2-week versus 2-month project roadmap"),
    ("docs-alignment", "the harness commands changed and the README plus testing guide no longer match"),
    ("docs-alignment", "CI lane ownership changed and the maintainer docs still describe the old shape"),
    ("docs-drift-check", "a README section is shorter than the maintainer docs and we need to know whether that is real drift"),
    ("docs-drift-check", "a FastAPI auth doc may now describe the wrong protected boundary after route changes"),
("architecture-diagram-review", "a worker arrow may look like a data relationship instead of execution flow"),
("architecture-diagram-review", "a README architecture diagram may now blur Electron, FastAPI, and detached-worker ownership"),
    ("readme-alignment-review", "a root README workflow section feels too heavy and may need to shrink and point to deeper docs"),
    ("readme-alignment-review", "the root README may now overstate project maturity after a runtime boundary refactor"),
    ("branch-pr-readiness", "a branch started as real-media hardening but now also carries detector-lab and CI work"),
    ("branch-pr-readiness", "two stacked PRs were merged remotely and it is unclear what can now be deleted"),
    ("ci-failure-triage", "`backend-tests` fails after detector or alert-rule changes"),
    ("ci-failure-triage", "`feature-gate` is red even though only one leaf check actually matters"),
    ("incident-timeline", "session starts but UI falls back to idle"),
    ("incident-timeline", "branch protection / CI merge incidents"),
    ("root-cause-suggestion", "session start succeeded but first read 404s"),
    ("root-cause-suggestion", "PR is green but merge remains blocked"),
]

# Prompts that could plausibly fit two nearby skills, but should still resolve
# to one clear owner.
def _bidirectional_boundary_cases(
    left_skill: str,
    left_summary: str,
    left_required: tuple[str, ...],
    right_required: tuple[str, ...],
    right_skill: str,
    right_summary: str,
) -> list[tuple[str, str, tuple[str, ...], tuple[str, ...]]]:
    """Keep paired skill-boundary expectations compact and symmetric."""
    return [
        (
            left_skill,
            left_summary,
            left_required,
            right_required,
        ),
        (
            right_skill,
            right_summary,
            right_required,
            left_required,
        ),
    ]


AMBIGUOUS_BOUNDARY_EXPECTATIONS = [
    (
        "summarization",
        "branch summary versus branch readiness",
        (
            "What changed",
            "Behavior impact",
        ),
        (
            "Recommended PR shape",
            "Readiness summary",
        ),
    ),
    (
        "branch-pr-readiness",
        "branch shaping versus change summary",
        (
            "Recommended PR shape",
            "Drift assessment",
        ),
        (
            "Behavior impact",
            "Best concise framing",
        ),
    ),
    (
        "test-strategy-review",
        "automated validation versus manual smoke path",
        (
            "Best first command",
            "Why this lane fits",
        ),
        (
            "What to click/run",
            "Best local flow",
        ),
    ),
    (
        "manual-validation-planner",
        "manual smoke path versus automated validation",
        (
            "What to click/run",
            "Best local flow",
        ),
        (
            "Best first command",
            "Why this lane fits",
        ),
    ),
    (
        "docs-drift-check",
        "docs drift audit versus docs editing",
        (
            "Drift class",
            "Severity",
        ),
        (
            "Recommended updates",
            "Smallest useful rewrite",
        ),
    ),
    (
        "architecture-diagram-review",
        "diagram review versus README wording review",
        (
            "Flow arrow review",
            "Boundary review",
        ),
        (
            "README fit",
            "Smallest useful rewrite",
        ),
    ),
]
AMBIGUOUS_BOUNDARY_EXPECTATIONS += _bidirectional_boundary_cases(
    "docs-drift-check",
    "docs drift audit versus docs editing",
    (
        "Drift class",
        "Severity",
    ),
    (
        "Recommended updates",
        "Best next doc pass",
    ),
    "docs-alignment",
    "docs editing versus docs drift audit",
)
AMBIGUOUS_BOUNDARY_EXPECTATIONS += _bidirectional_boundary_cases(
    "readme-alignment-review",
    "README wording review versus diagram review",
    (
        "README fit",
        "Heavy-section warning",
    ),
    (
        "Flow arrow review",
        "Boundary review",
    ),
    "architecture-diagram-review",
    "diagram review versus README wording review",
)
AMBIGUOUS_BOUNDARY_EXPECTATIONS += _bidirectional_boundary_cases(
    "ci-failure-triage",
    "CI failure classification versus likely underlying cause",
    (
        "Most likely failure class",
        "Smallest local reproduction",
    ),
    (
        "Most likely root cause",
        "Cheapest next validation",
    ),
    "root-cause-suggestion",
    "likely underlying cause versus CI failure classification",
)

# High-value handoffs that should stay explicit instead of being implied.
EXPLICIT_HANDOFF_EXPECTATIONS = [
    (
        "frontend-bridge-review",
        "use `manual-validation-planner` next",
    ),
    (
        "alert-backend-parity-review",
        "use `security-surface-review` first",
    ),
    (
        "ci-failure-triage",
        "use `test-strategy-review` next",
    ),
]

# Markers that protect recently merged skill families from collapsing back into
# one ambiguous mode.
MERGED_SKILL_MODE_MARKERS = [
    (
        "summarization",
        (
            "What it is",
            "Behavior impact",
            "Best concise framing",
        ),
    ),
    (
        "branch-pr-readiness",
        (
            "Drift assessment",
            "Recommended commit shape",
            "Readiness summary",
        ),
    ),
    (
        "test-strategy-review",
        (
            "Gap",
            "Strong tests",
            "Best first command",
        ),
    ),
]


def assert_all_snippets_present(text: str, snippets: tuple[str, ...]) -> None:
    """Keep repeated positive snippet checks easy to read."""
    for snippet in snippets:
        assert snippet in text


def assert_all_snippets_absent(text: str, snippets: tuple[str, ...]) -> None:
    """Keep repeated negative snippet checks easy to read."""
    for snippet in snippets:
        assert snippet not in text

SNAPSHOT_EXPECTATIONS = [
    SnapshotExpectation(
        skill_name="alert-backend-parity-review",
        snapshot_name="alert_backend_parity_review_store.md",
        required_order=(
            "Parity surface:",
            "What should stay the same:",
            "Main parity risk:",
            "Current confidence:",
            "Best next check:",
        ),
    ),
    SnapshotExpectation(
        skill_name="security-surface-review",
        snapshot_name="security_surface_review_share_mode.md",
        required_order=(
            "Security surface:",
            "Current protection:",
            "Main risk:",
            "Best next hardening step:",
            "What is intentionally out of scope:",
        ),
    ),
    SnapshotExpectation(
        skill_name="branch-pr-readiness",
        snapshot_name="commit_pr_shaping_harness.md",
        required_order=(
            "Branch story:",
            "Recommended commit shape:",
            "Recommended PR shape:",
            "What should stay out:",
            "Best next step:",
        ),
    ),
    SnapshotExpectation(
        skill_name="test-strategy-review",
        snapshot_name="test_quality_review_detector_lab.md",
        required_order=(
            "Strong tests:",
            "Weak or low-value tests:",
            "Main risk:",
            "Best cleanup:",
            "What not to cut:",
        ),
    ),
    SnapshotExpectation(
        skill_name="dependency-change-review",
        snapshot_name="dependency_change_review_harness.md",
        required_order=(
            "Changed dependency files:",
            "Most likely classification:",
            "Why it belongs or does not belong:",
            "Best next action:",
            "Validation or follow-up:",
        ),
    ),
    SnapshotExpectation(
        skill_name="summarization",
        snapshot_name="change_summary_harness.md",
        required_order=(
            "What changed:",
            "Why it matters:",
            "Behavior impact:",
            "Validation:",
            "Best concise framing:",
        ),
    ),
    SnapshotExpectation(
        skill_name="branch-pr-readiness",
        snapshot_name="release_merge_readiness_harness.md",
        required_order=(
            "Readiness summary:",
            "What looks solid:",
            "Open risks:",
            "Missing checks:",
            "Cleanup before merge:",
            "Recommended next step:",
        ),
    ),
    SnapshotExpectation(
        skill_name="fixture-environment-safety",
        snapshot_name="fixture_environment_safety_local_media.md",
        required_order=(
            "Risk summary:",
            "Environment dependency:",
            "CI safety assessment:",
            "Best fix shape:",
            "Cheapest validation:",
        ),
    ),
    SnapshotExpectation(
        skill_name="manual-validation-planner",
        snapshot_name="manual_validation_planner_playback_alerts.md",
        required_order=(
            "Validation target:",
            "Best local flow:",
            "What to click/run:",
            "What to watch for:",
            "Failure signal:",
            "Best follow-up automation:",
        ),
    ),
    SnapshotExpectation(
        skill_name="frontend-bridge-review",
        snapshot_name="frontend_bridge_review_polling.md",
        required_order=(
            "Findings:",
            "Ownership assessment:",
            "UI/runtime impact:",
            "Missing confidence:",
            "Suggested follow-up:",
        ),
    ),
    SnapshotExpectation(
        skill_name="detector-rule-review",
        snapshot_name="detector_rule_review_blur.md",
        required_order=(
            "Findings:",
            "Boundary assessment:",
            "Missing confidence:",
            "Suggested follow-up:",
        ),
    ),
    SnapshotExpectation(
        skill_name="test-strategy-review",
        snapshot_name="local_validation_selector_hls.md",
        required_order=(
            "Change area:",
            "Best first command:",
            "Why this lane fits:",
            "When to run something broader:",
            "Next broader option:",
        ),
    ),
    SnapshotExpectation(
        skill_name="task-planning-evaluation",
        snapshot_name="task_planning_harness.md",
        required_order=(
            "Task:",
            "Importance:",
            "Urgency:",
            "Scope:",
            "Complexity:",
            "Why it matters now:",
            "Recommended phase:",
            "Best next step:",
        ),
    ),
    SnapshotExpectation(
        skill_name="docs-alignment",
        snapshot_name="docs_alignment_harness.md",
        required_order=(
            "Drift summary:",
            "Owning docs:",
            "Recommended updates:",
            "Repetition to remove:",
            "Best next doc pass:",
        ),
    ),
    SnapshotExpectation(
        skill_name="docs-alignment",
        snapshot_name="code_docs_alignment_runtime_row.md",
        required_order=(
            "Docstring drift:",
            "Owning code surface:",
            "Recommended updates:",
            "Low-value wording to remove:",
            "Best next code-doc pass:",
        ),
    ),
    SnapshotExpectation(
        skill_name="docs-drift-check",
        snapshot_name="docs_drift_check_workflow.md",
        required_order=(
            "Drift target:",
            "Current accuracy:",
            "Drift class:",
            "Severity:",
            "Owning doc:",
            "Smallest useful fix:",
            "What should move with it:",
        ),
    ),
    SnapshotExpectation(
        skill_name="architecture-diagram-review",
        snapshot_name="architecture_diagram_review_runtime_flow.md",
        required_order=(
            "Diagram rating:",
            "Visual quality:",
            "What matches well:",
            "Flow arrow review:",
            "Boundary review:",
            "Arrow-origin check:",
            "Arrow-end check:",
            "Stage honesty:",
            "Biggest mismatch:",
            "Smallest useful fixes:",
        ),
    ),
    SnapshotExpectation(
        skill_name="readme-alignment-review",
        snapshot_name="readme_alignment_review_root_section.md",
        required_order=(
            "Section:",
            "Rating:",
            "What works:",
            "README fit:",
            "Stage honesty:",
            "Heavy-section warning:",
            "Smallest useful rewrite:",
        ),
    ),
    SnapshotExpectation(
        skill_name="branch-pr-readiness",
        snapshot_name="branch_hygiene_stacked_pr.md",
        required_order=(
            "Branch purpose:",
            "Drift assessment:",
            "Most likely branch shape:",
            "Recommended PR shape:",
            "Merged-vs-main state:",
            "Safe cleanup actions:",
            "Best next step:",
        ),
    ),
    SnapshotExpectation(
        skill_name="ci-failure-triage",
        snapshot_name="ci_failure_triage_backend_tests.md",
        required_order=(
            "Failing checks:",
            "Most likely failure class:",
            "Owning boundary:",
            "Evidence for it:",
            "Evidence against it:",
            "Smallest local reproduction:",
            "Best next fix:",
        ),
    ),
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
        skill_name="test-strategy-review",
        snapshot_name="test_coverage_gaps_bridge_contract.md",
        required_order=(
            "Gap:",
            "Why it matters:",
            "Best test layer:",
            "Recommended lane:",
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
            "alert-backend-parity-review",
            [
                "use `ci-failure-triage` first",
                "use `security-surface-review` first",
                "use `test-strategy-review` first",
                "use `branch-pr-readiness` first",
            ],
        ),
        (
            "fastapi-mcp-security-review",
            [
                "use `security-surface-review` first",
                "use `ci-failure-triage` first",
                "use `docs-alignment` first",
                "use `branch-pr-readiness` first",
            ],
        ),
        (
            "security-surface-review",
            [
                "use `ci-failure-triage` first",
                "use `task-planning-evaluation` first",
                "use `docs-alignment` first",
            ],
        ),
        (
            "branch-pr-readiness",
            [
                "use `incident-timeline` first",
                "use `ci-failure-triage` first",
                "use `test-strategy-review` first",
                "use `test-strategy-review` next",
                "use `dependency-change-review` first",
            ],
        ),
        (
            "test-strategy-review",
            [
                "use `summarization` or `incident-timeline` first",
                "use `ci-failure-triage` first",
                "use `branch-pr-readiness` first",
            ],
        ),
        (
            "dependency-change-review",
            [
                "use `branch-pr-readiness` first",
                "use `ci-failure-triage` first",
            ],
        ),
        (
            "fixture-environment-safety",
            [
                "use `test-strategy-review`",
                "use `ci-failure-triage` first",
                "use `test-strategy-review` next",
            ],
        ),
        (
            "detector-rule-review",
            [
                "use `test-strategy-review`",
                "use `test-strategy-review` first",
                "use `task-planning-evaluation`",
            ],
        ),
        (
            "test-strategy-review",
            [
                "use `summarization` or `incident-timeline` first",
                "use `ci-failure-triage` first",
                "use `branch-pr-readiness` first",
            ],
        ),
        (
            "task-planning-evaluation",
            [
                "use `branch-pr-readiness` first",
                "use `test-strategy-review` first",
                "use `docs-alignment` first",
            ],
        ),
        (
            "docs-alignment",
            [
                "use `ci-failure-triage` first",
                "use `summarization` or `incident-timeline` first",
                "use `test-strategy-review` next",
            ],
        ),
        (
            "manual-validation-planner",
            [
                "use `test-strategy-review` first",
                "use `branch-pr-readiness` first",
                "use `incident-timeline` first",
                "use `ci-failure-triage` first",
            ],
        ),
        (
            "frontend-bridge-review",
            [
                "use `test-strategy-review` first",
                "use `incident-timeline` first",
                "use `manual-validation-planner` next",
                "use `ci-failure-triage` first",
                "use `detector-rule-review` first",
            ],
        ),
        (
            "ci-failure-triage",
            [
                "use `incident-timeline` first",
                "hand off to `root-cause-suggestion`",
                "use `test-strategy-review` next",
            ],
        ),
        (
            "summarization",
            [
                "Use `branch-pr-readiness` first",
                "Use `docs-alignment` first",
                "Use `incident-timeline`",
                "Use `root-cause-suggestion`",
                "Use `test-strategy-review`",
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
            "test-strategy-review",
            [
                "use `summarization` or `incident-timeline` first",
                "use `ci-failure-triage` first",
                "use `branch-pr-readiness` first",
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
    assert list_skill_files() == [
        SKILLS_ROOT.joinpath("alert-backend-parity-review", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("architecture-diagram-review", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("branch-pr-readiness", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("ci-failure-triage", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("dependency-change-review", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("detector-rule-review", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("docs-alignment", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("docs-drift-check", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("fastapi-mcp-security-review", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("fixture-environment-safety", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("frontend-bridge-review", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("incident-timeline", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("manual-validation-planner", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("persistence-backend-review", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("readme-alignment-review", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("root-cause-suggestion", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("security-surface-review", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("summarization", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("task-planning-evaluation", "SKILL.md").relative_to(SKILLS_ROOT),
        SKILLS_ROOT.joinpath("test-strategy-review", "SKILL.md").relative_to(SKILLS_ROOT),
    ]
