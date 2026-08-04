# Development Environment Audit

This audit maps the current setup and diagnostic ownership. It distinguishes
the recommended contributor path from supported packaging and host-tool paths.

## Setup Ownership

| Surface | Current owner | Current path | Role |
| --- | --- | --- | --- |
| Python version | `.python-version`, `pyproject.toml`, CI | Python 3.12 default; `>=3.12` package floor | Contributor default and compatibility claim. |
| Node and npm versions | `.nvmrc`, `frontend/package.json` | Node 22; installer aligns npm to `packageManager` | Frontend toolchain contract. |
| Locked contributor environment | `uv.lock` | `uv sync --locked --extra dev` | Complete reproducible contributor and AI-agent environment. |
| Editable packaging smoke | `pyproject.toml` | `pip install -e .` | Valid packaging-compatibility check; not a locked setup replacement. |
| Focused editable environments | `pyproject.toml` extras | `pip install -e .[test]`, `.[lint]`, `.[typecheck]`, or `.[dev]` | Valid focused CI and packaging paths. |
| Frontend dependencies | `scripts/install_frontend_dependencies.sh` | Select Node 22, align npm, then run `npm ci` | Installs the lockfile-pinned frontend graph and retries one transient failure. |
| Local command harness | `justfile` | `just setup` and `just <recipe>` | Setup and daily validation entrypoints. |
| CI tool versions | GitHub workflows | `setup-python`, `setup-node`, `setup-uv`, and weekly FFmpeg install | Validated reference environment, not a local installer. |

## Frozen Recommended Setup Path

`just setup` is the contributor and AI-agent setup command. It runs, in order:

```bash
uv sync --locked --extra dev
cd frontend && bash ../scripts/install_frontend_dependencies.sh
just env-check
```

This command prepares repository-managed Python and frontend dependencies,
then reports whether the host environment matches the project contract. It
does not install Python, Node, FFmpeg, Git LFS, PostgreSQL, representative
media, or other operating-system-level dependencies.

The editable `pip` commands remain supported for their narrower packaging and
focused-extra purposes. They are not the recommended general contributor
setup because they do not use the committed lockfile resolution.

## Frozen Capability Contract

`just env-check` owns deterministic local readiness diagnostics. It checks
tracked version owners, required host tools, and repository `.venv` presence;
it reports optional capability status without inspecting configuration values.

It exits nonzero when a required tool is missing or incompatible. It exits
successfully when optional capabilities are absent, while reporting `not
configured (optional)`. Diagnostics never print secret values, database URLs,
or complete environment contents.

| Capability | Required contract | Exit behavior |
| --- | --- | --- |
| Python | Present and supported at `>=3.12`; report 3.12 as the default and CI-validated line. | Fail when missing or below 3.12. A supported newer version is advisory, not a failure. |
| Node.js | Present in the `22.x` family selected by `.nvmrc`. | Fail when missing or outside Node 22. |
| npm | Present at the exact `packageManager` version, currently 11.15.0. | Fail when missing or not aligned after setup. |
| uv and just | Present for the recommended locked setup and command harness. | Fail when either command is absent. |
| Git and Git LFS | Present and usable for repository history and checked-in LFS media. | Fail when either command is absent. |
| FFmpeg and FFprobe | Both present on `PATH` and executable. The weekly Ubuntu 6.1.1 package is a reference, not a local pin. | Fail when either command is absent or unusable; report versions without exact cross-platform comparison. |
| PostgreSQL selection, URL, and live-smoke flags | Explicit opt-in only. | Report configured or `not configured (optional)`; never connect or fail ordinary setup. |
| Representative local media | Optional local/manual confidence assets. | Report available or `not configured (optional)`; never fail ordinary setup. |
| External streams | Manual confidence only. | Report as out of scope; never contact a provider. |

Git LFS is required because checked-in media includes LFS-managed video
segments. PostgreSQL and representative media are not comparable prerequisites:
they widen validation confidence but are intentionally outside the normal local
workflow.

## Configuration Boundary

The repository ignores `.env` files and tracks [`.env.example`](../.env.example)
as a configuration reference. Application code reads process environment values
directly; it does not currently auto-load `.env`. Source or export values
explicitly. The example contains only safe local defaults and commented opt-in
names, never keys, database URLs, or generated credentials.

Detailed PostgreSQL and share-mode configuration remains owned by
[testing-and-validation.md](./testing-and-validation.md) and
[fastapi-boundary.md](./fastapi-boundary.md). This audit does not change those
runtime contracts.
