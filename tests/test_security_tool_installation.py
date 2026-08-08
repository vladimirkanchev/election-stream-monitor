"""Focused regression coverage for checksum-verified security-tool bootstrap."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

SCRIPT_PATH = Path("scripts/install_security_tool.py")
MANIFEST_PATH = Path(".github/security_tools.json")
SPEC = importlib.util.spec_from_file_location("install_security_tool", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class _Response(io.BytesIO):
    """Provide the small context-manager surface used by urllib responses."""

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _archive(binary_name: str, content: bytes) -> bytes:
    """Build one in-memory tarball with the reviewed executable member."""
    archive_output = io.BytesIO()
    with tarfile.open(fileobj=archive_output, mode="w:gz") as archive:
        member = tarfile.TarInfo(binary_name)
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))
    return archive_output.getvalue()


def _manifest(path: Path, archive: bytes) -> None:
    """Write one minimal valid manifest for deterministic installer coverage."""
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tools": {
                    "gitleaks": {
                        "version": "test",
                        "platform": "linux-x64",
                        "url": "https://example.invalid/gitleaks.tar.gz",
                        "sha256": hashlib.sha256(archive).hexdigest(),
                        "archive_member": "gitleaks",
                        "binary": "gitleaks",
                    }
                },
            }
        )
    )


def _stub_linux_download(
    monkeypatch: pytest.MonkeyPatch,
    archive: bytes,
) -> None:
    """Provide one deterministic supported platform and archive download."""
    monkeypatch.setattr(installer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(installer.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        installer.request,
        "urlopen",
        lambda *_args, **_kwargs: _Response(archive),
    )


def test_manifest_pins_each_reviewed_security_tool() -> None:
    """Keep all planned host tools on explicit Linux x64 checksum records."""
    manifest = json.loads(MANIFEST_PATH.read_text())
    tools = manifest["tools"]

    assert manifest["schema_version"] == 1
    assert set(tools) == {"gitleaks", "actionlint", "shellcheck"}
    for tool in tools.values():
        assert tool["platform"] == "linux-x64"
        assert tool["url"].startswith("https://github.com/")
        assert len(tool["sha256"]) == 64
        assert tool["sha256"].islower()


def test_install_tool_verifies_archive_before_exposing_binary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A matching pinned archive installs only its named executable."""
    archive = _archive("gitleaks", b"#!/bin/sh\nexit 0\n")
    manifest_path = tmp_path / "tools.json"
    _manifest(manifest_path, archive)
    _stub_linux_download(monkeypatch, archive)

    destination = installer.install_tool(
        "gitleaks",
        bin_dir=tmp_path / "bin",
        manifest_path=manifest_path,
    )

    assert destination.read_bytes() == b"#!/bin/sh\nexit 0\n"
    assert destination.stat().st_mode & 0o100


def test_install_tool_rejects_a_checksum_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A corrupted download never becomes an executable in the tool directory."""
    archive = _archive("gitleaks", b"not the reviewed archive")
    manifest_path = tmp_path / "tools.json"
    _manifest(manifest_path, archive)
    manifest = json.loads(manifest_path.read_text())
    manifest["tools"]["gitleaks"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))
    _stub_linux_download(monkeypatch, archive)

    with pytest.raises(
        installer.ToolInstallError, match="Checksum verification failed"
    ):
        installer.install_tool(
            "gitleaks",
            bin_dir=tmp_path / "bin",
            manifest_path=manifest_path,
        )

    assert not (tmp_path / "bin" / "gitleaks").exists()


def test_install_tool_rejects_an_unknown_manifest_schema(tmp_path: Path) -> None:
    """An unsupported manifest cannot be interpreted as the current contract."""
    manifest_path = tmp_path / "tools.json"
    manifest_path.write_text(json.dumps({"schema_version": 2, "tools": {}}))

    with pytest.raises(installer.ToolInstallError, match="schema version 1"):
        installer.install_tool("gitleaks", manifest_path=manifest_path)
