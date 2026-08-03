#!/usr/bin/env python3
"""Report local setup readiness without exposing environment values."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Literal


REPO_ROOT = Path(__file__).resolve().parents[2]
NODE_VERSION_PATTERN = re.compile(r"^v?(\d+)\.\d+\.\d+$")
NPM_PACKAGE_MANAGER_PATTERN = re.compile(r"^npm@(\d+\.\d+\.\d+)$")
POSTGRES_BACKEND_NAMES = (
    "ESM_SESSION_STORE_BACKEND",
    "ESM_ALERT_STORE_BACKEND",
)
POSTGRES_URL_NAMES = (
    "ESM_POSTGRES_SESSION_DATABASE_URL",
    "ESM_POSTGRES_ALERT_DATABASE_URL",
)
POSTGRES_LIVE_SMOKE_NAMES = (
    "POSTGRES_SESSION_STORE_REAL_SMOKE",
    "POSTGRES_ALERT_STORE_REAL_SMOKE",
)
VersionReader = Callable[[tuple[str, ...]], str | None]
DiagnosticStatus = Literal["ok", "advisory", "optional", "error"]


@dataclass(frozen=True)
class Diagnostic:
    """One safe, operator-facing environment readiness result."""

    name: str
    status: DiagnosticStatus
    detail: str

    @property
    def failed(self) -> bool:
        """Return whether this result must make the command fail."""
        return self.status == "error"

    def render(self) -> str:
        """Return one stable line without configuration values or paths."""
        return f"[{self.status}] {self.name}: {self.detail}"


def _read_command_version(command: tuple[str, ...]) -> str | None:
    """Return one command's first version line, or no value when unavailable."""
    if shutil.which(command[0]) is None:
        return None

    result = subprocess.run(command, capture_output=True, check=False, text=True)
    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        if line.strip():
            return line.strip()
    return None


def _read_text(path: Path) -> str | None:
    """Return one nonempty tracked text value when it is available."""
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _python_diagnostic(
    default: str | None, version: tuple[int, int, int]
) -> Diagnostic:
    """Classify the running Python against the tracked compatibility policy."""
    current = f"{version[0]}.{version[1]}.{version[2]}"
    if default != "3.12":
        return Diagnostic("Python", "error", "tracked default must be 3.12")
    if version[:2] < (3, 12):
        return Diagnostic("Python", "error", f"requires >=3.12; found {current}")
    if version[:2] == (3, 12):
        return Diagnostic("Python", "ok", f"{current} (default)")
    return Diagnostic("Python", "advisory", f"{current} (supported, non-default)")


def _node_diagnostic(default: str | None, version: str | None) -> Diagnostic:
    """Classify Node against the tracked major-version owner."""
    if default is None or not default.isdecimal():
        return Diagnostic("Node.js", "error", ".nvmrc must declare one major version")
    if version is None:
        return Diagnostic("Node.js", "error", f"requires Node.js {default}.x")

    match = NODE_VERSION_PATTERN.fullmatch(version)
    if match is None:
        return Diagnostic("Node.js", "error", "version output is not recognized")
    if int(match.group(1)) != int(default):
        return Diagnostic("Node.js", "error", f"requires {default}.x; found {version}")
    return Diagnostic("Node.js", "ok", version)


def _npm_diagnostic(package_manager: str | None, version: str | None) -> Diagnostic:
    """Classify npm against the exact frontend package-manager owner."""
    if package_manager is None:
        return Diagnostic("npm", "error", "frontend packageManager must declare npm")
    match = NPM_PACKAGE_MANAGER_PATTERN.fullmatch(package_manager)
    if match is None:
        return Diagnostic(
            "npm", "error", "frontend packageManager must pin npm exactly"
        )
    if version is None:
        return Diagnostic("npm", "error", f"requires npm {match.group(1)}")
    if version != match.group(1):
        return Diagnostic("npm", "error", f"requires {match.group(1)}; found {version}")
    return Diagnostic("npm", "ok", version)


