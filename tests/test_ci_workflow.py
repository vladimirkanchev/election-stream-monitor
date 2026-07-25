"""Regression tests for the workflow reader and protected CI contract.

This module keeps three seams honest:
- the small YAML reader used by the workflow checks
- the protected/advisory policy enforced over the live `ci.yml`
- the workflow split that keeps protected PR statuses separate from branch
  push feedback
"""

from __future__ import annotations

from dataclasses import replace
import importlib
from pathlib import Path
import sys
from typing import Any

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

ci_workflow = importlib.import_module("ci_workflow")
ci_workflow_contract = importlib.import_module("ci_workflow_contract")
CI_WORKFLOW_PATH = SCRIPTS_DIR.parent / "workflows" / "ci.yml"
BRANCH_CI_WORKFLOW_PATH = SCRIPTS_DIR.parent / "workflows" / "branch-ci.yml"
WEEKLY_VALIDATION_WORKFLOW_PATH = SCRIPTS_DIR.parent / "workflows" / "weekly-validation.yml"
FRONTEND_INSTALLER_PATH = Path("scripts/install_frontend_dependencies.sh")
FRONTEND_INSTALL_COMMAND = "bash ../scripts/install_frontend_dependencies.sh"
MAIN_GATE_REQUIRED_JOBS = ci_workflow_contract.MAIN_GATE_REQUIRED_JOBS
FEATURE_GATE_REQUIRED_JOBS = ci_workflow_contract.FEATURE_GATE_REQUIRED_JOBS
ADVISORY_JOBS = ci_workflow_contract.ADVISORY_JOBS
REQUIRED_FRONTEND_COMMANDS_BY_JOB = (
    ci_workflow_contract.REQUIRED_FRONTEND_COMMANDS_BY_JOB
)
MAIN_PR_FORCE_ON_CLAUSE = ci_workflow_contract.MAIN_PR_FORCE_ON_CLAUSE
MAIN_ONLY_JOBS = ci_workflow_contract.MAIN_ONLY_JOBS
FORCED_ON_WORK_STEPS = ci_workflow_contract.FORCED_ON_WORK_STEPS
BACKEND_TEST_JOB = ci_workflow_contract.BACKEND_TEST_JOB
BACKEND_TEST_STEP = ci_workflow_contract.BACKEND_TEST_STEP
BACKEND_FAST_SELECTOR = ci_workflow_contract.BACKEND_FAST_SELECTOR
BACKEND_RUFF_STEP = "Run backend Ruff lint"
FRONTEND_BUILD_COMMAND = "npm run build"
FRONTEND_BUILD_STEP = "Run frontend production build"


def _live_workflow() -> Any:
    """Load the current repository workflow through the public reader."""
    return ci_workflow.load_workflow(CI_WORKFLOW_PATH)


def _workflow_text(path: Path) -> str:
    """Return one workflow file as raw text for trigger-shape assertions."""
    return path.read_text()


def _load_text_workflow(tmp_path: Path, text: str) -> Any:
    """Load one temporary workflow fixture through the public reader."""
    workflow_path = tmp_path / "workflow.yml"
    workflow_path.write_text(text)
    return ci_workflow.load_workflow(workflow_path)


def _steps_by_command(workflow: Any, command: str) -> list[tuple[Any, Any]]:
    """Return every job/step pair that runs one exact command."""
    return [
        (job, step)
        for job in workflow.jobs.values()
        for step in job.steps
        if step.command == command
    ]


def _replace_job(workflow: Any, job_name: str, **changes: object) -> Any:
    """Return a workflow with one job immutably replaced."""
    jobs = dict(workflow.jobs)
    jobs[job_name] = replace(jobs[job_name], **changes)
    return replace(workflow, jobs=jobs)


def _remove_job(workflow: Any, job_name: str) -> Any:
    """Return a workflow with one named job removed."""
    jobs = dict(workflow.jobs)
    del jobs[job_name]
    return replace(workflow, jobs=jobs)


def _replace_named_step(job: Any, step_name: str, **changes: object) -> tuple[Any, ...]:
    """Return one job's step tuple with one named step updated."""
    return tuple(
        replace(step, **changes) if step.name == step_name else step
        for step in job.steps
    )


def _replace_job_step(
    workflow: Any,
    job_name: str,
    step_name: str,
    **changes: object,
) -> Any:
    """Return a workflow with one named step updated inside one job."""
    job = workflow.job(job_name)
    return _replace_job(
        workflow,
        job_name,
        steps=_replace_named_step(job, step_name, **changes),
    )


