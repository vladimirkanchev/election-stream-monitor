#!/usr/bin/env python3
"""Validate the protected and advisory contract around the main CI workflow.

The checks in this module answer a narrow policy question:
- which jobs must block `main` pull requests
- which jobs stay advisory
- which path-skippable steps must still run for `main`
- where full frontend validation is allowed to live

The goal is to keep the external protection surface simple while making the
internal contract hard to drift by accident.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from ci_workflow import Workflow, WorkflowJob, WorkflowStep


MAIN_GATE_REQUIRED_JOBS = frozenset(
    {
        "feature-gate",
        "main-pr-consistency",
        "integration-smoke",
        "contract-checks",
        "test-and-build",
    }
)
FEATURE_GATE_REQUIRED_JOBS = frozenset(
    {
        "frontend-checkpoint",
        "backend-tests",
        "frontend-typecheck",
        "backend-typecheck",
        "backend-ruff",
    }
)
ADVISORY_JOBS = frozenset(
    {
        "frontend-lint",
        "backend-pyright",
    }
)
REQUIRED_FRONTEND_COMMANDS_BY_JOB = {
    "test-and-build": (
        "npm run test",
        "npm run build",
    ),
}
MAIN_PR_FORCE_ON_CLAUSE = (
    "github.event_name == 'pull_request' && github.base_ref == 'main'"
)
MAIN_ONLY_JOBS = frozenset(
    {
        "main-pr-consistency",
        "integration-smoke",
        "main-gate",
    }
)
FORCED_ON_WORK_STEPS = {
    "frontend-checkpoint": (
        "Install Python dependencies",
        "Install frontend dependencies",
        "Run frontend checkpoint",
    ),
    "backend-tests": (
        "Run editable-install packaging check",
        "Install Python dependencies",
        "Run packaging smoke check",
        "Run report tooling compile smoke check",
        "Run fast_synthetic backend tests",
    ),
    "backend-ruff": (
        "Install Python lint dependencies",
        "Run backend Ruff lint",
    ),
    "backend-typecheck": (
        "Install Python typecheck dependencies",
        "Run backend typecheck",
    ),
    "frontend-typecheck": (
        "Install frontend dependencies",
        "Run frontend typecheck",
    ),
    "test-and-build": (
        "Install Python dependencies",
        "Install frontend dependencies",
        "Run full frontend test suite",
        "Run frontend production build",
    ),
}
BACKEND_TEST_JOB = "backend-tests"
BACKEND_TEST_STEP = "Run fast_synthetic backend tests"
BACKEND_FAST_SELECTOR = 'pytest -q -m "not e2e and not slow"'
AGGREGATE_REQUIRED_JOBS = {
    "main-gate": MAIN_GATE_REQUIRED_JOBS,
    "feature-gate": FEATURE_GATE_REQUIRED_JOBS,
}
AGGREGATE_DEPENDENCY_FAILURE_CODES = {
    "main-gate": "main-gate-dependencies",
    "feature-gate": "feature-gate-dependencies",
}


@dataclass(frozen=True)
class ContractFailure:
    """Stable failure record emitted by the workflow-contract validator."""

    code: str
    message: str


def _has_main_pr_force_on(condition: str | None) -> bool:
    """Return whether a job or step is explicitly forced on for `main` PRs."""
    return MAIN_PR_FORCE_ON_CLAUSE in (condition or "")


def _required_job(
    workflow: Workflow,
    job_name: str,
    failures: list[ContractFailure],
    *,
    missing_code: str = "required-job-missing",
) -> WorkflowJob | None:
    """Return one required job and record a stable failure when it is missing."""
    job = workflow.jobs.get(job_name)
    if job is None:
        failures.append(
            ContractFailure(missing_code, f"Workflow job '{job_name}' is missing.")
        )
    return job


def _dependency_failures(workflow: Workflow) -> list[ContractFailure]:
    """Check the exact aggregate dependency sets for the protected gate jobs."""
    failures: list[ContractFailure] = []

    for job_name, expected in AGGREGATE_REQUIRED_JOBS.items():
        job = _required_job(workflow, job_name, failures)
        if job is None:
            continue
        if frozenset(job.dependencies) != expected:
            failures.append(
                ContractFailure(
                    AGGREGATE_DEPENDENCY_FAILURE_CODES[job_name],
                    f"Workflow job '{job_name}' dependencies differ from the protected contract.",
                )
            )
    return failures


def _advisory_failures(workflow: Workflow) -> list[ContractFailure]:
    """Check that advisory jobs still exist and stay outside the blocking graph."""
    failures: list[ContractFailure] = []

    for job_name in sorted(ADVISORY_JOBS):
        job = _required_job(
            workflow,
            job_name,
            failures,
            missing_code="advisory-job-missing",
        )
        if job is not None and job.continue_on_error is not True:
            failures.append(
                ContractFailure(
                    "advisory-job-blocking",
                    f"Advisory workflow job '{job_name}' is no longer non-blocking.",
                )
            )

    aggregate_dependencies: set[str] = set()
    for gate_name in ("feature-gate", "main-gate"):
        gate = workflow.jobs.get(gate_name)
        if gate is not None:
            aggregate_dependencies.update(gate.dependencies)
    promoted_jobs = sorted(ADVISORY_JOBS.intersection(aggregate_dependencies))
    if promoted_jobs:
        failures.append(
            ContractFailure(
                "advisory-job-promoted",
                f"Advisory jobs became aggregate dependencies: {promoted_jobs}.",
            )
        )
    return failures


def _job_activation_failures(workflow: Workflow) -> list[ContractFailure]:
    """Check the job-level rules that force protected work onto `main` PRs."""
    failures: list[ContractFailure] = []
    contract_checks = _required_job(workflow, "contract-checks", failures)
    if contract_checks is not None:
        condition = contract_checks.condition or ""
        if (
            "github.event_name == 'pull_request'" not in condition
            or "github.base_ref == 'main'" not in condition
        ):
            failures.append(
                ContractFailure(
                    "main-force-on-missing",
                    "Workflow job 'contract-checks' is not forced on for main PRs.",
                )
            )

    for job_name in sorted(MAIN_ONLY_JOBS):
        job = _required_job(workflow, job_name, failures)
        if job is not None and not _has_main_pr_force_on(job.condition):
            failures.append(
                ContractFailure(
                    "main-force-on-missing",
                    f"Main-only workflow job '{job_name}' lost its main-PR condition.",
                )
            )
    return failures


def _work_step_activation_failures(workflow: Workflow) -> list[ContractFailure]:
    """Check step-level force-on rules for jobs that normally path-skip work."""
    failures: list[ContractFailure] = []

    for job_name, step_names in FORCED_ON_WORK_STEPS.items():
        job = _required_job(workflow, job_name, failures)
        if job is None:
            continue
        steps_by_name = job.steps_by_name()
        for step_name in step_names:
            step = steps_by_name.get(step_name)
            if step is None:
                failures.append(
                    ContractFailure(
                        "required-step-missing",
                        f"Workflow job '{job_name}' is missing step '{step_name}'.",
                    )
                )
                continue
            if not _has_main_pr_force_on(step.condition):
                failures.append(
                    ContractFailure(
                        "main-force-on-missing",
                        f"Workflow step '{job_name} / {step_name}' lost its main-PR condition.",
                    )
                )
    return failures


def _backend_test_lane_failures(workflow: Workflow) -> list[ContractFailure]:
    """Check that the fast backend lane still discovers the contract tests broadly."""
    failures: list[ContractFailure] = []
    job = _required_job(workflow, BACKEND_TEST_JOB, failures)
    if job is None:
        return failures

    step = job.steps_by_name().get(BACKEND_TEST_STEP)
    if step is None:
        failures.append(
            ContractFailure(
                "backend-test-lane",
                f"Workflow job '{BACKEND_TEST_JOB}' is missing its fast test step.",
            )
        )
        return failures

    command = step.command or ""
    if BACKEND_FAST_SELECTOR not in command or "tests/" in command:
        failures.append(
            ContractFailure(
                "backend-test-lane",
                "Backend fast tests must retain broad marker-based discovery.",
            )
        )
    return failures


def _frontend_command_owners(
    workflow: Workflow,
    commands: Iterable[str],
) -> dict[str, list[tuple[WorkflowJob, WorkflowStep]]]:
    """Collect the owning job/step pairs for each required frontend command."""
    owners_by_command: dict[str, list[tuple[WorkflowJob, WorkflowStep]]] = defaultdict(
        list
    )
    expected_commands = set(commands)

    for job in workflow.jobs.values():
        for step in job.steps:
            if step.command in expected_commands:
                owners_by_command[step.command].append((job, step))

    return owners_by_command


def _frontend_validation_failures(workflow: Workflow) -> list[ContractFailure]:
    """Check ownership and protection rules for full frontend test/build commands."""
    failures: list[ContractFailure] = []
    required_commands = {
        command
        for commands in REQUIRED_FRONTEND_COMMANDS_BY_JOB.values()
        for command in commands
    }
    owners_by_command = _frontend_command_owners(workflow, required_commands)

    for expected_job_name, commands in REQUIRED_FRONTEND_COMMANDS_BY_JOB.items():
        for command in commands:
            owners = owners_by_command.get(command, [])
            if not owners:
                failures.append(
                    ContractFailure(
                        "frontend-command-missing",
                        f"Required frontend command '{command}' is missing.",
                    )
                )
                continue
            if len(owners) != 1:
                failures.append(
                    ContractFailure(
                        "frontend-command-duplicated",
                        f"Required frontend command '{command}' must have one owner.",
                    )
                )
                continue

            job, step = owners[0]
            if job.name != expected_job_name:
                failures.append(
                    ContractFailure(
                        "frontend-command-owner",
                        f"Required frontend command '{command}' moved to '{job.name}'.",
                    )
                )
            if job.continue_on_error not in (None, False) or step.continue_on_error not in (
                None,
                False,
            ):
                failures.append(
                    ContractFailure(
                        "frontend-command-advisory",
                        f"Required frontend command '{command}' became advisory.",
                    )
                )
            if step.working_directory != "frontend":
                failures.append(
                    ContractFailure(
                        "frontend-command-directory",
                        f"Required frontend command '{command}' no longer runs from frontend.",
                    )
                )
            if not _has_main_pr_force_on(step.condition):
                failures.append(
                    ContractFailure(
                        "main-force-on-missing",
                        f"Required frontend command '{command}' lost its main-PR condition.",
                    )
                )
    return failures


def contract_failures(workflow: Workflow) -> tuple[ContractFailure, ...]:
    """Return the full ordered list of workflow-contract failures."""
    return tuple(
        _dependency_failures(workflow)
        + _advisory_failures(workflow)
        + _job_activation_failures(workflow)
        + _work_step_activation_failures(workflow)
        + _backend_test_lane_failures(workflow)
        + _frontend_validation_failures(workflow)
    )