def _required_command_diagnostic(
    name: str,
    command: tuple[str, ...],
    version_reader: VersionReader,
) -> Diagnostic:
    """Return a safe presence and version result for one host command."""
    version = version_reader(command)
    if version is None:
        return Diagnostic(name, "error", "required command is missing or unusable")
    return Diagnostic(name, "ok", version)


def _venv_diagnostic(repo_root: Path) -> Diagnostic:
    """Report whether the repository virtual environment has been created."""
    python_name = "python.exe" if sys.platform == "win32" else "python"
    venv_python = (
        repo_root
        / ".venv"
        / ("Scripts" if sys.platform == "win32" else "bin")
        / python_name
    )
    if venv_python.is_file():
        return Diagnostic("Repository virtual environment", "ok", "available")
    return Diagnostic(
        "Repository virtual environment",
        "error",
        "missing; run just setup",
    )


def _postgres_diagnostic(environment: Mapping[str, str]) -> Diagnostic:
    """Report opt-in PostgreSQL configuration without exposing its values."""
    configured = (
        any(
            environment.get(name, "").strip().lower() == "postgres"
            for name in POSTGRES_BACKEND_NAMES
        )
        or any(environment.get(name, "").strip() for name in POSTGRES_URL_NAMES)
        or any(
            environment.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
            for name in POSTGRES_LIVE_SMOKE_NAMES
        )
    )
    detail = "configured (optional)" if configured else "not configured (optional)"
    return Diagnostic("PostgreSQL", "optional", detail)


def _representative_media_diagnostic(repo_root: Path) -> Diagnostic:
    """Report optional representative media presence without listing local paths."""
    media_root = repo_root / "tests" / "fixtures" / "media" / "representative"
    available = any(media_root.rglob("*.mp4")) or any(media_root.rglob("index.m3u8"))
    detail = "available (optional)" if available else "not configured (optional)"
    return Diagnostic("Representative local media", "optional", detail)


def _frontend_package_manager(repo_root: Path) -> str | None:
    """Return the exact npm owner declared by the frontend package manifest."""
    try:
        package = json.loads(
            (repo_root / "frontend" / "package.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return None
    package_manager = package.get("packageManager")
    return package_manager if isinstance(package_manager, str) else None


def collect_environment_diagnostics(
    repo_root: Path,
    *,
    environment: Mapping[str, str],
    version_reader: VersionReader = _read_command_version,
    python_version: tuple[int, int, int] = sys.version_info[:3],
) -> tuple[Diagnostic, ...]:
    """Collect deterministic readiness results without opening external services."""
    return (
        _python_diagnostic(_read_text(repo_root / ".python-version"), python_version),
        _node_diagnostic(
            _read_text(repo_root / ".nvmrc"), version_reader(("node", "--version"))
        ),
        _npm_diagnostic(
            _frontend_package_manager(repo_root), version_reader(("npm", "--version"))
        ),
        _required_command_diagnostic("uv", ("uv", "--version"), version_reader),
        _required_command_diagnostic("just", ("just", "--version"), version_reader),
        _required_command_diagnostic("FFmpeg", ("ffmpeg", "-version"), version_reader),
        _required_command_diagnostic(
            "FFprobe", ("ffprobe", "-version"), version_reader
        ),
        _required_command_diagnostic("Git", ("git", "--version"), version_reader),
        _required_command_diagnostic(
            "Git LFS", ("git", "lfs", "version"), version_reader
        ),
        _venv_diagnostic(repo_root),
        _postgres_diagnostic(environment),
        _representative_media_diagnostic(repo_root),
        Diagnostic("External streams", "optional", "manual confidence only"),
    )


def main() -> int:
    """Print readiness results and return nonzero only for required failures."""
    diagnostics = collect_environment_diagnostics(REPO_ROOT, environment=os.environ)
    for diagnostic in diagnostics:
        print(diagnostic.render())
    return int(any(diagnostic.failed for diagnostic in diagnostics))


if __name__ == "__main__":
    raise SystemExit(main())