def _remove_job_step(workflow: Any, job_name: str, step_name: str) -> Any:
    """Return a workflow with one named step removed from one job."""
    job = workflow.job(job_name)
    return _replace_job(
        workflow,
        job_name,
        steps=tuple(step for step in job.steps if step.name != step_name),
    )


def _append_step(
    job: Any,
    *,
    name: str,
    command: str,
    **changes: object,
) -> tuple[Any, ...]:
    """Return one job's steps with one extra synthetic step appended."""
    return job.steps + (
        ci_workflow.WorkflowStep(
            name=name,
            condition=changes.get("condition"),
            command=command,
            working_directory=changes.get("working_directory"),
            continue_on_error=changes.get("continue_on_error"),
        ),
    )


def _failure_codes(workflow: Any) -> set[str]:
    """Return the stable failure codes emitted for one mutated workflow."""
    return {
        failure.code
        for failure in ci_workflow_contract.contract_failures(workflow)
    }


def _assert_failure_code(workflow: Any, expected_code: str) -> None:
    """Assert that one mutated workflow produces the expected failure code."""
    assert expected_code in _failure_codes(workflow)


def test_reader_loads_current_ci_job_structure() -> None:
    """The live workflow should expose the expected main-gate structure."""
    workflow = _live_workflow()
    main_gate = workflow.job("main-gate")

    assert main_gate.dependencies
    assert "github.base_ref == 'main'" in main_gate.condition


def test_protected_ci_workflow_is_pull_request_only() -> None:
    """Protected CI should be PR-only so push runs cannot emit `main-gate`."""
    workflow_text = _workflow_text(CI_WORKFLOW_PATH)

    assert "pull_request:" in workflow_text
    assert "branches-ignore:" not in workflow_text.split("jobs:", 1)[0]
    assert "\n  push:" not in workflow_text.split("jobs:", 1)[0]


def test_branch_feedback_workflow_is_push_only() -> None:
    """Branch CI should own ordinary push feedback outside the protected PR lane."""
    workflow_text = _workflow_text(BRANCH_CI_WORKFLOW_PATH)

    assert "name: Branch CI" in workflow_text
    assert "\n  push:" in workflow_text.split("jobs:", 1)[0]
    assert "branches-ignore:" in workflow_text
    assert "pull_request:" not in workflow_text.split("jobs:", 1)[0]


def test_routine_workflows_keep_live_alert_postgres_confidence_disabled() -> None:
    """Routine PR and branch workflows must not start PostgreSQL confidence."""
    for workflow_path in (CI_WORKFLOW_PATH, BRANCH_CI_WORKFLOW_PATH):
        workflow_text = _workflow_text(workflow_path)

        assert "ESM_ALERT_STORE_BACKEND: file" in workflow_text
        assert 'POSTGRES_ALERT_STORE_REAL_SMOKE: "0"' in workflow_text
        assert "services:" not in workflow_text
        assert "postgres_alert_weekly_" not in workflow_text


def test_frontend_workflows_use_the_pinned_retrying_installer() -> None:
    """Every frontend install lane should share the pinned toolchain helper."""

    for workflow_path in (
        CI_WORKFLOW_PATH,
        BRANCH_CI_WORKFLOW_PATH,
        WEEKLY_VALIDATION_WORKFLOW_PATH,
    ):
        workflow = ci_workflow.load_workflow(workflow_path)
        install_steps = [
            step
            for job in workflow.jobs.values()
            for step in job.steps
            if step.name == "Install frontend dependencies"
        ]

        assert install_steps
        assert all(step.command == FRONTEND_INSTALL_COMMAND for step in install_steps)

    installer = FRONTEND_INSTALLER_PATH.read_text()
    assert 'REQUIRED_NPM_VERSION="11.15.0"' in installer
    assert "npm ci" in installer


def test_weekly_alert_postgres_jobs_keep_their_explicit_live_environment() -> None:
    """Scheduled/manual validation must retain both isolated live-alert jobs."""
    workflow_text = _workflow_text(WEEKLY_VALIDATION_WORKFLOW_PATH)
    backend_job = workflow_text.split(
        "  postgres-alert-backend-confidence:", 1
    )[1].split("  postgres-alert-runtime-operator-confidence:", 1)[0]
    runtime_job = workflow_text.split(
        "  postgres-alert-runtime-operator-confidence:", 1
    )[1]

    assert "  schedule:" in workflow_text
    assert "  workflow_dispatch:" in workflow_text

    for job_text in (backend_job, runtime_job):
        assert "services:\n      postgres:" in job_text
        assert "image: postgres:16" in job_text
        assert (
            "ESM_POSTGRES_ALERT_DATABASE_URL: "
            "postgresql://postgres:postgres@localhost:5432/election_stream_monitor"
        ) in job_text
        assert "ESM_ALERT_STORE_BACKEND: postgres" in job_text
        assert 'POSTGRES_ALERT_STORE_REAL_SMOKE: "1"' in job_text


