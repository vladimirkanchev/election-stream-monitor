"""Expectation tables for deterministic repo-skill tests.

This module keeps inventory, routing, scenario, and snapshot expectations out
of the assertion file so the skill harness stays readable as the local skill
set grows.
"""

from __future__ import annotations

from pathlib import Path

from tests.skill_test_support import ScenarioExpectation, SnapshotExpectation

EXPECTED_SKILL_ORDER = (
    "branch-pr-readiness",
    "ci-failure-triage",
    "dependency-change-review",
    "detector-rule-review",
    "docs-alignment",
    "docs-drift-check",
    "fastapi-mcp-security-review",
    "fixture-environment-safety",
    "frontend-bridge-review",
    "incident-analysis",
    "manual-validation-planner",
    "persistence-backend-review",
    "readme-alignment-review",
    "real-media-validation-review",
    "release-version-readiness",
    "summarization",
    "task-planning-evaluation",
    "test-strategy-review",
)

EXPECTED_SKILLS = set(EXPECTED_SKILL_ORDER)

ARCHIVED_SKILL_REACTIVATION_SNIPPETS = (
    "./.agents/archived-skills/",
    "`architecture-diagram-review` for concrete architecture-diagram work",
    "`postgres-migration-rollout-review` before PostgreSQL migration or cloud",
    "`security-surface-review` before broad trust review or public exposure",
)

DISCOVERY_DESCRIPTION_EXPECTATIONS = {
    "branch-pr-readiness": (
        "branch scope",
        ("generic summaries", "test selection"),
    ),
    "ci-failure-triage": (
        "CI check",
        ("general incident analysis",),
    ),
    "dependency-change-review": (
        "dependency metadata",
        ("supply-chain review", "package-upgrade planning"),
    ),
    "detector-rule-review": (
        "production detector",
        ("broad test selection", "real-media lane choice"),
    ),
    "docs-alignment": (
        "docs or docstring",
        ("pre-edit drift audits", "test planning"),
    ),
    "docs-drift-check": (
        "documentation drift audits",
        ("direct doc editing", "README fit", "test planning"),
    ),
    "fastapi-mcp-security-review": (
        "share mode",
        ("broad trust review", "deployment design"),
    ),
    "fixture-environment-safety": (
        "test fixture",
        ("detector confidence", "real-media assertion review"),
    ),
    "frontend-bridge-review": (
        "renderer",
        ("manual smoke planning", "general test selection"),
    ),
    "incident-analysis": (
        "timeline reconstruction",
        ("first-pass CI triage", "generic summaries"),
    ),
    "manual-validation-planner": (
        "local smoke plans",
        ("automated test selection", "CI triage"),
    ),
    "persistence-backend-review": (
        "persistence parity",
        ("access-policy hardening", "broad database design"),
    ),
    "readme-alignment-review": (
        "root README fit",
        ("repo-wide docs drift", "test planning"),
    ),
    "real-media-validation-review": (
        "real-media",
        ("fixture portability", "broad automated test selection"),
    ),
    "release-version-readiness": (
        "version-change semantics",
        ("PR merge readiness", "dependency ownership"),
    ),
    "summarization": (
        "concise",
        ("PR shaping", "incident diagnosis", "test strategy"),
    ),
    "task-planning-evaluation": (
        "task priority",
        ("branch or PR shape", "detailed test design"),
    ),
    "test-strategy-review": (
        "test value",
        ("CI-failure diagnosis", "specialist seam review"),
    ),
}

PLANNING_CLOSURE_PROFILE_EXPECTATIONS = {
    "small": (
        "small and obvious",
        "one focused check",
        "inspect the diff",
        "refactoring and docs",
        "alignment apply only when they are genuinely needed",
        "brief reason when",
        "skipping a closure phase",
    ),
    "standard": (
        "standard: implement",
        "validate the focused seam",
        "refactor touched code",
        "align changed behavior",
        "review branch shape",
        "cheapest honest final validation",
    ),
    "high-risk": (
        "high-risk: record a baseline",
        "staged validation",
        "before the standard",
    ),
}

PLANNING_CLOSURE_SPECIALISTS = (
    "`test-strategy-review`",
    "`docs-alignment`",
    "`branch-pr-readiness`",
)

