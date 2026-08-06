"""Regression coverage for CI, static-analysis, coverage, and security policy.

The tests keep the workflow reader, detector-lane admission, protected PR
requirements, static-analysis ownership, advisory reporting, supply-chain
checks, and bounded weekly-media diagnostics aligned with their owners.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

ci_workflow = importlib.import_module("ci_workflow")
ci_workflow_contract = importlib.import_module("ci_workflow_contract")
check_split_suite_registration = importlib.import_module(
    "check_split_suite_registration"
)
CI_WORKFLOW_PATH = SCRIPTS_DIR.parent / "workflows" / "ci.yml"
BRANCH_CI_WORKFLOW_PATH = SCRIPTS_DIR.parent / "workflows" / "branch-ci.yml"
WEEKLY_VALIDATION_WORKFLOW_PATH = (
    SCRIPTS_DIR.parent / "workflows" / "weekly-validation.yml"
)
COVERAGE_EVIDENCE_WORKFLOW_PATH = (
    SCRIPTS_DIR.parent / "workflows" / "coverage-evidence.yml"
)
WORKFLOW_PATHS = (
    CI_WORKFLOW_PATH,
    BRANCH_CI_WORKFLOW_PATH,
    COVERAGE_EVIDENCE_WORKFLOW_PATH,
    WEEKLY_VALIDATION_WORKFLOW_PATH,
)
# Job-level token scopes are exceptions to the workflow read-only default. Keep
# this empty until a reviewed job needs a narrowly scoped write permission.
WORKFLOW_PERMISSION_EXCEPTIONS: dict[str, dict[str, dict[str, str]]] = {
    workflow_path.name: {} for workflow_path in WORKFLOW_PATHS
}
FRONTEND_INSTALLER_PATH = Path("scripts/install_frontend_dependencies.sh")
PYTHON_VERSION_PATH = Path(".python-version")
NVMRC_PATH = Path(".nvmrc")
FRONTEND_PACKAGE_PATH = Path("frontend/package.json")
FRONTEND_ESLINT_CONFIG_PATH = Path("frontend/eslint.config.js")
FRONTEND_VITE_CONFIG_PATH = Path("frontend/vite.config.ts")
PYTHON_AUDIT_SCRIPT_PATH = Path("scripts/audit_python_dependencies.sh")
CI_TARGET_MANIFEST_PATH = Path(".github/ci_test_targets.json")
BACKEND_TYPECHECK_TARGETS_PATH = Path(".github/backend_typecheck_targets.txt")
JUSTFILE_PATH = Path("justfile")
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
DETECTOR_BACKEND_PATHS = frozenset(
    {
        "src/**",
        "detector_lab/**",
        "tests/**",
        "justfile",
        ".github/ci_test_targets.json",
    }
)
DETECTOR_WORKFLOW_CONFIGURATION_PATHS = frozenset(
    {"justfile", ".github/ci_test_targets.json"}
)
SUPPLY_CHAIN_ACTIVATION_PATHS = frozenset(
    {
        ".github/workflows/**",
        ".github/scripts/**",
        ".github/security_tools.json",
        "scripts/install_security_tool.py",
        "scripts/**/*.sh",
        "justfile",
    }
)
WEEKLY_ONLY_TARGET_GROUPS = (
    "weekly_slow_media",
    "weekly_api_stream_deep",
    "weekly_lifecycle",
)
BRANCH_BACKEND_CONDITION = (
    "needs.changes.outputs.backend == 'true' || "
    "needs.changes.outputs.contract == 'true'"
)


def _live_workflow() -> Any:
    """Load the current repository workflow through the public reader."""
    return ci_workflow.load_workflow(CI_WORKFLOW_PATH)


def _workflow_text(path: Path) -> str:
    """Return one workflow file as raw text for trigger-shape assertions."""
    return path.read_text()


def _workflow_document(workflow_path: Path) -> dict[str, Any]:
    """Load one checked-in workflow as a validated top-level mapping."""
    workflow = yaml.safe_load(workflow_path.read_text())
    assert isinstance(workflow, dict)
    return workflow


def _workflow_jobs(workflow_path: Path) -> dict[str, dict[str, Any]]:
    """Return validated job mappings from one checked-in workflow."""
    jobs = _workflow_document(workflow_path).get("jobs")
    assert isinstance(jobs, dict)
    assert all(
        isinstance(name, str) and isinstance(job, dict) for name, job in jobs.items()
    )
    return jobs


@pytest.mark.parametrize("workflow_path", WORKFLOW_PATHS)
def test_workflow_permissions_default_to_read_only(
    workflow_path: Path,
) -> None:
    """Workflows stay read-only unless a reviewed job needs a narrower scope."""
    workflow = _workflow_document(workflow_path)
    assert workflow.get("permissions") == {"contents": "read"}

    job_permissions = {
        job_name: permissions
        for job_name, job in _workflow_jobs(workflow_path).items()
        if (permissions := job.get("permissions")) is not None
    }
    assert job_permissions == WORKFLOW_PERMISSION_EXCEPTIONS[workflow_path.name]


def _workflow_job_steps(
    workflow_path: Path, job_name: str
) -> tuple[dict[str, Any], ...]:
    """Return parsed step mappings for one checked-in workflow job."""
    job = _workflow_jobs(workflow_path).get(job_name)
    assert isinstance(job, dict)
    steps = job.get("steps")
    assert isinstance(steps, list)
    assert all(isinstance(step, dict) for step in steps)
    return tuple(steps)


def _workflow_job_commands(workflow_path: Path, job_name: str) -> tuple[str, ...]:
    """Return the executable commands for one workflow job without step labels."""
    return tuple(
        command
        for step in _workflow_job_steps(workflow_path, job_name)
        if isinstance(command := step.get("run"), str)
    )


def _workflow_commands(workflow_path: Path) -> tuple[str, ...]:
    """Return executable commands from every job in one checked-in workflow."""
    return tuple(
        command
        for job in _workflow_jobs(workflow_path).values()
        for step in job.get("steps", [])
        if isinstance(step, dict)
        if isinstance(command := step.get("run"), str)
    )


def _backend_typecheck_targets() -> tuple[str, ...]:
    """Return reviewed backend type targets from their sole owner."""
    targets = tuple(
        line.strip()
        for line in BACKEND_TYPECHECK_TARGETS_PATH.read_text().splitlines()
        if line.strip()
    )
    assert targets
    assert len(targets) == len(set(targets))
    assert all(
        target.startswith("src/") and Path(target).is_file() for target in targets
    )
    return targets


def _workflow_environment_values(
    workflow_path: Path,
    setting_name: str,
) -> tuple[str, ...]:
    """Return configured values for one setting across every workflow scope."""
    workflow = _workflow_document(workflow_path)
    environment_scopes: list[object] = [workflow.get("env")]

    for job in _workflow_jobs(workflow_path).values():
        environment_scopes.append(job.get("env"))
        steps = job.get("steps", [])
        assert isinstance(steps, list)
        for step in steps:
            assert isinstance(step, dict)
            environment_scopes.append(step.get("env"))

    values: list[str] = []
    for environment in environment_scopes:
        if environment is None:
            continue
        assert isinstance(environment, dict)
        if setting_name in environment:
            values.append(str(environment[setting_name]))
    return tuple(values)


def _workflow_action_values(
    workflow_path: Path,
    action_prefix: str,
    setting_name: str,
) -> tuple[str, ...]:
    """Return one `with:` setting from actions selected by stable identity."""
    values: list[str] = []
    for job in _workflow_jobs(workflow_path).values():
        steps = job.get("steps", [])
        assert isinstance(steps, list)
        for step in steps:
            assert isinstance(step, dict)
            action = step.get("uses")
            if not isinstance(action, str) or not action.startswith(action_prefix):
                continue
            settings = step.get("with")
            assert isinstance(settings, dict)
            value = settings.get(setting_name)
            assert isinstance(value, str)
            values.append(value)
    return tuple(values)


def _weekly_slow_media_steps() -> tuple[dict[str, Any], ...]:
    """Return the weekly job that owns checked-in slow media confidence."""
    return _workflow_job_steps(WEEKLY_VALIDATION_WORKFLOW_PATH, "slow-e2e")


def _weekly_artifact_uploads() -> tuple[dict[str, Any], ...]:
    """Return weekly artifact uploads through their stable GitHub Action identity."""
    return tuple(
        step
        for job in _workflow_jobs(WEEKLY_VALIDATION_WORKFLOW_PATH).values()
        for step in job.get("steps", [])
        if isinstance(step, dict) and step.get("uses") == "actions/upload-artifact@v4"
    )


def _weekly_slow_media_artifact_uploads() -> tuple[dict[str, Any], ...]:
    """Return failure uploads owned specifically by the weekly slow-media job."""
    return tuple(
        step
        for step in _weekly_slow_media_steps()
        if step.get("uses") == "actions/upload-artifact@v4"
    )


def _coverage_evidence_steps() -> tuple[dict[str, Any], ...]:
    """Return the standalone advisory coverage-job steps."""
    return _workflow_job_steps(COVERAGE_EVIDENCE_WORKFLOW_PATH, "coverage-evidence")


def _artifact_paths(upload_step: dict[str, Any]) -> frozenset[str]:
    """Return the normalized path allowlist from one artifact upload step."""
    options = upload_step.get("with")
    assert isinstance(options, dict)
    raw_paths = options.get("path")
    assert isinstance(raw_paths, str)
    return frozenset(path.strip() for path in raw_paths.splitlines() if path.strip())


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
        failure.code for failure in ci_workflow_contract.contract_failures(workflow)
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


def _path_filter_paths(workflow_path: Path, filter_name: str) -> frozenset[str]:
    """Return the configured path patterns for one named workflow filter."""
    changes_job = _workflow_jobs(workflow_path).get("changes")
    assert isinstance(changes_job, dict)
    steps = changes_job.get("steps")
    assert isinstance(steps, list)
    filter_steps = [
        step for step in steps if isinstance(step, dict) and step.get("id") == "filter"
    ]

    assert len(filter_steps) == 1
    options = filter_steps[0].get("with")
    assert isinstance(options, dict)
    filter_source = options.get("filters")
    assert isinstance(filter_source, str)
    filters = yaml.safe_load(filter_source)
    assert isinstance(filters, dict)
    paths = filters.get(filter_name)
    assert isinstance(paths, list)
    assert all(isinstance(path, str) for path in paths)
    return frozenset(paths)


def _just_recipe_test_targets(recipe_name: str) -> frozenset[str]:
    """Return direct test-file targets through the registration guard reader."""
    return check_split_suite_registration.recipe_test_paths(recipe_name)


def _just_recipe_body(recipe_name: str) -> str:
    """Return one recipe body without coupling assertions to nearby recipes."""
    lines = JUSTFILE_PATH.read_text().splitlines()
    recipe_start = lines.index(f"{recipe_name}:") + 1
    recipe_lines: list[str] = []

    for line in lines[recipe_start:]:
        if line and not line[0].isspace():
            break
        recipe_lines.append(line)

    return "\n".join(recipe_lines)


def _typescript_string_array(source: str, setting_name: str) -> frozenset[str]:
    """Read one simple quoted-string array from checked-in TypeScript config."""
    match = re.search(
        rf"{setting_name}\s*:\s*\[(?P<items>.*?)\]",
        source,
        re.DOTALL,
    )
    assert match is not None
    return frozenset(re.findall(r'"([^"]+)"', match.group("items")))


def test_focused_detector_recipes_keep_canonical_targets() -> None:
    """Focused detector recipes must retain their reviewed ownership sets."""
    expected_targets_by_recipe = {
        "test-detectors": {"tests/test_detectors.py"},
        "test-detector-lab": {
            "tests/test_detector_lab_runner.py",
            "tests/test_detector_lab_metrics.py",
            "tests/test_detector_lab_practical_blur.py",
            "tests/test_detector_lab_practical_motion.py",
        },
        "test-real-media": {
            "tests/test_detectors_integration.py",
            "tests/test_detector_lab_real_media.py",
        },
    }

    for recipe_name, expected_targets in expected_targets_by_recipe.items():
        assert _just_recipe_test_targets(recipe_name) == expected_targets
        assert all(Path(target).is_file() for target in expected_targets)


@pytest.mark.parametrize(
    "workflow_path",
    (CI_WORKFLOW_PATH, BRANCH_CI_WORKFLOW_PATH),
)
def test_detector_paths_activate_backend_feedback(
    workflow_path: Path,
) -> None:
    """Detector code, tests, and selectors must activate backend feedback."""
    assert DETECTOR_BACKEND_PATHS <= _path_filter_paths(workflow_path, "backend")


@pytest.mark.parametrize(
    "workflow_path",
    (CI_WORKFLOW_PATH, BRANCH_CI_WORKFLOW_PATH),
)
def test_detector_validation_configuration_activates_workflow_feedback(
    workflow_path: Path,
) -> None:
    """Detector recipe and manifest edits must also activate workflow checks."""
    assert DETECTOR_WORKFLOW_CONFIGURATION_PATHS <= _path_filter_paths(
        workflow_path, "workflow"
    )


def test_backend_admission_keeps_main_pr_force_on_separate() -> None:
    """Branch pushes use path activation while protected main PRs add force-on."""
    branch_step = (
        ci_workflow.load_workflow(BRANCH_CI_WORKFLOW_PATH)
        .job(BACKEND_TEST_JOB)
        .step(BACKEND_TEST_STEP)
    )
    protected_step = _live_workflow().job(BACKEND_TEST_JOB).step(BACKEND_TEST_STEP)

    assert branch_step.condition == BRANCH_BACKEND_CONDITION
    assert protected_step.condition is not None
    assert BRANCH_BACKEND_CONDITION in protected_step.condition
    assert MAIN_PR_FORCE_ON_CLAUSE in protected_step.condition


def test_routine_fast_workflows_exclude_environment_sensitive_confidence() -> None:
    """Routine feedback must not start slow, external, or weekly confidence."""
    for workflow_path in (CI_WORKFLOW_PATH, BRANCH_CI_WORKFLOW_PATH):
        backend_commands = _workflow_job_commands(workflow_path, BACKEND_TEST_JOB)
        workflow_commands = _workflow_commands(workflow_path)

        assert any(BACKEND_FAST_SELECTOR in command for command in backend_commands)
        assert all(
            target_group not in command
            for target_group in WEEKLY_ONLY_TARGET_GROUPS
            for command in workflow_commands
        )
        assert "1" not in _workflow_environment_values(
            workflow_path,
            "API_STREAM_REAL_SMOKE",
        )
        assert all(
            "API_STREAM_REAL_SMOKE=1" not in command for command in workflow_commands
        )


def test_routine_workflows_keep_live_postgres_confidence_disabled() -> None:
    """Routine PR and branch workflows must not start live PostgreSQL confidence."""
    for workflow_path in (CI_WORKFLOW_PATH, BRANCH_CI_WORKFLOW_PATH):
        workflow_commands = _workflow_commands(workflow_path)

        assert set(
            _workflow_environment_values(workflow_path, "ESM_ALERT_STORE_BACKEND")
        ) == {"file"}
        for setting_name in (
            "POSTGRES_ALERT_STORE_REAL_SMOKE",
            "POSTGRES_SESSION_STORE_REAL_SMOKE",
        ):
            assert set(_workflow_environment_values(workflow_path, setting_name)) == {
                "0"
            }
            assert all(
                f"{setting_name}=1" not in command for command in workflow_commands
            )
        assert all(
            "services" not in job for job in _workflow_jobs(workflow_path).values()
        )
        assert all(
            "postgres_alert_weekly_" not in command for command in workflow_commands
        )


def test_frontend_workflows_use_the_shared_installer() -> None:
    """Every frontend install lane should use the shared toolchain helper."""

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


def test_environment_toolchain_owners_stay_aligned() -> None:
    """Tracked defaults, CI setup, and frontend declarations must agree."""
    workflow_paths = (
        CI_WORKFLOW_PATH,
        BRANCH_CI_WORKFLOW_PATH,
        WEEKLY_VALIDATION_WORKFLOW_PATH,
    )
    python_default = PYTHON_VERSION_PATH.read_text().strip()
    node_default = NVMRC_PATH.read_text().strip()
    frontend_package = json.loads(FRONTEND_PACKAGE_PATH.read_text())

    assert re.fullmatch(r"\d+\.\d+", python_default)
    assert {
        value
        for workflow_path in workflow_paths
        for value in _workflow_action_values(
            workflow_path, "actions/setup-python@", "python-version"
        )
    } == {python_default}
    assert node_default.isdecimal()
    assert frontend_package["engines"]["node"] == f"{node_default}.x"
    assert {
        value
        for workflow_path in workflow_paths
        for value in _workflow_action_values(
            workflow_path, "actions/setup-node@", "node-version-file"
        )
    } == {str(NVMRC_PATH)}

    npm_spec = frontend_package.get("packageManager")
    assert isinstance(npm_spec, str)
    match = re.fullmatch(r"npm@(\d+)\.\d+\.\d+", npm_spec)
    assert match is not None
    assert frontend_package["engines"]["npm"] == f"{match.group(1)}.x"

    installer = FRONTEND_INSTALLER_PATH.read_text()
    assert '"${REPO_ROOT}/.nvmrc"' in installer
    assert "packageJson.packageManager" in installer
    assert re.search(
        r'REQUIRED_NPM_VERSION="\$\{REQUIRED_NPM_SPEC#npm@\}"', installer
    )
    assert 'npm@${REQUIRED_NPM_VERSION}' in installer


def test_backend_typecheck_target_manifest_is_valid() -> None:
    """The shared typecheck manifest must contain reviewed backend modules."""
    targets = _backend_typecheck_targets()

    assert {
        "src/analyzer_contract.py",
        "src/analyzer_registry.py",
        "src/api/errors.py",
        "src/api/http_auth_policy.py",
        "src/api/http_rate_limit_policy.py",
        "src/api_bind_policy.py",
        "src/detectors/black_screen.py",
        "src/detectors/blur.py",
        "src/detectors/registry.py",
    }.issubset(targets)


def test_local_typecheck_recipes_share_backend_target_manifest() -> None:
    """Local protected and advisory type checks must use the shared manifest."""
    justfile = JUSTFILE_PATH.read_text()

    assert 'backend_typecheck_target_file := ".github/backend_typecheck_targets.txt"' in justfile
    assert (
        "MYPYPATH=src xargs {{venv_mypy}} --explicit-package-bases "
        "< {{backend_typecheck_target_file}}"
    ) in justfile
    assert (
        "xargs {{venv_pyright}} --project pyrightconfig.json "
        "< {{backend_typecheck_target_file}}"
    ) in justfile
    assert "typecheck-backend:" in justfile
    assert "typecheck-advisory:" in justfile
    assert "typecheck-frontend:" in justfile
    assert (
        "typecheck: typecheck-backend typecheck-advisory typecheck-frontend"
    ) in justfile


def test_ci_typecheck_jobs_share_backend_target_manifest() -> None:
    """Protected and branch CI must use the same backend typecheck manifest."""
    for workflow_path in (CI_WORKFLOW_PATH, BRANCH_CI_WORKFLOW_PATH):
        workflow = ci_workflow.load_workflow(workflow_path)
        assert workflow.job("backend-typecheck").step("Run backend typecheck").command == (
            "MYPYPATH=src xargs mypy --explicit-package-bases "
            "< .github/backend_typecheck_targets.txt"
        )
        assert workflow.job("backend-pyright").step("Run backend pyright").command == (
            "xargs .venv/bin/pyright --project pyrightconfig.json "
            "< .github/backend_typecheck_targets.txt"
        )


def test_frontend_lint_keeps_electron_advisory_and_renderer_protected() -> None:
    """Electron lint must use Node globals without widening the protected baseline."""
    frontend_package = json.loads(FRONTEND_PACKAGE_PATH.read_text())
    scripts = frontend_package["scripts"]

    assert scripts["lint:renderer"] == "eslint src"
    assert scripts["lint:electron"] == "eslint electron"
    assert scripts["lint:frontend"] == "npm run lint:renderer && npm run lint:electron"

    eslint_config = FRONTEND_ESLINT_CONFIG_PATH.read_text()
    assert 'files: ["src/**/*.{ts,tsx}"]' in eslint_config
    assert "...globals.browser" in eslint_config
    assert 'files: ["electron/**/*.mjs"]' in eslint_config
    assert "...globals.node" in eslint_config

    for workflow_path in (CI_WORKFLOW_PATH, BRANCH_CI_WORKFLOW_PATH):
        workflow = ci_workflow.load_workflow(workflow_path)
        assert workflow.job("frontend-lint").continue_on_error is True
        assert workflow.job("frontend-lint").step("Run frontend lint").command == (
            "npm run lint:frontend"
        )

    assert _live_workflow().job("contract-checks").step(
        "Run frontend lint"
    ).command == "npm run lint:renderer"


def test_static_analysis_policy_keeps_protected_and_advisory_owners() -> None:
    """Static-analysis commands must retain their reviewed coverage and status."""
    justfile = JUSTFILE_PATH.read_text()

    assert "lint-backend:\n    {{venv_ruff}} check src scripts tests" in justfile
    assert "format-check:\n    {{venv_ruff}} format --check src scripts tests" in justfile
    assert "lint-renderer:\n    npm --prefix frontend run lint:renderer" in justfile
    assert "lint-electron-advisory:\n    npm --prefix frontend run lint:electron" in justfile
    assert (
        "ci-local: _backend-tests-fast lint-backend lint-renderer "
        "typecheck-backend typecheck-frontend"
    ) in justfile

    for workflow_path in (CI_WORKFLOW_PATH, BRANCH_CI_WORKFLOW_PATH):
        workflow = ci_workflow.load_workflow(workflow_path)
        feature_gate = workflow.job("feature-gate")

        assert "backend-ruff" in feature_gate.dependencies
        assert "backend-typecheck" in feature_gate.dependencies
        assert workflow.job("backend-ruff").continue_on_error in (None, False)
        assert workflow.job("backend-typecheck").continue_on_error in (None, False)
        assert workflow.job("backend-pyright").continue_on_error is True
        assert workflow.job("frontend-lint").continue_on_error is True
        assert workflow.job("backend-ruff").step("Run backend Ruff lint").command == (
            "ruff check src scripts tests"
        )


def test_security_audits_keep_locked_inputs_and_stay_outside_protected_gates() -> None:
    """Weekly audits must inspect declared inputs without applying fixes."""
    justfile = JUSTFILE_PATH.read_text()
    audit_script = PYTHON_AUDIT_SCRIPT_PATH.read_text()
    weekly_commands = _workflow_commands(WEEKLY_VALIDATION_WORKFLOW_PATH)
    weekly_jobs = _workflow_jobs(WEEKLY_VALIDATION_WORKFLOW_PATH)

    assert "{{venv_bandit}} -r src -x tests,frontend" in _just_recipe_body(
        "audit-bandit"
    )
    assert "scripts/audit_python_dependencies.sh" in _just_recipe_body("audit-python")
    assert "npm --prefix frontend audit --audit-level=high" in _just_recipe_body(
        "audit-frontend"
    )
    assert "uv export --frozen --no-dev --no-emit-project" in audit_script
    assert "--format requirements.txt" in audit_script
    assert '"$PIP_AUDIT" -r "$audit_input"' in audit_script
    assert "trap 'rm -f" in audit_script

    assert "uv sync --locked --extra security" in _workflow_job_commands(
        WEEKLY_VALIDATION_WORKFLOW_PATH, "security-audit"
    )
    assert ".venv/bin/bandit -r src -x tests,frontend" in _workflow_job_commands(
        WEEKLY_VALIDATION_WORKFLOW_PATH, "security-audit"
    )
    assert "uv sync --locked --extra security" in _workflow_job_commands(
        WEEKLY_VALIDATION_WORKFLOW_PATH, "python-security-audit"
    )
    assert (
        "PIP_AUDIT=.venv/bin/pip-audit sh scripts/audit_python_dependencies.sh"
        in _workflow_job_commands(
            WEEKLY_VALIDATION_WORKFLOW_PATH, "python-security-audit"
        )
    )
    npm_steps = _workflow_job_steps(
        WEEKLY_VALIDATION_WORKFLOW_PATH, "npm-security-audit"
    )
    assert any(
        step.get("working-directory") == "frontend"
        and step.get("run") == "npm audit --audit-level=high"
        for step in npm_steps
    )
    assert not any(
        re.fullmatch(r"(?:\.venv/bin/)?pip-audit(?:\s+.*)?", command.strip())
        for command in weekly_commands
    )
    audit_command_sources = "\n".join((justfile, audit_script, *weekly_commands))
    assert "--fix" not in audit_command_sources
    assert "npm audit fix" not in audit_command_sources

    protected_dependencies = {
        *_live_workflow().job("feature-gate").dependencies,
        *_live_workflow().job("main-gate").dependencies,
    }
    assert {"security-audit", "python-security-audit", "npm-security-audit"}.isdisjoint(
        protected_dependencies
    )
    assert {"security-audit", "python-security-audit", "npm-security-audit"} <= set(
        weekly_jobs
    )


@pytest.mark.parametrize(
    "workflow_path",
    (CI_WORKFLOW_PATH, BRANCH_CI_WORKFLOW_PATH),
)
def test_supply_chain_audit_retains_pinned_advisory_scanner_ownership(
    workflow_path: Path,
) -> None:
    """The supply-chain job must stay bounded, advisory, and artifact-free."""
    workflow_job = _workflow_jobs(workflow_path)["ci-supply-chain-audit"]
    workflow_steps = _workflow_job_steps(workflow_path, "ci-supply-chain-audit")
    steps_by_name = {step.get("name"): step for step in workflow_steps}

    assert workflow_job["if"] == "needs.changes.outputs.workflow == 'true'"
    assert workflow_job["continue-on-error"] is True
    assert workflow_job["timeout-minutes"] == 10
    assert workflow_steps[0]["with"]["fetch-depth"] == 0
    for step_name in (
        "Scan committed repository history",
        "Validate GitHub Actions workflows",
        "Validate repository shell scripts",
    ):
        assert steps_by_name[step_name]["continue-on-error"] is True
    assert not any(
        step.get("uses") == "actions/upload-artifact@v4" for step in workflow_steps
    )
    summary_step = steps_by_name["Summarize advisory scanner outcomes"]
    assert summary_step["if"] == "always()"
    assert "raw" not in str(summary_step["run"]).lower()


@pytest.mark.parametrize(
    "workflow_path",
    (CI_WORKFLOW_PATH, BRANCH_CI_WORKFLOW_PATH),
)
def test_supply_chain_audit_runs_each_reviewed_scanner(workflow_path: Path) -> None:
    """The advisory job must install and execute each scanner safely."""
    commands = "\n".join(
        _workflow_job_commands(workflow_path, "ci-supply-chain-audit")
    )

    for tool in ("gitleaks", "actionlint", "shellcheck"):
        assert f"install_security_tool.py {tool}" in commands
    assert "gitleaks\" git --redact --no-banner --exit-code 1" in commands
    assert 'PATH="$RUNNER_TEMP/esm-security-tools:$PATH"' in commands
    assert "esm-security-tools/actionlint" in commands
    assert "shellcheck\" $(git ls-files -- 'scripts/*.sh')" in commands


def test_local_supply_chain_recipes_keep_focused_scanner_ownership() -> None:
    """Local commands must run each reviewed scanner once without suppressions."""
    actionlint_recipe = _just_recipe_body("audit-actionlint")
    shellcheck_recipe = _just_recipe_body("audit-shell")
    aggregate_recipe = _just_recipe_body("audit-ci-supply-chain")

    assert "gitleaks git --redact --no-banner --exit-code 1" in _just_recipe_body(
        "audit-gitleaks"
    )
    assert (
        "PATH=\"{{security_tool_bin_dir}}:$PATH\" {{security_tool_bin_dir}}/actionlint"
        in actionlint_recipe
    )
    assert "shellcheck $(git ls-files -- 'scripts/*.sh')" in shellcheck_recipe
    assert "actionlint" not in shellcheck_recipe
    assert {
        "just audit-gitleaks",
        "just audit-actionlint",
        "just audit-shell",
    } <= {line.strip() for line in aggregate_recipe.splitlines()}
    assert not any(
        path.exists()
        for path in (
            Path(".shellcheckrc"),
            Path(".gitleaks.toml"),
            Path(".github/actionlint.yaml"),
            Path(".github/actionlint.yml"),
        )
    )


@pytest.mark.parametrize(
    "workflow_path",
    (CI_WORKFLOW_PATH, BRANCH_CI_WORKFLOW_PATH),
)
def test_supply_chain_paths_activate_the_advisory_audit(workflow_path: Path) -> None:
    """Scanner configuration and checked shell code must wake its CI owner."""
    assert SUPPLY_CHAIN_ACTIVATION_PATHS <= _path_filter_paths(
        workflow_path, "workflow"
    )


def test_coverage_evidence_stays_advisory_and_non_blocking() -> None:
    """Coverage reporting must remain outside protected PR gate ownership."""
    workflow = ci_workflow.load_workflow(COVERAGE_EVIDENCE_WORKFLOW_PATH)
    coverage_job = workflow.job("coverage-evidence")
    document = _workflow_document(COVERAGE_EVIDENCE_WORKFLOW_PATH)

    assert coverage_job.dependencies == ()
    assert coverage_job.continue_on_error is True
    triggers = document.get("on", document.get(True))
    assert isinstance(triggers, dict)
    assert set(triggers) == {"pull_request", "push"}
    push_trigger = triggers["push"]
    assert isinstance(push_trigger, dict)
    assert push_trigger.get("branches") == ["main"]
    assert isinstance(push_trigger.get("paths"), list)

    coverage_steps = coverage_job.steps_by_name()
    backend_step = coverage_steps["Run backend coverage"]
    frontend_step = coverage_steps["Run frontend coverage"]
    assert backend_step.continue_on_error is True
    assert backend_step.command is not None
    assert "-p pytest_cov" in backend_step.command
    assert '-m "not e2e and not slow"' in backend_step.command
    assert "--cov-report=json:coverage/backend/coverage.json" in backend_step.command
    assert "--cov-report=xml:coverage/backend/coverage.xml" in backend_step.command
    assert frontend_step.continue_on_error is True
    assert frontend_step.command == "npm run test:coverage"
    assert "reportOnFailure: true" in FRONTEND_VITE_CONFIG_PATH.read_text()

    protected_workflow = _live_workflow()
    assert "coverage-evidence" not in protected_workflow.job(
        "main-gate"
    ).dependencies
    assert "coverage-evidence" not in protected_workflow.job(
        "feature-gate"
    ).dependencies


def test_coverage_entrypoints_keep_reviewed_source_boundaries() -> None:
    """Coverage entrypoints must retain their distinct backend/frontend scopes."""
    backend_recipe = _just_recipe_body("coverage-backend")
    frontend_package = json.loads(FRONTEND_PACKAGE_PATH.read_text())
    vite_config = FRONTEND_VITE_CONFIG_PATH.read_text()

    assert "--cov=src" in backend_recipe
    assert "--cov-branch" in backend_recipe
    assert frontend_package["scripts"]["test:coverage"] == "vitest run --coverage"
    assert _typescript_string_array(vite_config, "include") == {
        "src/**/*.{ts,tsx}",
        "electron/**/*.mjs",
    }
    assert {
        "node_modules/**",
        "coverage/**",
        "dist/**",
    } <= _typescript_string_array(vite_config, "exclude")


def test_coverage_policy_has_no_percentage_threshold() -> None:
    """Coverage remains evidence only, without a hidden pass/fail threshold."""
    coverage_workflow = ci_workflow.load_workflow(COVERAGE_EVIDENCE_WORKFLOW_PATH)
    coverage_steps = coverage_workflow.job("coverage-evidence").steps_by_name()
    frontend_package = json.loads(FRONTEND_PACKAGE_PATH.read_text())
    vite_config = FRONTEND_VITE_CONFIG_PATH.read_text()

    configured_coverage = "\n".join(
        (
            _just_recipe_body("coverage-backend"),
            coverage_steps["Run backend coverage"].command or "",
            coverage_steps["Run frontend coverage"].command or "",
            frontend_package["scripts"]["test:coverage"],
        )
    )
    assert "--cov-fail-under" not in configured_coverage
    assert "fail-under" not in configured_coverage
    assert not re.search(r"\bthresholds?\s*:", vite_config)


def test_coverage_evidence_uploads_only_relative_reviewed_reports() -> None:
    """Coverage artifacts upload only after bounded path preparation succeeds."""
    steps = _coverage_evidence_steps()
    names = [str(step.get("name")) for step in steps]
    normalize_index = names.index("Normalize coverage artifact paths")
    summary_index = names.index("Summarize advisory coverage")
    upload_index = names.index("Upload advisory coverage reports")
    incomplete_index = names.index("Mark incomplete advisory coverage")

    normalize_step = steps[normalize_index]
    assert normalize_step.get("if") == "always()"
    assert normalize_step.get("continue-on-error") is True
    normalize_command = str(normalize_step.get("run"))
    assert "normalize_coverage_report_paths.py" in normalize_command
    assert "--repository-root \"$GITHUB_WORKSPACE\"" in normalize_command
    assert "--allow-missing" in normalize_command
    for report_path in (
        "coverage/backend/coverage.json",
        "coverage/backend/coverage.xml",
        "frontend/coverage/coverage-summary.json",
        "frontend/coverage/lcov.info",
    ):
        assert f"test -f {report_path}" in normalize_command

    summary_step = steps[summary_index]
    assert summary_step.get("if") == "always()"
    summary_command = str(summary_step.get("run"))
    assert "$GITHUB_STEP_SUMMARY" in summary_command
    assert "Artifact preparation" in summary_command
    assert "partial reports" in summary_command

    upload_step = steps[upload_index]
    assert (
        upload_step.get("if")
        == "always() && steps.coverage_reports.outcome == 'success'"
    )
    options = upload_step.get("with")
    assert isinstance(options, dict)
    assert options.get("retention-days") == 7
    assert options.get("if-no-files-found") == "warn"
    assert _artifact_paths(upload_step) == {
        "coverage/backend/coverage.json",
        "coverage/backend/coverage.xml",
        "frontend/coverage/coverage-summary.json",
        "frontend/coverage/lcov.info",
    }

    incomplete_step = steps[incomplete_index]
    incomplete_condition = str(incomplete_step.get("if", ""))
    assert incomplete_condition.startswith("always()")
    assert "steps.coverage_reports.outcome != 'success'" in incomplete_condition
    assert "exit 1" in str(incomplete_step.get("run"))
    assert normalize_index < summary_index < upload_index < incomplete_index


def test_weekly_alert_postgres_jobs_keep_their_explicit_live_environment() -> None:
    """Scheduled/manual validation must retain both isolated live-alert jobs."""
    workflow_text = _workflow_text(WEEKLY_VALIDATION_WORKFLOW_PATH)
    backend_job = workflow_text.split("  postgres-alert-backend-confidence:", 1)[
        1
    ].split("  postgres-alert-runtime-operator-confidence:", 1)[0]
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


def test_weekly_slow_media_job_sets_failure_artifact_directories() -> None:
    """The weekly media command must configure both bounded diagnostic folders."""
    media_test_steps = [
        step
        for step in _weekly_slow_media_steps()
        if "weekly_slow_media" in str(step.get("run", ""))
    ]

    assert len(media_test_steps) == 1
    environment = media_test_steps[0].get("env")
    assert environment == {
        "ESM_DETECTOR_LAB_ARTIFACT_DIR": "ci-artifacts/detector-lab-real-media",
        "ESM_GROUND_TRUTH_ARTIFACT_DIR": "ci-artifacts/ground-truth-failures",
    }


def test_weekly_slow_media_job_builds_result_index_before_exiting() -> None:
    """The weekly media command must build its summary before restoring pytest status."""
    media_command = next(
        command
        for command in _workflow_job_commands(
            WEEKLY_VALIDATION_WORKFLOW_PATH, "slow-e2e"
        )
        if "weekly_slow_media" in command
    )

    assert "--junitxml=ci-artifacts/weekly-media-results.junit.xml" in media_command
    assert "build_weekly_media_result_index.py" in media_command
    assert "ci-artifacts/weekly-media-results.json" in media_command
    assert "cat ci-artifacts/weekly-media-results.json" in media_command
    assert 'exit "$pytest_status"' in media_command
    assert (
        media_command.index("pytest_status=${PIPESTATUS[0]}")
        < media_command.index("build_weekly_media_result_index.py")
        < media_command.index("cat ci-artifacts/weekly-media-results.json")
        < media_command.index('exit "$pytest_status"')
    )


def test_weekly_artifacts_are_failure_only_and_short_lived() -> None:
    """Weekly uploads must retain only reviewed evidence for a short period."""
    upload_steps = _weekly_artifact_uploads()

    assert upload_steps
    for step in upload_steps:
        options = step.get("with")
        assert step.get("if") == "failure()"
        assert isinstance(options, dict)
        assert options.get("retention-days") == 7

    excluded_paths = {
        "ci-artifacts/slow-e2e.log",
        "ci-artifacts/weekly-media-results.junit.xml",
    }
    assert all(
        not excluded_paths & _artifact_paths(step)
        for step in upload_steps
    )


def test_weekly_slow_media_failure_upload_has_the_reviewed_artifact_allowlist() -> None:
    """The weekly media bundle must not retain unreviewed diagnostic files."""
    expected_paths = {
        "ci-artifacts/weekly-media-preflight.log",
        "ci-artifacts/weekly-media-results.json",
        "ci-artifacts/detector-lab-real-media/**",
        "ci-artifacts/ground-truth-failures/**",
    }

    upload_steps = _weekly_slow_media_artifact_uploads()

    assert len(upload_steps) == 1
    assert _artifact_paths(upload_steps[0]) == expected_paths


def test_weekly_slow_media_job_runs_non_decoding_fixture_and_tool_preflight() -> None:
    """Weekly media failures should be classified before detector execution."""
    commands = _workflow_job_commands(WEEKLY_VALIDATION_WORKFLOW_PATH, "slow-e2e")

    preflight_index = next(
        index
        for index, command in enumerate(commands)
        if "check_weekly_media_preflight.py" in command
    )
    media_test_index = next(
        index
        for index, command in enumerate(commands)
        if "weekly_slow_media" in command
    )

    assert preflight_index < media_test_index
    assert "ci-artifacts/weekly-media-preflight.log" in commands[preflight_index]


def test_weekly_slow_media_job_reports_media_tool_and_detector_lab_versions() -> None:
    """Weekly media diagnostics must identify their reviewed toolchain versions."""
    commands = _workflow_job_commands(WEEKLY_VALIDATION_WORKFLOW_PATH, "slow-e2e")

    assert any("ffmpeg -version" in command for command in commands)
    assert any("ffprobe -version" in command for command in commands)
    assert any(
        ".venv/bin/python --version" in command
        and "import cv2" in command
        and "import numpy" in command
        and "opencv-python-headless==" in command
        and "numpy==" in command
        for command in commands
    )


def test_weekly_slow_media_target_ownership_is_explicit() -> None:
    """Weekly media confidence must contain exactly its reviewed slow suites."""
    manifest = json.loads(CI_TARGET_MANIFEST_PATH.read_text())
    weekly_targets = set(manifest["targets"]["weekly_slow_media"])

    assert weekly_targets == {
        "tests/test_detector_lab_real_media.py",
        "tests/test_detectors_integration.py",
        "tests/test_e2e_local_session_real_media.py",
        "tests/test_e2e_session_ground_truth_local.py",
    }


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

    assert frozenset(workflow.job("main-gate").dependencies) == MAIN_GATE_REQUIRED_JOBS


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