def test_current_ci_workflow_satisfies_complete_contract() -> None:
    """The live workflow should pass the full protected/advisory contract."""
    workflow = _live_workflow()

    assert ci_workflow_contract.contract_failures(workflow) == ()


def test_workflow_contract_tests_remain_in_protected_backend_discovery() -> None:
    """The backend fast lane should still discover the workflow tests broadly."""
    workflow = _live_workflow()
    backend_test_step = workflow.job(BACKEND_TEST_JOB).step(BACKEND_TEST_STEP)

    assert backend_test_step.command is not None
    assert BACKEND_FAST_SELECTOR in backend_test_step.command
    assert "tests/" not in backend_test_step.command
    assert MAIN_PR_FORCE_ON_CLAUSE in (backend_test_step.condition or "")


def test_main_gate_requires_exact_protected_job_set() -> None:
    """`main-gate` should keep its exact protected direct dependencies."""
    workflow = _live_workflow()

    assert (
        frozenset(workflow.job("main-gate").dependencies)
        == MAIN_GATE_REQUIRED_JOBS
    )


def test_feature_gate_requires_exact_protected_job_set() -> None:
    """`feature-gate` should keep its exact protected direct dependencies."""
    workflow = _live_workflow()

    assert (
        frozenset(workflow.job("feature-gate").dependencies)
        == FEATURE_GATE_REQUIRED_JOBS
    )


@pytest.mark.parametrize("job_name", sorted(ADVISORY_JOBS))
def test_advisory_jobs_remain_present_and_non_blocking(job_name: str) -> None:
    """Each advisory job should still exist and stay non-blocking."""
    workflow = _live_workflow()

    assert workflow.job(job_name).continue_on_error is True


def test_advisory_jobs_are_not_aggregate_gate_dependencies() -> None:
    """Advisory jobs should not appear in either aggregate gate."""
    workflow = _live_workflow()
    aggregate_dependencies = {
        *workflow.job("feature-gate").dependencies,
        *workflow.job("main-gate").dependencies,
    }

    assert ADVISORY_JOBS.isdisjoint(aggregate_dependencies)


def test_contract_checks_job_is_forced_on_for_main_prs() -> None:
    """`contract-checks` should still be forced on for `main` pull requests."""
    workflow = _live_workflow()
    condition = workflow.job("contract-checks").condition

    assert condition is not None
    assert "github.event_name == 'pull_request'" in condition
    assert "github.base_ref == 'main'" in condition


@pytest.mark.parametrize("job_name", sorted(MAIN_ONLY_JOBS))
def test_main_only_jobs_require_a_main_pull_request(job_name: str) -> None:
    """Main-only jobs should keep their explicit `main` PR condition."""
    workflow = _live_workflow()
    condition = workflow.job(job_name).condition

    assert condition is not None
    assert MAIN_PR_FORCE_ON_CLAUSE in condition


@pytest.mark.parametrize(
    ("job_name", "step_name"),
    (
        (job_name, step_name)
        for job_name, step_names in FORCED_ON_WORK_STEPS.items()
        for step_name in step_names
    ),
)
def test_required_work_steps_are_forced_on_for_main_prs(
    job_name: str,
    step_name: str,
) -> None:
    """Protected work steps should keep their `main` PR force-on condition."""
    workflow = _live_workflow()
    condition = workflow.job(job_name).step(step_name).condition

    assert condition is not None
    assert MAIN_PR_FORCE_ON_CLAUSE in condition


@pytest.mark.parametrize(
    "command",
    REQUIRED_FRONTEND_COMMANDS_BY_JOB["test-and-build"],
)
def test_full_frontend_validation_stays_in_protected_main_lane(
    command: str,
) -> None:
    """Full frontend validation should stay in the protected `test-and-build` lane."""
    workflow = _live_workflow()
    command_owners = _steps_by_command(workflow, command)

    assert len(command_owners) == 1
    job, step = command_owners[0]
    assert job.name == "test-and-build"
    assert job.continue_on_error in (None, False)
    assert step.continue_on_error in (None, False)
    assert step.working_directory == "frontend"
    assert step.condition is not None
    assert MAIN_PR_FORCE_ON_CLAUSE in step.condition