COMMON_SECTIONS = (
    "## Default approach",
    "## Output shape",
    "## Avoid",
)

SCENARIO_EXPECTATIONS = [
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
        skill_name="persistence-backend-review",
        required_snippets=(
            "Alert-parity mode",
            "raw alert reads",
            "incident grouping",
            "FastAPI/MCP",
            "share-mode",
        ),
    ),
    ScenarioExpectation(
        skill_name="fastapi-mcp-security-review",
        required_snippets=(
            "Checklist gaps",
            "branch-scoped",
            "share mode",
            "MCP tool exposure",
            "dependency exposure",
            "Best validation lane",
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
        skill_name="real-media-validation-review",
        required_snippets=(
            "Fixture reality",
            "Flaky or environment-sensitive risk",
            "Best confidence lane",
            "docs honesty",
            "`just test-real-media`",
        ),
    ),
    ScenarioExpectation(
        skill_name="release-version-readiness",
        required_snippets=(
            "Current base version",
            "Recommended version",
            "Why not smaller",
            "What must be true first",
            "opt-in adapter",
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
            "current local-first pilot stage",
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
            "follow-up branch",
            "focused evidence",
            "one coherent PR",
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
        skill_name="incident-analysis",
        required_snippets=(
            "Timeline mode",
            "Observed facts",
            "Reconstructed sequence",
            "first session snapshot persisted",
            "Frontend events",
            "Terminal state",
        ),
    ),
    ScenarioExpectation(
        skill_name="incident-analysis",
        required_snippets=(
            "Hypothesis mode",
            "Most likely root cause",
            "GitHub policy/state",
            "Cheapest next validation",
        ),
    ),
]

REAL_INCIDENT_REGRESSIONS = [
    ("persistence-backend-review", "a session-alert store refactor changed file/PostgreSQL grouped-incident behavior"),
    ("persistence-backend-review", "an alerts-router auth change touched store parity or only access policy"),
    ("persistence-backend-review", "a session-store branch may have changed file versus PostgreSQL snapshot semantics"),
    ("persistence-backend-review", "a detached worker may no longer inherit the same store backend as the parent"),
    ("fastapi-mcp-security-review", "a FastAPI route branch may have widened `share` mode beyond the intended boundary"),
    ("fastapi-mcp-security-review", "an MCP tool update may have drifted outside the read-only local tooling model"),
    ("dependency-change-review", "`pyproject.toml` and `uv.lock` changed during harness work and it is unclear whether they belong"),
    ("dependency-change-review", "a code-only branch picked up dependency-file noise after local installs"),
    ("docs-alignment", "`practical_alerts.py` docstrings no longer match the newer evaluation-context shape"),
    ("docs-alignment", "a production runtime module docstring still sounds dict-shaped after typed-row refactors"),
    ("fixture-environment-safety", "a detector-lab test unexpectedly depends on local baseline clips that are not committed"),
    ("fixture-environment-safety", "an HTTP/HLS test fails only because local sockets are unavailable in the environment"),
    ("frontend-bridge-review", "a session-polling hook change may have blurred renderer versus bridge responsibilities"),
    ("frontend-bridge-review", "a preload contract change needs review for normalization drift and test gaps"),
    ("manual-validation-planner", "before merge, what should I click locally after touching playback status and alert rendering?"),
    ("manual-validation-planner", "a FastAPI share-mode change needs a small manual smoke plan rather than a full release checklist"),
    ("real-media-validation-review", "a remote HLS confidence test may now be too flaky for routine PR validation"),
    ("real-media-validation-review", "a stream/file branch may rely on local-only clips that should not be treated like checked-in fixtures"),
    ("release-version-readiness", "a PostgreSQL session-store branch may look big, but the default runtime is still file-backed"),
    ("release-version-readiness", "real-media confidence improvements may justify `0.5.3` but not `0.6.0`"),
    ("detector-rule-review", "a blur-rule refactor needs review for behavior risk and test gaps"),
    ("detector-rule-review", "`detector_lab` motion-blur work may be drifting toward production responsibilities"),
    ("docs-alignment", "the harness commands changed and the README plus testing guide no longer match"),
    ("docs-alignment", "CI lane ownership changed and the maintainer docs still describe the old shape"),
    ("docs-drift-check", "a README section is shorter than the maintainer docs and we need to know whether that is real drift"),
    ("docs-drift-check", "a FastAPI auth doc may now describe the wrong protected boundary after route changes"),
    ("readme-alignment-review", "a root README workflow section feels too heavy and may need to shrink and point to deeper docs"),
    ("readme-alignment-review", "the root README may now overstate project maturity after a runtime boundary refactor"),
    ("ci-failure-triage", "`backend-tests` fails after detector or alert-rule changes"),
    ("ci-failure-triage", "`feature-gate` is red even though only one leaf check actually matters"),
    ("incident-analysis", "session starts but UI falls back to idle"),
    ("incident-analysis", "branch protection or CI merge state has conflicting signals"),
    ("incident-analysis", "session start succeeded but the first read returned 404"),
    ("incident-analysis", "PR is green but merge remains blocked"),
]


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
    "ci-failure-triage",
    "CI failure classification versus incident hypothesis",
    (
        "Most likely failure class",
        "Smallest local reproduction",
    ),
    (
        "Hypothesis mode",
        "Most likely root cause",
        "Cheapest next validation",
    ),
    "incident-analysis",
    "incident hypothesis versus CI failure classification",
)

