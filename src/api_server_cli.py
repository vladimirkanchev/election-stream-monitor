"""User-facing CLI for running the FastAPI server in local or share mode.

This entrypoint keeps the project-stage startup story explicit:

- `local` preserves the friction-free trusted local runtime defaults
- `share` enables the protected sharing preset for temporary demo access

The CLI owns only lightweight startup policy and operator-facing guidance.
The underlying FastAPI auth, limiter, and request handling remain in their
existing boundary modules.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
import sys
from typing import Callable, TextIO

import uvicorn

from api.app import app
from api_boundary_config import (
    ApiAuthSettings,
    ApiBoundaryConfigurationError,
    ApiRateLimitSettings,
    FastApiRunMode,
    clear_fastapi_boundary_settings_caches,
    get_api_auth_settings,
    get_api_rate_limit_settings,
    validate_fastapi_boundary_settings,
)


@dataclass(frozen=True)
class FastApiCliRuntime:
    """Resolved runtime policy used by the user-facing FastAPI CLI.

    This is the small bridge object between:

    - CLI mode selection
    - boundary settings resolution
    - startup summary output
    """

    mode: FastApiRunMode
    auth_settings: ApiAuthSettings
    rate_limit_settings: ApiRateLimitSettings


ServerRunner = Callable[..., None]


def build_parser() -> argparse.ArgumentParser:
    """Create the parser for the supported FastAPI startup modes."""

    parser = argparse.ArgumentParser(
        description="Run the Election Stream Monitor FastAPI server"
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    local_parser = subparsers.add_parser(
        "local",
        help="run the local FastAPI server with trusted local defaults",
    )
    _add_common_server_arguments(local_parser)

    share_parser = subparsers.add_parser(
        "share",
        help="run the FastAPI server with protected temporary shared-access defaults",
    )
    _add_common_server_arguments(share_parser)
    share_parser.add_argument(
        "--api-key",
        default=None,
        help="manual API key for share mode; if omitted, one is generated",
    )

    return parser


def main() -> None:
    """Parse one startup mode and run the FastAPI app."""

    parser = build_parser()
    args = parser.parse_args()
    run_from_args(args)


def run_from_args(
    args: argparse.Namespace,
    *,
    stdout: TextIO = sys.stdout,
    server_runner: ServerRunner = uvicorn.run,
) -> None:
    """Apply one parsed startup mode and hand off to Uvicorn.

    This keeps the user-facing startup path linear:

    1. resolve runtime policy
    2. print the startup summary
    3. start the ASGI server
    """

    runtime = prepare_cli_runtime(
        mode=args.mode,
        manual_api_key=getattr(args, "api_key", None),
    )
    _write_startup_summary(
        runtime=runtime,
        host=args.host,
        port=args.port,
        stdout=stdout,
    )
    _run_server(server_runner, host=args.host, port=args.port)


def prepare_cli_runtime(
    *,
    mode: FastApiRunMode,
    manual_api_key: str | None = None,
) -> FastApiCliRuntime:
    """Apply one CLI mode to the current process and resolve its runtime policy.

    The helper mutates process-local env state on purpose because the current
    FastAPI boundary settings are env-driven and cached. That keeps the CLI
    aligned with the same settings seam the app itself uses at startup.
    """

    _apply_runtime_env(mode=mode, manual_api_key=manual_api_key)
    clear_fastapi_boundary_settings_caches()

    # Fail fast on impossible protected-boundary combinations before handing
    # off to Uvicorn. This keeps the CLI aligned with the same startup
    # validation philosophy the FastAPI lifespan uses.
    validate_fastapi_boundary_settings()

    return FastApiCliRuntime(
        mode=mode,
        auth_settings=get_api_auth_settings(),
        rate_limit_settings=get_api_rate_limit_settings(),
    )


def _add_common_server_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the shared host and port options to one startup subcommand."""

    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)


def _apply_runtime_env(
    *,
    mode: FastApiRunMode,
    manual_api_key: str | None,
) -> None:
    """Apply one CLI-selected mode to the current process environment.

    The CLI intentionally expresses startup policy through the same env-backed
    configuration seam used elsewhere, rather than introducing a second
    internal configuration pathway.
    """

    os.environ["ESM_FASTAPI_RUN_MODE"] = mode
    normalized_manual_api_key = _normalize_manual_api_key(manual_api_key)
    if normalized_manual_api_key is None:
        os.environ.pop("ESM_API_AUTH_ALLOWED_KEYS", None)
        return
    os.environ["ESM_API_AUTH_ALLOWED_KEYS"] = normalized_manual_api_key


def _normalize_manual_api_key(manual_api_key: str | None) -> str | None:
    """Normalize one manual share-mode key before exposing it to auth settings.

    Share mode treats blank or whitespace-only keys as absent so the generated
    key path can still produce a usable protected startup. Non-blank keys are
    stripped for copy/paste friendliness before entering the env-driven
    settings seam.
    """

    if manual_api_key is None:
        return None
    normalized = manual_api_key.strip()
    if not normalized:
        return None
    if "," in normalized:
        raise ApiBoundaryConfigurationError(
            "Manual share-mode API key must be one key value and may not contain commas"
        )
    return normalized


def _write_startup_summary(
    *,
    runtime: FastApiCliRuntime,
    host: str,
    port: int,
    stdout: TextIO,
) -> None:
    """Write one small startup summary for the selected FastAPI mode."""

    stdout.write("\n".join(_build_startup_summary_lines(runtime, host, port)) + "\n")


def _build_startup_summary_lines(
    runtime: FastApiCliRuntime,
    host: str,
    port: int,
) -> list[str]:
    """Return the startup summary lines for one selected FastAPI mode.

    Keeping line assembly separate from output makes the startup summary easier
    to test without coupling those tests to the server-runner handoff.
    """

    lines = [
        "Election Stream Monitor FastAPI",
        f"mode: {runtime.mode}",
        f"listen: http://{host}:{port}",
        f"auth: {'enabled' if runtime.auth_settings.enabled else 'disabled'}",
        "rate limiting: "
        f"{'enabled' if runtime.rate_limit_settings.enabled else 'disabled'}",
    ]

    if runtime.mode == "share":
        lines.extend(
            [
                "share mode is for temporary protected demo/shared access.",
                "share mode is not production-distributed hardened.",
            ]
        )
        if runtime.auth_settings.generated_api_key is not None:
            lines.extend(
                [
                    "",
                    "Generated API key:",
                    runtime.auth_settings.generated_api_key,
                    "",
                    "Send it in the X-API-Key header.",
                    (
                        "Example: "
                        f"curl -H 'X-API-Key: {runtime.auth_settings.generated_api_key}' "
                        f"http://{host}:{port}/sessions/<session_id>/alerts"
                    ),
                ]
            )
        else:
            lines.append("API key: configured manually")

    return lines


def _run_server(server_runner: ServerRunner, *, host: str, port: int) -> None:
    """Hand the assembled FastAPI app off to the selected server runner."""

    server_runner(
        app,
        host=host,
        port=port,
    )


if __name__ == "__main__":
    main()
