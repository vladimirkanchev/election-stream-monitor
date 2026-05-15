#!/usr/bin/env python3
"""Resolve one stable CI target group from the canonical manifest."""

from __future__ import annotations

import argparse
import sys

from ci_target_manifest import CiTargetManifest, ManifestError


def _read_group(group: str, subgroup: str | None) -> list[str]:
    """Return one target group from the manifest.

    Stable manifests now use top-level groups only. The deprecated subgroup
    flag remains as a guard so older call sites fail with a clear message.
    """
    if subgroup is None:
        return list(CiTargetManifest.load().group_targets(group))

    raise ManifestError(
        "Nested subgroups are no longer supported; use a stable top-level target group."
    )


def main() -> int:
    """Print one manifest target group in a shell-friendly format."""
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
    args = parser.parse_args()

    try:
        targets = _read_group(args.group, args.subgroup)
    except ManifestError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.separator == "space":
        print(" ".join(targets))
    else:
        print("\n".join(targets))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