BOUNDARY_SNIPPETS_BY_SKILL = [
    (
        "persistence-backend-review",
        [
            "Use `ci-failure-triage` first",
            "Use `fastapi-mcp-security-review` first",
            "Use `test-strategy-review` first",
            "Use `branch-pr-readiness` first",
        ],
    ),
    (
        "fastapi-mcp-security-review",
        [
            "reactivate the archived",
            "use `ci-failure-triage` first",
            "use `docs-alignment` first",
            "use `branch-pr-readiness` first",
        ],
    ),
    (
        "branch-pr-readiness",
        [
            "Own branch scope, commits, PR shape, and merge readiness.",
            "use `incident-analysis` first",
            "use `ci-failure-triage` first",
            "use `test-strategy-review` first",
            "use `test-strategy-review` next",
            "use `dependency-change-review` first",
        ],
    ),
    (
        "test-strategy-review",
        [
            "Own coverage value and the cheapest honest validation.",
            "Use `summarization` or `incident-analysis` first",
            "Use `ci-failure-triage` first",
            "Use `branch-pr-readiness` first",
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
        "task-planning-evaluation",
        [
            "Own prioritization, sequencing, and proportional closure.",
            "Use `branch-pr-readiness` first",
            "Use `test-strategy-review` first",
            "Use `docs-alignment` first",
        ],
    ),
    (
        "docs-alignment",
        [
            "use `ci-failure-triage` first",
            "use `summarization` or `incident-analysis` first",
            "use `test-strategy-review` next",
        ],
    ),
    (
        "manual-validation-planner",
        [
            "use `test-strategy-review` first",
            "use `branch-pr-readiness` first",
            "use `incident-analysis` first",
            "use `ci-failure-triage` first",
        ],
    ),
    (
        "real-media-validation-review",
        [
            "use `fixture-environment-safety` first",
            "use `test-strategy-review` first",
            "use `manual-validation-planner` first",
            "use `branch-pr-readiness` first",
        ],
    ),
    (
        "release-version-readiness",
        [
            "use `branch-pr-readiness` first",
            "use `summarization` first",
            "use `task-planning-evaluation` first",
            "use `dependency-change-review` first",
        ],
    ),
    (
        "frontend-bridge-review",
        [
            "use `test-strategy-review` first",
            "use `incident-analysis` first",
            "use `manual-validation-planner` next",
            "use `ci-failure-triage` first",
            "use `detector-rule-review` first",
        ],
    ),
    (
        "ci-failure-triage",
        [
            "use `incident-analysis` next",
            "use `test-strategy-review` next",
        ],
    ),
    (
        "summarization",
        [
            "Own concise repository and completed-change summaries.",
            "Use `branch-pr-readiness` first",
            "Use `docs-alignment` first",
            "Use `incident-analysis`",
            "Use `test-strategy-review`",
        ],
    ),
    (
        "incident-analysis",
        [
            "Use `ci-failure-triage` first",
            "Use `summarization` for a generic repository or change summary",
        ],
    ),
]

EXPLICIT_HANDOFF_EXPECTATIONS = [
    (
        "frontend-bridge-review",
        "use `manual-validation-planner` next",
    ),
    (
        "persistence-backend-review",
        "Use `fastapi-mcp-security-review` first",
    ),
    (
        "ci-failure-triage",
        "use `test-strategy-review` next",
    ),
]

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
    (
        "incident-analysis",
        (
            "Timeline mode",
            "Hypothesis mode",
            "Cheapest next validation",
        ),
    ),
    (
        "release-version-readiness",
        (
            "Current base version",
            "Recommended version",
            "What must be true first",
        ),
    ),
]

