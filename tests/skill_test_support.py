"""Helpers for deterministic tests around repo-local Codex skills."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


SKILLS_ROOT = Path(__file__).resolve().parent.parent / ".agents" / "skills"
SNAPSHOTS_ROOT = Path(__file__).resolve().parent / "fixtures" / "skill_output_snapshots"
SKILL_SECTION_ORDER = (
    "## Default approach",
    "## Output shape",
    "## Skill boundaries",
    "## Avoid",
)


@dataclass(frozen=True)
class SkillDocument:
    """Parsed markdown skill with minimal frontmatter support."""

    path: Path
    name: str
    description: str
    body: str

    @property
    def text(self) -> str:
        """Return the full searchable skill text."""
        return f"{self.name}\n{self.description}\n{self.body}"


@dataclass(frozen=True)
class ScenarioExpectation:
    """Expected skill coverage for one representative prompt."""

    skill_name: str
    required_snippets: tuple[str, ...]


@dataclass(frozen=True)
class SnapshotExpectation:
    """Expected output snapshot metadata for one skill."""

    skill_name: str
    snapshot_name: str
    required_order: tuple[str, ...]


def load_skill(skill_name: str) -> SkillDocument:
    """Load one repo-local skill by folder name."""
    skill_path = SKILLS_ROOT / skill_name / "SKILL.md"
    text = skill_path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)
    return SkillDocument(
        path=skill_path,
        name=frontmatter["name"],
        description=frontmatter["description"],
        body=body.strip(),
    )


def load_all_skills() -> dict[str, SkillDocument]:
    """Load all current repo-local skills keyed by folder name."""
    return {
        skill_dir.name: load_skill(skill_dir.name)
        for skill_dir in sorted(SKILLS_ROOT.iterdir())
        if skill_dir.is_dir()
    }


def list_skill_files() -> list[Path]:
    """Return all repo-local skill files relative to the skills root."""
    return sorted(
        path.relative_to(SKILLS_ROOT)
        for path in SKILLS_ROOT.rglob("SKILL.md")
    )


def extract_headings(body: str) -> list[str]:
    """Return markdown headings in source order."""
    return [
        line.strip()
        for line in body.splitlines()
        if line.startswith("#")
    ]


def load_snapshot(snapshot_name: str) -> str:
    """Load one expected output snapshot by filename."""
    return (SNAPSHOTS_ROOT / snapshot_name).read_text(encoding="utf-8").strip()


def extract_colon_headings(text: str) -> list[str]:
    """Return non-empty lines that behave like `Section:` headings."""
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().endswith(":")
    ]


def assert_contains_in_order(text: str, snippets: Sequence[str]) -> bool:
    """Return whether all snippets appear in the given order."""
    start_index = 0
    for snippet in snippets:
        found_index = text.find(snippet, start_index)
        if found_index < 0:
            return False
        start_index = found_index + len(snippet)
    return True


def snapshot_heading_matches_skill_text(skill_text: str, heading: str) -> bool:
    """Return whether one snapshot heading is represented by the skill text."""
    normalized = heading.removesuffix(":")
    if " or " in normalized:
        options = [part.strip() for part in normalized.split(" or ")]
        return any(option in skill_text for option in options)
    return normalized in skill_text or heading in skill_text


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse the minimal YAML frontmatter used by these skill files."""
    lines = text.splitlines()
    if len(lines) < 4 or lines[0].strip() != "---":
        raise ValueError("Missing YAML frontmatter start")

    closing_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing_index = index
            break
    if closing_index is None:
        raise ValueError("Missing YAML frontmatter end")

    frontmatter: dict[str, str] = {}
    for line in lines[1:closing_index]:
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"Invalid frontmatter line: {line}")
        frontmatter[key.strip()] = value.strip()

    missing_keys = {"name", "description"} - frontmatter.keys()
    if missing_keys:
        missing = ", ".join(sorted(missing_keys))
        raise ValueError(f"Missing frontmatter keys: {missing}")

    body = "\n".join(lines[closing_index + 1:])
    return frontmatter, body
