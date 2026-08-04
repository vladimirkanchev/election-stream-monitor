"""User-facing CLI for running the FastAPI server in local or share mode.

This entrypoint keeps the project-stage startup story explicit:

- `local` preserves the friction-free trusted local runtime defaults
- `share` enables the protected sharing preset for temporary demo access

The CLI owns only lightweight startup policy and operator-facing guidance.
It validates bind exposure before delegating auth, limiter, and request
handling to the existing boundary modules.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import TextIO

import uvicorn

from api.app import app
from api_bind_policy import BindHostClass, classify_bind_host
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
    """Resolved mode, authentication, and limiter settings for one CLI startup."""

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
        help="manual API key for share mode; overrides ESM_API_AUTH_ALLOWED_KEYS",
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

    This keeps the user-facing startup path linear and fail-fast:

    1. validate the requested bind exposure
    2. resolve runtime policy
    3. print the startup summary
    4. start the ASGI server
    """

    _validate_cli_bind_policy(mode=args.mode, host=args.host)
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


def _validate_cli_bind_policy(*, mode: FastApiRunMode, host: str) -> None:
    """Reject malformed hosts and local binds that are not loopback-only.

    Validation runs before settings resolution or the Uvicorn handoff, so an
    invalid request cannot alter process-local runtime configuration.
    """

    host_class = classify_bind_host(host)
    if host_class is BindHostClass.INVALID:
        raise ApiBoundaryConfigurationError(
            "FastAPI bind host must be a numeric address or valid ASCII hostname "
            "without brackets, ports, or surrounding whitespace"
        )
    if mode == "local" and host_class is not BindHostClass.LOOPBACK:
        raise ApiBoundaryConfigurationError(
            "Local FastAPI mode only permits loopback bind hosts. "
            "Use `api_server_cli share --host <host>` for intentional network exposure"
        )


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
    if normalized_manual_api_key is not None:
        os.environ["ESM_API_AUTH_ALLOWED_KEYS"] = normalized_manual_api_key


def _normalize_manual_api_key(manual_api_key: str | None) -> str | None:
    """Normalize one manual share-mode key before exposing it to auth settings.

    An omitted CLI option leaves environment configuration in control. An
    explicitly blank value is invalid rather than a request to generate a new
    key, which keeps startup credentials predictable.
    """

    if manual_api_key is None:
        return None
    normalized = manual_api_key.strip()
    if not normalized:
        raise ApiBoundaryConfigurationError("Manual share-mode API key must not be blank")
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
                        "curl -H 'X-API-Key: <generated-api-key>' "
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
