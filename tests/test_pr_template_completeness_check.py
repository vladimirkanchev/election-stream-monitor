"""Focused tests for the lightweight PR-template completeness guard."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

check_pr_template_completeness = importlib.import_module(
    "check_pr_template_completeness"
)


def _assert_has_failure(failures: tuple[str, ...], expected: str) -> None:
    """Assert one PR-template validation failure fragment."""
    assert any(expected in failure for failure in failures)


def test_complete_pr_body_passes() -> None:
    body = """
## Validation Run

Commands run:

```bash
just test-fast
just fixture-check
```

Why these lanes were enough:

- changed seams were detector rules and shared fixture docs only

## Fixture / Environment Impact

- [x] uses checked-in fixtures only
- [ ] no special fixture or environment impact

Notes:
- none

## Docs Impact

- [x] docs/testing-and-validation.md
- [ ] no docs change needed

Notes:
- updated local lane guidance
"""

    assert check_pr_template_completeness.validation_failures(body) == ()


def test_complete_pr_body_with_crlf_line_endings_passes() -> None:
    body = (
        "## Validation Run\r\n\r\n"
        "Commands run:\r\n\r\n"
        "```bash\r\n"
        "just test-fast\r\n"
        "```\r\n\r\n"
        "Why these lanes were enough:\r\n\r\n"
        "- changed seams were detector rules and shared fixture docs only\r\n\r\n"
        "## Fixture / Environment Impact\r\n\r\n"
        "- [x] uses checked-in fixtures only\r\n"
        "- [ ] no special fixture or environment impact\r\n\r\n"
        "## Docs Impact\r\n\r\n"
        "- [x] docs/testing-and-validation.md\r\n"
        "- [ ] no docs change needed\r\n"
    )

    assert check_pr_template_completeness.validation_failures(body) == ()


def test_empty_pr_body_fails() -> None:
    failures = check_pr_template_completeness.validation_failures("")

    assert failures == (
        "PR body is empty; fill out the required PR template sections.",
    )


def test_missing_required_sections_fail() -> None:
    failures = check_pr_template_completeness.validation_failures(
        "## Validation Run\n\nCommands run:\n\n```bash\njust test-fast\n```"
    )

    _assert_has_failure(failures, "missing required PR section: Fixture / Environment Impact")
    _assert_has_failure(failures, "missing required PR section: Docs Impact")


def test_placeholder_validation_commands_fail() -> None:
    body = """
## Validation Run

Commands run:

```bash
# paste the commands you actually ran
```

Why these lanes were enough:

- kept it simple

## Fixture / Environment Impact

- [x] no special fixture or environment impact

## Docs Impact

- [x] no docs change needed
"""

    failures = check_pr_template_completeness.validation_failures(body)

    _assert_has_failure(
        failures, "Validation Run must list at least one actual command"
    )


def test_fixture_and_docs_sections_require_a_choice() -> None:
    body = """
## Validation Run

Commands run:

```bash
just docs-check
```

Why these lanes were enough:

- docs-only PR

## Fixture / Environment Impact

- [ ] no special fixture or environment impact
- [ ] uses checked-in fixtures only

## Docs Impact

- [ ] no docs change needed
- [ ] docs/README.md
"""

    failures = check_pr_template_completeness.validation_failures(body)

    _assert_has_failure(
        failures, "Fixture / Environment Impact must select one checkbox option"
    )
    _assert_has_failure(failures, "Docs Impact must select one checkbox option")
