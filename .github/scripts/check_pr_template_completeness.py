#!/usr/bin/env python3
"""Lightweight CI guard for the repo PR template's key sections."""

from __future__ import annotations

import os
import re
import sys


HEADING_PATTERN = re.compile(r"^## (?P<title>.+)$", re.MULTILINE)
REQUIRED_SECTIONS = (
    "Validation Run",
    "Fixture / Environment Impact",
    "Docs Impact",
)
SECTION_VALIDATION = "Validation Run"
SECTION_FIXTURE = "Fixture / Environment Impact"
SECTION_DOCS = "Docs Impact"
COMMANDS_MARKER = "Commands run:"
WHY_MARKER = "Why these lanes were enough:"
PLACEHOLDER_MARKER = "# paste the commands you actually ran"


def _normalize_body(body: str) -> str:
    """Return one PR body with predictable line endings for heading parsing."""
    return body.replace("\r\n", "\n").replace("\r", "\n")


def _section_body(body: str, heading: str) -> str | None:
    """Return the body text for one level-two heading."""
    matches = list(HEADING_PATTERN.finditer(body))
    for index, match in enumerate(matches):
        if match.group("title").strip() != heading:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        return body[start:end].strip()
    return None


def _has_checked_option(section_body: str) -> bool:
    """Return whether a section contains at least one selected checkbox."""
    return bool(re.search(r"^- \[[xX]\] ", section_body, re.MULTILINE))


def _has_real_command(section_body: str) -> bool:
    """Return whether the validation section lists at least one real command."""
    command_block = section_body
    if COMMANDS_MARKER in section_body and WHY_MARKER in section_body:
        command_block = section_body.split(COMMANDS_MARKER, 1)[1].split(
            WHY_MARKER, 1
        )[0]

    for line in command_block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("##"):
            continue
        if stripped in {COMMANDS_MARKER, WHY_MARKER, "```bash", "```"}:
            continue
        if stripped.startswith(PLACEHOLDER_MARKER):
            continue
        if stripped == "-":
            continue
        return True
    return False


def validation_failures(body: str) -> tuple[str, ...]:
    """Return all missing or incomplete required PR-template parts.

    Keep this intentionally narrow: prove that the PR body names the
    validation commands and makes explicit docs and fixture/environment
    choices, without trying to score the whole PR.
    """
    failures: list[str] = []
    body = _normalize_body(body)

    if not body.strip():
        return ("PR body is empty; fill out the required PR template sections.",)

    sections = {heading: _section_body(body, heading) for heading in REQUIRED_SECTIONS}

    for heading, section_body in sections.items():
        if section_body is None:
            failures.append(f"missing required PR section: {heading}")

    validation_section = sections.get(SECTION_VALIDATION)
    if validation_section is not None and not _has_real_command(validation_section):
        failures.append(
            "Validation Run must list at least one actual command, not only the template placeholder"
        )

    fixture_section = sections.get(SECTION_FIXTURE)
    if fixture_section is not None and not _has_checked_option(fixture_section):
        failures.append("Fixture / Environment Impact must select one checkbox option")

    docs_section = sections.get(SECTION_DOCS)
    if docs_section is not None and not _has_checked_option(docs_section):
        failures.append("Docs Impact must select one checkbox option")

    return tuple(failures)


def main() -> int:
    """Run the lightweight PR-template completeness guard."""
    body = os.environ.get("PR_BODY", "")
    failures = validation_failures(body)
    if not failures:
        print("PR template completeness check passed")
        return 0

    print("PR template completeness check failed:", file=sys.stderr)
    for failure in failures:
        print(f"- {failure}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
