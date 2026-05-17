#!/usr/bin/env python3
"""Resolve one stable CI target group from the canonical manifest for workflows.

The active workflow consumers are the broad contract-style jobs in `ci.yml`
and the heavier weekly validation lanes. Small one-off smoke paths stay inline
in the workflow when extracting them would add noise without reducing drift.
The drift check then treats the reader-backed `test-and-build` contract lane
as the workflow-side alignment target for those shared `ci.yml` groups.

For task-9's final frontend split, this reader resolves the shared
`frontend_contract` workflow lane, while the narrower hook-level frontend tests
stay policy-only in `check_main_pr_consistency.py`.
"""

from __future__ import annotations

import argparse
import sys

from ci_target_manifest import ManifestError, manifest_group_targets


def _read_group(group: str, subgroup: str | None) -> list[str]:
    """Return one target group from the manifest.

    Stable manifests now use top-level groups only. The deprecated subgroup
    flag remains as a guard so older call sites fail with a clear message.
    """
    if subgroup is None:
        return list(manifest_group_targets(group))

    raise ManifestError(
        "Nested subgroups are no longer supported; use a stable top-level target group."
    )


def _build_parser() -> argparse.ArgumentParser:
    """Return the CLI parser for one target-group read request."""
    parser = argparse.ArgumentParser()
    parser.add_argument("group", help="Top-level target group name")
    parser.add_argument(
        "--subgroup",
        help="Deprecated nested subgroup name; stable manifests should use top-level groups",
    )
    parser.add_argument(
        "--separator",
        choices=("newline", "space"),
        default="newline",
        help="How to print the resolved targets",
    )
    parser.add_argument(
        "--strip-prefix",
        help="Optional leading path prefix to remove from each resolved target",
    )
    return parser


def _normalize_targets(targets: list[str], strip_prefix: str | None) -> list[str]:
    """Return resolved targets after an optional leading-prefix strip."""
    if strip_prefix is None:
        return targets

    return [
        target.removeprefix(strip_prefix)
        if target.startswith(strip_prefix)
        else target
        for target in targets
    ]


def _print_targets(targets: list[str], separator: str) -> None:
    """Print resolved targets in one shell-friendly format."""
    if separator == "space":
        print(" ".join(targets))
        return

    print("\n".join(targets))


def main() -> int:
    """Print one manifest target group in a shell-friendly format.

    In `ci.yml`, this currently powers the shared backend and frontend
    contract lanes in `test-and-build`. The frontend lane strips the leading
    `frontend/` prefix because Vitest runs from that working directory, while
    the tiny integration smoke path stays inline outside the reader on
    purpose.
    """
    args = _build_parser().parse_args()

    try:
        targets = _read_group(args.group, args.subgroup)
    except ManifestError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    targets = _normalize_targets(targets, args.strip_prefix)
    _print_targets(targets, args.separator)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
