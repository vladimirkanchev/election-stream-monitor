"""Generate a frontend-readable detector manifest from the analyzer registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analyzer_registry import list_available_detectors


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for detector export."""
    parser = argparse.ArgumentParser(
        description="Export the detector catalog for the frontend.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the output JSON file.",
    )
    return parser


def main() -> None:
    """Write the current analyzer registry metadata to disk."""
    args = build_parser().parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(list_available_detectors(), indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