def test_contract_checker_detects_removed_main_gate_dependency() -> None:
    """Removing a required `main-gate` dependency should be reported."""
    workflow = _live_workflow()
    main_gate = workflow.job("main-gate")
    mutated = _replace_job(
        workflow,
        "main-gate",
        dependencies=tuple(
            dependency
            for dependency in main_gate.dependencies
            if dependency != "contract-checks"
        ),
    )

    _assert_failure_code(mutated, "main-gate-dependencies")


def test_contract_checker_detects_deleted_protected_job() -> None:
    """Deleting a required protected job should be reported."""
    mutated = _remove_job(_live_workflow(), "backend-ruff")

    _assert_failure_code(mutated, "required-job-missing")


def test_contract_checker_detects_removed_protected_step_name() -> None:
    """Removing a required protected step should be reported."""
    mutated = _remove_job_step(_live_workflow(), "backend-ruff", BACKEND_RUFF_STEP)

    _assert_failure_code(mutated, "required-step-missing")


def test_contract_checker_detects_removed_frontend_build_command() -> None:
    """Removing the protected frontend build command should be reported."""
    workflow = _live_workflow()
    job = workflow.job("test-and-build")
    mutated = _replace_job(
        workflow,
        "test-and-build",
        steps=tuple(
            step for step in job.steps if step.command != FRONTEND_BUILD_COMMAND
        ),
    )

    _assert_failure_code(mutated, "frontend-command-missing")


def test_contract_checker_detects_frontend_command_moving_to_the_wrong_job() -> None:
    """Moving frontend build into the wrong job should be reported."""
    workflow = _live_workflow()
    frontend_checkpoint = workflow.job("frontend-checkpoint")

    mutated = _replace_job_step(
        workflow,
        "test-and-build",
        FRONTEND_BUILD_STEP,
        command="npm run build:web",
    )
    mutated = _replace_job(
        mutated,
        "frontend-checkpoint",
        steps=_append_step(
            frontend_checkpoint,
            name="Synthetic frontend production build",
            command=FRONTEND_BUILD_COMMAND,
            condition=MAIN_PR_FORCE_ON_CLAUSE,
            working_directory="frontend",
        ),
    )

    _assert_failure_code(mutated, "frontend-command-owner")


def test_contract_checker_detects_duplicated_frontend_build_command_owner() -> None:
    """Duplicating a protected frontend command owner should be reported."""
    workflow = _live_workflow()
    frontend_checkpoint = workflow.job("frontend-checkpoint")
    mutated = _replace_job(
        workflow,
        "frontend-checkpoint",
        steps=_append_step(
            frontend_checkpoint,
            name="Duplicate frontend production build",
            command=FRONTEND_BUILD_COMMAND,
            condition=MAIN_PR_FORCE_ON_CLAUSE,
            working_directory="frontend",
        ),
    )

    _assert_failure_code(mutated, "frontend-command-duplicated")


def test_contract_checker_detects_frontend_command_becoming_advisory() -> None:
    """Turning a protected frontend command advisory should be reported."""
    mutated = _replace_job_step(
        _live_workflow(),
        "test-and-build",
        FRONTEND_BUILD_STEP,
        continue_on_error=True,
    )

    _assert_failure_code(mutated, "frontend-command-advisory")


def test_contract_checker_detects_frontend_command_leaving_frontend_directory() -> None:
    """Changing the frontend command working directory should be reported."""
    mutated = _replace_job_step(
        _live_workflow(),
        "test-and-build",
        FRONTEND_BUILD_STEP,
        working_directory=".",
    )

    _assert_failure_code(mutated, "frontend-command-directory")


def test_contract_checker_detects_frontend_command_losing_main_pr_force_on() -> None:
    """Dropping the `main` PR force-on condition should be reported."""
    mutated = _replace_job_step(
        _live_workflow(),
        "test-and-build",
        FRONTEND_BUILD_STEP,
        condition="needs.changes.outputs.frontend == 'true'",
    )

    _assert_failure_code(mutated, "main-force-on-missing")


def test_contract_checker_detects_removed_main_force_on_condition() -> None:
    """Removing force-on from a protected step should be reported."""
    mutated = _replace_job_step(
        _live_workflow(),
        "backend-ruff",
        BACKEND_RUFF_STEP,
        condition=None,
    )

    _assert_failure_code(mutated, "main-force-on-missing")


def test_contract_checker_detects_advisory_job_becoming_blocking() -> None:
    """Promoting an advisory job to blocking should be reported."""
    mutated = _replace_job(
        _live_workflow(),
        "frontend-lint",
        continue_on_error=False,
    )

    _assert_failure_code(mutated, "advisory-job-blocking")