SNAPSHOT_EXPECTATIONS = [
    SnapshotExpectation(
        skill_name="persistence-backend-review",
        snapshot_name="persistence_backend_review_alert_parity.md",
        required_order=(
            "Persistence surface:",
            "Default versus opt-in behavior:",
            "Shared contract risk:",
            "Current confidence:",
            "Best next check:",
        ),
    ),
    SnapshotExpectation(
        skill_name="persistence-backend-review",
        snapshot_name="persistence_backend_review_session_store.md",
        required_order=(
            "Persistence surface:",
            "Default versus opt-in behavior:",
            "Shared contract risk:",
            "Current confidence:",
            "Best next check:",
        ),
    ),
    SnapshotExpectation(
        skill_name="fastapi-mcp-security-review",
        snapshot_name="fastapi_mcp_security_review_share_mode.md",
        required_order=(
            "Security surface:",
            "Current protection:",
            "Checklist gaps:",
            "Best next hardening step:",
            "Best validation lane:",
        ),
    ),
    SnapshotExpectation(
        skill_name="real-media-validation-review",
        snapshot_name="real_media_validation_review_hls_lane.md",
        required_order=(
            "Validation target:",
            "Fixture reality:",
            "Flaky or environment-sensitive risk:",
            "Best confidence lane:",
            "Best next cleanup:",
        ),
    ),
    SnapshotExpectation(
        skill_name="release-version-readiness",
        snapshot_name="release_version_readiness_postgres.md",
        required_order=(
            "Current base version:",
            "Change class:",
            "Recommended version:",
            "Why not smaller:",
            "Why not larger:",
            "What must be true first:",
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
        skill_name="incident-analysis",
        snapshot_name="incident_analysis_timeline_ui_idle.md",
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
        skill_name="incident-analysis",
        snapshot_name="incident_analysis_root_cause_pr_blocked.md",
        required_order=(
            "Most likely root cause:",
            "Confidence:",
            "Evidence for it:",
            "Evidence against it:",
            "Cheapest next validation:",
        ),
    ),
]

RISKY_CHANGE_ROUTING_ORDER = [
    "## Risky Change Routing",
    "session or alert persistence, runtime backend selection, or PostgreSQL migration",
    "`persistence-backend-review`",
    "FastAPI or MCP security, auth, `share` mode, secrets, rate limits, or trust boundaries",
    "`fastapi-mcp-security-review`",
    "real-media, long-running stream, or environment-sensitive validation work",
    "`fixture-environment-safety`",
    "`manual-validation-planner`",
    "detector extension, detector-lab growth, or analyzer/rule ownership changes",
    "`detector-rule-review`",
]

RISKY_CHANGE_ROUTING_REQUIRED_SNIPPETS = (
    "[`docs/contracts.md`](./docs/contracts.md)",
    "[`docs/session-model.md`](./docs/session-model.md)",
    "[`docs/testing-and-validation.md`](./docs/testing-and-validation.md)",
    "[`docs/adding-an-analyzer.md`](./docs/adding-an-analyzer.md)",
    "[`docs/adding-an-alert-rule.md`](./docs/adding-an-alert-rule.md)",
    "prefer one primary skill",
)


def expected_skill_files(skills_root: Path) -> list[Path]:
    """Return the expected ordered skill paths relative to the skills root."""
    return [
        skills_root.joinpath(skill_name, "SKILL.md").relative_to(skills_root)
        for skill_name in EXPECTED_SKILL_ORDER
    ]
