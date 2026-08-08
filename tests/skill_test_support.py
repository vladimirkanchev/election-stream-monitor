"""Shared loaders and assertions for deterministic repo-skill tests."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parent.parent / ".agents" / "skills"
ARCHIVED_SKILLS_ROOT = SKILLS_ROOT.parent / "archived-skills"
REPOSITORY_ROOT = SKILLS_ROOT.parent.parent
SNAPSHOTS_ROOT = Path(__file__).resolve().parent / "fixtures" / "skill_output_snapshots"
MANUAL_PROMPT_EVALUATIONS_PATH = (
    REPOSITORY_ROOT / ".agents" / "evaluations" / "manual-prompt-evaluation.md"
)
SKILL_SECTION_ORDER = (
    "## Default approach",
    "## Output shape",
    "## Skill boundaries",
    "## Avoid",
)
REQUIRED_SKILL_FRONTMATTER_KEYS = frozenset({"name", "description"})
REPOSITORY_PATH_PREFIXES = (
    ".agents/",
    ".github/",
    "detector_lab/",
    "docs/",
    "frontend/",
    "scripts/",
    "src/",
    "tests/",
)
REPOSITORY_ROOT_FILES = frozenset(
    {
        "AGENTS.md",
        "README.md",
        "justfile",
        "pyproject.toml",
        "uv.lock",
    }
)
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")
INLINE_CODE_PATTERN = re.compile(r"`([^`]+)`")
JUST_RECIPE_PATTERN = re.compile(r"\bjust\s+([a-z][a-z0-9-]*)\b")
JUST_RECIPE_DEFINITION_PATTERN = re.compile(r"^([a-z][a-z0-9-]*):", re.MULTILINE)


@dataclass(frozen=True)
class SkillDocument:
    """Parsed markdown skill with the required discovery metadata."""

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


@dataclass(frozen=True)
class ManualPromptEvaluationCase:
    """One manually executed prompt with its routing expectation."""

    case_id: str
    prompt: str
    primary_skill: str
    required_properties: str
    avoided_behavior: str


def load_skill(skill_name: str) -> SkillDocument:
    """Load one repo-local skill by folder name."""
    skill_path = SKILLS_ROOT / skill_name / "SKILL.md"
    return load_skill_file(skill_path)


def load_skill_file(skill_path: Path) -> SkillDocument:
    """Load one active or archived skill from its explicit file path."""
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


def load_manual_prompt_evaluation_cases(
    path: Path = MANUAL_PROMPT_EVALUATIONS_PATH,
) -> list[ManualPromptEvaluationCase]:
    """Load labelled cases without treating the catalog as a model-output fixture."""
    text = path.read_text(encoding="utf-8")
    sections = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    cases = []

    for section in sections:
        _title, _, body = section.partition("\n")
        fields = {
            match.group("label"): match.group("value").strip()
            for match in re.finditer(
                r"^- (?P<label>Case ID|User prompt|Expected primary skill|"
                r"Required response properties|Avoid): (?P<value>.+)$",
                body,
                flags=re.MULTILINE,
            )
        }
        required_labels = {
            "Case ID",
            "User prompt",
            "Expected primary skill",
            "Required response properties",
            "Avoid",
        }
        missing_labels = required_labels - fields.keys()
        if missing_labels:
            raise ValueError(
                f"Manual prompt evaluation case is missing fields: {sorted(missing_labels)}"
            )

        cases.append(
            ManualPromptEvaluationCase(
                case_id=fields["Case ID"].strip("`"),
                prompt=fields["User prompt"].strip('"'),
                primary_skill=fields["Expected primary skill"].strip("`"),
                required_properties=fields["Required response properties"],
                avoided_behavior=fields["Avoid"],
            )
        )

    return cases


def list_skill_files() -> list[Path]:
    """Return all repo-local skill files relative to the skills root."""
    return sorted(
        path.relative_to(SKILLS_ROOT)
        for path in SKILLS_ROOT.rglob("SKILL.md")
    )


def list_archived_skill_files() -> list[Path]:
    """Return archived skill files as absolute paths for explicit validation."""
    return sorted(ARCHIVED_SKILLS_ROOT.rglob("SKILL.md"))


def list_validated_skill_files() -> list[Path]:
    """Return every active and archived skill file checked by the harness."""
    active_files = (SKILLS_ROOT / relative_path for relative_path in list_skill_files())
    return sorted([*active_files, *list_archived_skill_files()])


def extract_repository_references(text: str) -> set[str]:
    """Return explicit repository paths from Markdown links and inline code."""
    references = {
        target.split("#", maxsplit=1)[0]
        for target in MARKDOWN_LINK_PATTERN.findall(text)
        if _is_repository_link_target(target)
    }
    references.update(
        candidate
        for candidate in INLINE_CODE_PATTERN.findall(text)
        if _is_repository_path_candidate(candidate)
    )
    return references


def resolve_repository_reference(skill_path: Path, reference: str) -> Path:
    """Resolve one explicit repository reference from the owning skill file."""
    base_path = skill_path.parent if reference.startswith(("./", "../")) else REPOSITORY_ROOT
    return (base_path / reference).resolve()


def extract_just_recipes(text: str) -> set[str]:
    """Return explicit `just <recipe>` commands from inline code examples."""
    return {
        recipe
        for code_span in INLINE_CODE_PATTERN.findall(text)
        for recipe in JUST_RECIPE_PATTERN.findall(code_span)
    }


def list_just_recipes(justfile_path: Path) -> set[str]:
    """Return recipe names declared by the repository justfile."""
    text = justfile_path.read_text(encoding="utf-8")
    return set(JUST_RECIPE_DEFINITION_PATTERN.findall(text))


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


def contains_in_order(text: str, snippets: Sequence[str]) -> bool:
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


def assert_all_snippets_present(text: str, snippets: Sequence[str]) -> None:
    """Assert that each expected snippet appears in the given text."""
    missing = [snippet for snippet in snippets if snippet not in text]
    assert not missing, f"Missing snippets: {missing}"


def assert_all_snippets_absent(text: str, snippets: Sequence[str]) -> None:
    """Assert that each excluded snippet is absent from the given text."""
    unexpected = [snippet for snippet in snippets if snippet in text]
    assert not unexpected, f"Unexpected snippets: {unexpected}"


def _is_repository_link_target(target: str) -> bool:
    """Return whether a Markdown destination is an internal repository path."""
    return bool(target) and not target.startswith(("#", "http://", "https://", "mailto:"))


def _is_repository_path_candidate(candidate: str) -> bool:
    """Return whether one inline-code span is an unambiguous repository path."""
    return candidate in REPOSITORY_ROOT_FILES or candidate.startswith(
        REPOSITORY_PATH_PREFIXES
    )


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse the strict frontmatter contract used by active skill files."""
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
        normalized_key = key.strip()
        if normalized_key in frontmatter:
            raise ValueError(f"Duplicate frontmatter key: {normalized_key}")
        frontmatter[normalized_key] = value.strip()

    actual_keys = frozenset(frontmatter)
    if actual_keys != REQUIRED_SKILL_FRONTMATTER_KEYS:
        missing = REQUIRED_SKILL_FRONTMATTER_KEYS - actual_keys
        unexpected = actual_keys - REQUIRED_SKILL_FRONTMATTER_KEYS
        details = []
        if missing:
            details.append(f"missing: {', '.join(sorted(missing))}")
        if unexpected:
            details.append(f"unexpected: {', '.join(sorted(unexpected))}")
        raise ValueError(f"Invalid frontmatter keys ({'; '.join(details)})")

    body = "\n".join(lines[closing_index + 1:])
    return frontmatter, body