def test_contract_checker_detects_deleted_advisory_job() -> None:
    """Deleting an advisory job should still be reported."""
    mutated = _remove_job(_live_workflow(), "backend-pyright")

    _assert_failure_code(mutated, "advisory-job-missing")


def test_contract_checker_detects_narrowed_backend_test_discovery() -> None:
    """Narrowing the backend fast test selector should be reported."""
    mutated = _replace_job_step(
        _live_workflow(),
        BACKEND_TEST_JOB,
        BACKEND_TEST_STEP,
        command='pytest -q -m "not e2e and not slow" tests/test_detectors.py',
    )

    _assert_failure_code(mutated, "backend-test-lane")


def test_reader_normalizes_scalar_and_missing_dependencies(tmp_path: Path) -> None:
    """The reader should normalize missing and scalar `needs` values."""
    workflow = _load_text_workflow(
        tmp_path,
        """
jobs:
  first:
    steps: []
  second:
    needs: first
    steps: []
""",
    )

    assert workflow.job("first").dependencies == ()
    assert workflow.job("second").dependencies == ("first",)


def test_reader_preserves_conditions_and_continue_on_error(tmp_path: Path) -> None:
    """The reader should preserve supported condition and advisory fields."""
    workflow = _load_text_workflow(
        tmp_path,
        """
jobs:
  advisory:
    if: github.event_name == 'pull_request'
    continue-on-error: true
    steps:
      - name: Conditional command
        if: github.base_ref == 'main'
        continue-on-error: ${{ matrix.experimental }}
        working-directory: frontend
        run: npm run lint
""",
    )
    job = workflow.job("advisory")
    step = job.step("Conditional command")

    assert job.condition == "github.event_name == 'pull_request'"
    assert job.continue_on_error is True
    assert step.condition == "github.base_ref == 'main'"
    assert step.continue_on_error == "${{ matrix.experimental }}"
    assert step.command == "npm run lint"
    assert step.working_directory == "frontend"


@pytest.mark.parametrize(
    ("workflow_text", "expected_message"),
    (
        ("jobs: [\n", "Could not parse workflow YAML"),
        ("name: CI\n", "field 'jobs' must be a mapping"),
        ("jobs: []\n", "field 'jobs' must be a mapping"),
        (
            "jobs:\n  invalid:\n    needs: [valid, 3]\n",
            "field 'needs' must be a string or string list",
        ),
        (
            "jobs:\n  invalid:\n    steps: command\n",
            "field 'steps' must be a list",
        ),
        (
            "jobs:\n  invalid:\n    steps:\n      - command\n",
            "field 'jobs.invalid.steps\\[0\\]' must be a mapping",
        ),
        (
            "jobs:\n  invalid:\n    if: true\n    steps: []\n",
            "field 'jobs.invalid.if' must be a string",
        ),
        (
            "jobs:\n  invalid:\n    continue-on-error: 1\n    steps: []\n",
            "field 'jobs.invalid.continue-on-error' must be a boolean or expression string",
        ),
        (
            "jobs:\n  invalid:\n    steps:\n      - name: bad-if\n        if: true\n",
            "field 'jobs.invalid.steps\\[0\\].if' must be a string",
        ),
        (
            "jobs:\n  invalid:\n    steps:\n      - name: bad-run\n        run: 7\n",
            "field 'jobs.invalid.steps\\[0\\].run' must be a string",
        ),
        (
            "jobs:\n  invalid:\n    steps:\n      - name: bad-dir\n        working-directory: 5\n",
            "field 'jobs.invalid.steps\\[0\\].working-directory' must be a string",
        ),
        (
            "jobs:\n  invalid:\n    steps:\n      - name: bad-coe\n        continue-on-error: 1\n",
            "field 'jobs.invalid.steps\\[0\\].continue-on-error' must be a boolean or expression string",
        ),
    ),
)
def test_reader_rejects_unsupported_workflow_shapes(
    tmp_path: Path,
    workflow_text: str,
    expected_message: str,
) -> None:
    """Unsupported workflow shapes should fail with readable validation errors."""
    workflow_path = tmp_path / "invalid.yml"
    workflow_path.write_text(workflow_text)

    with pytest.raises(ci_workflow.WorkflowError, match=expected_message):
        ci_workflow.load_workflow(workflow_path)


def test_reader_lookup_errors_name_the_missing_job_or_step() -> None:
    """Lookup errors should name the missing job or step plainly."""
    workflow = _live_workflow()

    with pytest.raises(KeyError, match="missing-job"):
        workflow.job("missing-job")
    with pytest.raises(KeyError, match="missing-step"):
        workflow.job("main-gate").step("missing-step")
