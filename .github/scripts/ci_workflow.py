#!/usr/bin/env python3
"""Read the narrow CI workflow shape used by the task-4 policy checks.

This module intentionally parses only the parts of `ci.yml` that the workflow
contract tests care about:
- jobs and direct dependencies
- job and step `if:` conditions
- shell commands
- working directories
- `continue-on-error`

It is a structural reader, not a GitHub Actions emulator.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

import yaml


ContinueOnError: TypeAlias = bool | str | None


class WorkflowError(ValueError):
    """Raised when the workflow file falls outside the supported narrow shape."""


@dataclass(frozen=True)
class WorkflowStep:
    """Normalized view of one workflow step used by the contract tests."""

    name: str
    condition: str | None
    command: str | None
    working_directory: str | None
    continue_on_error: ContinueOnError


@dataclass(frozen=True)
class WorkflowJob:
    """Normalized view of one workflow job used by the contract tests."""

    name: str
    dependencies: tuple[str, ...]
    condition: str | None
    continue_on_error: ContinueOnError
    steps: tuple[WorkflowStep, ...]

    def steps_by_name(self) -> dict[str, WorkflowStep]:
        """Return this job's steps keyed by display name for fast lookup."""
        return {step.name: step for step in self.steps}

    def step(self, name: str) -> WorkflowStep:
        """Return one named step or raise a readable error."""
        workflow_step = self.steps_by_name().get(name)
        if workflow_step is None:
            raise KeyError(f"Workflow job '{self.name}' has no step named '{name}'.")
        return workflow_step


@dataclass(frozen=True)
class Workflow:
    """Parsed workflow keyed by stable job ids."""

    jobs: dict[str, WorkflowJob]

    def job(self, name: str) -> WorkflowJob:
        """Return one named job or raise a readable error."""
        try:
            return self.jobs[name]
        except KeyError:
            raise KeyError(f"Workflow has no job named '{name}'.") from None


def _mapping(raw: object, field_name: str) -> dict[str, object]:
    """Validate and normalize one mapping-shaped workflow node."""
    if not isinstance(raw, dict):
        raise WorkflowError(f"Workflow field '{field_name}' must be a mapping.")
    return {str(key): value for key, value in raw.items()}


def _optional_string(raw: object, field_name: str) -> str | None:
    """Validate one optional string workflow field."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise WorkflowError(f"Workflow field '{field_name}' must be a string.")
    return raw


def _continue_on_error(raw: object, field_name: str) -> ContinueOnError:
    """Validate one supported `continue-on-error` value."""
    if raw is None or isinstance(raw, (bool, str)):
        return raw
    raise WorkflowError(
        f"Workflow field '{field_name}' must be a boolean or expression string."
    )


def _dependencies(raw: object, job_name: str) -> tuple[str, ...]:
    """Normalize a job's `needs` value into one stable tuple."""
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        return tuple(raw)
    raise WorkflowError(
        f"Workflow job '{job_name}' field 'needs' must be a string or string list."
    )


def _steps(raw: object, job_name: str) -> tuple[WorkflowStep, ...]:
    """Parse one job's optional step list into normalized workflow steps."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise WorkflowError(f"Workflow job '{job_name}' field 'steps' must be a list.")

    parsed_steps: list[WorkflowStep] = []
    for index, raw_step in enumerate(raw):
        step = _mapping(raw_step, f"jobs.{job_name}.steps[{index}]")
        step_prefix = f"jobs.{job_name}.steps[{index}]"
        parsed_steps.append(
            WorkflowStep(
                name=_optional_string(step.get("name"), f"{step_prefix}.name") or "",
                condition=_optional_string(step.get("if"), f"{step_prefix}.if"),
                command=_optional_string(step.get("run"), f"{step_prefix}.run"),
                working_directory=_optional_string(
                    step.get("working-directory"),
                    f"{step_prefix}.working-directory",
                ),
                continue_on_error=_continue_on_error(
                    step.get("continue-on-error"),
                    f"{step_prefix}.continue-on-error",
                ),
            )
        )
    return tuple(parsed_steps)


def load_workflow(path: Path) -> Workflow:
    """Load one workflow file into the narrow structural model."""
    try:
        raw_workflow = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise WorkflowError(f"Could not parse workflow YAML: {exc}") from exc

    workflow = _mapping(raw_workflow, "root")
    raw_jobs = _mapping(workflow.get("jobs"), "jobs")
    jobs: dict[str, WorkflowJob] = {}

    for job_name, raw_job in raw_jobs.items():
        job = _mapping(raw_job, f"jobs.{job_name}")
        jobs[job_name] = WorkflowJob(
            name=job_name,
            dependencies=_dependencies(job.get("needs"), job_name),
            condition=_optional_string(job.get("if"), f"jobs.{job_name}.if"),
            continue_on_error=_continue_on_error(
                job.get("continue-on-error"),
                f"jobs.{job_name}.continue-on-error",
            ),
            steps=_steps(job.get("steps"), job_name),
        )

    return Workflow(jobs=jobs)
