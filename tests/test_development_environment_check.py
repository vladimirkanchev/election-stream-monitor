"""Focused regression coverage for deterministic local environment diagnostics."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

environment_check = importlib.import_module("check_development_environment")
JUSTFILE_PATH = Path("justfile")


def _just_recipe_body(recipe_name: str) -> str:
    """Return one recipe body for public harness-contract assertions."""
    lines = JUSTFILE_PATH.read_text(encoding="utf-8").splitlines()
    recipe_start = lines.index(f"{recipe_name}:") + 1
    body: list[str] = []
    for line in lines[recipe_start:]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


def _write_environment_contract(repo_root: Path) -> None:
    (repo_root / ".python-version").write_text("3.12\n", encoding="utf-8")
    (repo_root / ".nvmrc").write_text("22\n", encoding="utf-8")
    frontend = repo_root / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps({"packageManager": "npm@11.15.0"}), encoding="utf-8"
    )
    venv_python = repo_root / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.touch()


def _version_reader(versions: dict[tuple[str, ...], str]):
    """Return deterministic command-version output for one test environment."""
    return lambda command: versions.get(command)


def _valid_versions() -> dict[tuple[str, ...], str]:
    """Return one complete valid host-tool version map."""
    return {
        ("node", "--version"): "v22.23.2",
        ("npm", "--version"): "11.15.0",
        ("uv", "--version"): "uv 0.10.7",
        ("just", "--version"): "just 1.52.0",
        ("ffmpeg", "-version"): "ffmpeg version 6.1.1",
        ("ffprobe", "-version"): "ffprobe version 6.1.1",
        ("git", "--version"): "git version 2.43.0",
        ("git", "lfs", "version"): "git-lfs/3.4.1",
    }


def _by_name(diagnostics):
    """Index diagnostic results by their stable operator-facing names."""
    return {diagnostic.name: diagnostic for diagnostic in diagnostics}


def test_environment_check_accepts_required_tools_and_optional_absence(
    tmp_path: Path,
) -> None:
    """A normal setup must not require PostgreSQL or representative media."""
    _write_environment_contract(tmp_path)

    diagnostics = environment_check.collect_environment_diagnostics(
        tmp_path,
        environment={},
        version_reader=_version_reader(_valid_versions()),
        python_version=(3, 12, 3),
    )
    by_name = _by_name(diagnostics)

    assert not any(diagnostic.failed for diagnostic in diagnostics)
    assert by_name["Python"].detail.endswith("(default)")
    assert by_name["PostgreSQL"].detail == "not configured (optional)"
    assert by_name["Representative local media"].detail == "not configured (optional)"


def test_environment_check_rejects_missing_required_tool_without_secret_leaks(
    tmp_path: Path,
) -> None:
    """Missing Git LFS must fail while configured database values stay hidden."""
    _write_environment_contract(tmp_path)
    versions = _valid_versions()
    versions.pop(("git", "lfs", "version"))
    database_url = "postgresql://operator:super-secret@localhost:5432/esm"
    api_key = "share-key-must-not-appear"

    diagnostics = environment_check.collect_environment_diagnostics(
        tmp_path,
        environment={
            "ESM_POSTGRES_ALERT_DATABASE_URL": database_url,
            "ESM_API_AUTH_ALLOWED_KEYS": api_key,
        },
        version_reader=_version_reader(versions),
        python_version=(3, 12, 3),
    )
    output = "\n".join(diagnostic.render() for diagnostic in diagnostics)
    by_name = _by_name(diagnostics)

    assert by_name["Git LFS"].failed
    assert by_name["PostgreSQL"].detail == "configured (optional)"
    assert database_url not in output
    assert "super-secret" not in output
    assert api_key not in output


def test_environment_check_keeps_file_defaults_out_of_postgres_status(
    tmp_path: Path,
) -> None:
    """File-backed defaults and disabled smoke flags are not PostgreSQL setup."""
    _write_environment_contract(tmp_path)

    diagnostics = environment_check.collect_environment_diagnostics(
        tmp_path,
        environment={
            "ESM_SESSION_STORE_BACKEND": "file",
            "ESM_ALERT_STORE_BACKEND": "file",
            "POSTGRES_SESSION_STORE_REAL_SMOKE": "0",
        },
        version_reader=_version_reader(_valid_versions()),
        python_version=(3, 12, 3),
    )

    assert _by_name(diagnostics)["PostgreSQL"].detail == "not configured (optional)"


def test_environment_check_reports_supported_newer_python_as_advisory(
    tmp_path: Path,
) -> None:
    """A supported non-default Python line remains usable but visible."""
    _write_environment_contract(tmp_path)

    diagnostics = environment_check.collect_environment_diagnostics(
        tmp_path,
        environment={},
        version_reader=_version_reader(_valid_versions()),
        python_version=(3, 13, 1),
    )
    python = _by_name(diagnostics)["Python"]

    assert python.status == "advisory"
    assert not python.failed


def test_environment_check_rejects_unsupported_python(tmp_path: Path) -> None:
    """Python below the supported floor must fail with the required version."""
    _write_environment_contract(tmp_path)

    diagnostics = environment_check.collect_environment_diagnostics(
        tmp_path,
        environment={},
        version_reader=_version_reader(_valid_versions()),
        python_version=(3, 11, 9),
    )
    python = _by_name(diagnostics)["Python"]

    assert python.failed
    assert python.detail == "requires >=3.12; found 3.11.9"


@pytest.mark.parametrize(
    ("command", "actual_version", "diagnostic_name", "expected_detail"),
    (
        (("node", "--version"), "v20.20.0", "Node.js", "requires 22.x"),
        (("npm", "--version"), "10.9.8", "npm", "requires 11.15.0"),
    ),
)
def test_environment_check_reports_owned_tool_version_mismatches(
    tmp_path: Path,
    command: tuple[str, ...],
    actual_version: str,
    diagnostic_name: str,
    expected_detail: str,
) -> None:
    """Tracked Node and npm owners must reject incompatible local versions."""
    _write_environment_contract(tmp_path)
    versions = _valid_versions()
    versions[command] = actual_version

    diagnostics = environment_check.collect_environment_diagnostics(
        tmp_path,
        environment={},
        version_reader=_version_reader(versions),
        python_version=(3, 12, 3),
    )
    mismatch = _by_name(diagnostics)[diagnostic_name]

    assert mismatch.failed
    assert expected_detail in mismatch.detail


@pytest.mark.parametrize(
    ("name", "status", "detail", "expected_exit"),
    (
        ("PostgreSQL", "optional", "not configured (optional)", 0),
        ("Git LFS", "error", "required command is missing or unusable", 1),
    ),
)
def test_environment_check_main_reflects_required_failures_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    name: str,
    status: environment_check.DiagnosticStatus,
    detail: str,
    expected_exit: int,
) -> None:
    """The public command must fail for errors but not optional capabilities."""
    diagnostics = (environment_check.Diagnostic(name, status, detail),)
    monkeypatch.setattr(
        environment_check,
        "collect_environment_diagnostics",
        lambda *args, **kwargs: diagnostics,
    )

    assert environment_check.main() == expected_exit
    assert f"[{status}] {name}: {detail}" in capsys.readouterr().out


def test_env_check_recipe_delegates_to_the_diagnostic_script() -> None:
    """The public harness command must keep one diagnostic implementation owner."""
    assert _just_recipe_body("env-check").strip() == (
        "python3 .github/scripts/check_development_environment.py"
    )


def test_setup_recipe_uses_locked_dependency_owners() -> None:
    """Contributor setup must stay locked, frontend-aware, and host-tool neutral."""
    recipe = _just_recipe_body("setup")
    expected_commands = (
        "uv sync --locked --extra dev",
        "cd frontend && bash ../scripts/install_frontend_dependencies.sh",
        "just env-check",
    )

    positions = tuple(recipe.index(command) for command in expected_commands)
    assert positions == tuple(sorted(positions))
    assert all(
        term not in recipe.lower() for term in ("postgres", "git lfs", "representative")
    )


def test_env_example_is_explicit_and_secret_free() -> None:
    """The tracked reference must not imply dotenv loading or supply credentials."""
    example = Path(".env.example").read_text(encoding="utf-8")

    assert "does not auto-load .env" in example
    assert "ESM_SESSION_STORE_BACKEND=file" in example
    assert "ESM_ALERT_STORE_BACKEND=file" in example
    assert "ESM_FASTAPI_RUN_MODE=local" in example
    assert "# ESM_POSTGRES_SESSION_DATABASE_URL (set privately)" in example
    assert "# ESM_POSTGRES_ALERT_DATABASE_URL (set privately)" in example
    assert "# ESM_API_AUTH_ALLOWED_KEYS (set privately; do not leave blank)" in example
    assert "postgresql://" not in example
    assert "ESM_API_AUTH_ALLOWED_KEYS=example" not in example

    active_entries = {
        line.split("=", maxsplit=1)[0]: line.split("=", maxsplit=1)[1]
        for line in example.splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    assert active_entries == {
        "ESM_SESSION_STORE_BACKEND": "file",
        "ESM_ALERT_STORE_BACKEND": "file",
        "ESM_FASTAPI_RUN_MODE": "local",
    }
