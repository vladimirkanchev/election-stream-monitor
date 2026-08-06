"""Install one checksum-verified security tool for local or CI validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import stat
import tarfile
import tempfile
from pathlib import Path
from urllib import request

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = REPO_ROOT / ".github" / "security_tools.json"
DEFAULT_BIN_DIR = REPO_ROOT / ".tools" / "security" / "bin"
REQUIRED_TOOL_FIELDS = frozenset(
    {"version", "platform", "url", "sha256", "archive_member", "binary"}
)


class ToolInstallError(RuntimeError):
    """Raise an actionable error when a pinned tool cannot be installed."""


def _load_tool(tool_name: str, manifest_path: Path) -> dict[str, str]:
    """Load and validate one tool record from the checked-in manifest."""
    try:
        manifest = json.loads(manifest_path.read_text())
        tools = manifest["tools"]
        tool = tools[tool_name]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ToolInstallError(
            f"Could not load tool '{tool_name}' from {manifest_path}."
        ) from exc

    if not isinstance(tool, dict) or set(tool) != REQUIRED_TOOL_FIELDS:
        raise ToolInstallError(f"Tool '{tool_name}' has an invalid manifest record.")
    if not all(isinstance(value, str) and value for value in tool.values()):
        raise ToolInstallError(f"Tool '{tool_name}' has an incomplete manifest record.")
    if len(tool["sha256"]) != 64 or any(
        character not in "0123456789abcdef" for character in tool["sha256"]
    ):
        raise ToolInstallError(f"Tool '{tool_name}' must declare a lowercase SHA-256.")
    return tool


def _require_linux_x64(tool_name: str, tool: dict[str, str]) -> None:
    """Keep the initial verified-download contract explicit and portable later."""
    machine = platform.machine().lower()
    if (
        tool["platform"] != "linux-x64"
        or platform.system() != "Linux"
        or machine
        not in {
            "x86_64",
            "amd64",
        }
    ):
        raise ToolInstallError(
            f"{tool_name} is pinned only for Linux x64; install {tool_name} through "
            "your host package manager on this platform."
        )


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest for one downloaded archive."""
    digest = hashlib.sha256()
    with path.open("rb") as archive_file:
        for chunk in iter(lambda: archive_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    """Download one pinned archive without evaluating remote content."""
    with request.urlopen(url, timeout=30) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def _install_archive_member(
    archive_path: Path,
    member_name: str,
    destination: Path,
) -> None:
    """Copy only the reviewed executable from a verified tar archive."""
    with tarfile.open(archive_path, "r:gz") as archive:
        try:
            member = archive.getmember(member_name)
        except KeyError as exc:
            raise ToolInstallError(
                f"Verified archive does not contain expected executable '{member_name}'."
            ) from exc
        if not member.isfile():
            raise ToolInstallError(
                f"Archive member '{member_name}' is not a regular file."
            )
        source = archive.extractfile(member)
        if source is None:
            raise ToolInstallError(f"Could not extract archive member '{member_name}'.")
        with source, destination.open("wb") as output:
            shutil.copyfileobj(source, output)


def install_tool(
    tool_name: str,
    bin_dir: Path = DEFAULT_BIN_DIR,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> Path:
    """Install one named tool from its checked-in checksum-verified archive."""
    tool = _load_tool(tool_name, manifest_path)
    _require_linux_x64(tool_name, tool)
    bin_dir.mkdir(parents=True, exist_ok=True)
    destination = bin_dir / tool["binary"]

    with tempfile.TemporaryDirectory(prefix=f"esm-{tool_name}-") as temporary_dir:
        archive_path = Path(temporary_dir) / "tool.tar.gz"
        _download(tool["url"], archive_path)
        if _sha256(archive_path) != tool["sha256"]:
            raise ToolInstallError(f"Checksum verification failed for {tool_name}.")
        temporary_binary = Path(temporary_dir) / tool["binary"]
        _install_archive_member(archive_path, tool["archive_member"], temporary_binary)
        shutil.copyfile(temporary_binary, destination)
        destination.chmod(destination.stat().st_mode | stat.S_IXUSR)

    print(f"Installed {tool_name} {tool['version']} to {destination}")
    return destination


def main() -> int:
    """Install one declared security tool into an ignored local directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", choices=("gitleaks", "actionlint", "shellcheck"))
    parser.add_argument("--bin-dir", type=Path, default=DEFAULT_BIN_DIR)
    arguments = parser.parse_args()
    try:
        install_tool(arguments.tool, arguments.bin_dir)
    except (OSError, tarfile.TarError, ToolInstallError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
