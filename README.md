# Election Stream Monitor

![License: MIT](https://img.shields.io/badge/license-MIT-green)

Election Stream Monitor is a local-first AI video-monitoring prototype for
election-related media. It helps surface video-quality problems that can make
real-time observation harder: a black picture, excessive blur, or a broken
source.

It is an advanced, desktop-oriented prototype for local development, demos,
and small monitoring runs, not a public Internet service or a finished
monitoring platform.

**Quick try:** run `npm --prefix frontend run dev`, choose `video_files`, and
select a local `.mp4`.

For contributor workflow, use [CONTRIBUTING.md](./CONTRIBUTING.md). For
maintainer and AI-agent routing, use [docs/README.md](./docs/README.md).

## Current Capabilities

- React/Electron desktop app backed by a local FastAPI runtime.
- Three input modes: local video files, local segmented/HLS-style folders, and
  direct remote `api_stream` inputs.
- Two production detectors: `Black Screen` and `Blur Check`, each with an
  explicit default alert rule.
- Session metadata, progress, detector results, and alerts persisted locally.
  File-backed storage is the default; PostgreSQL is an explicit opt-in for
  session and alert backends.
- A local, read-only MCP server for alert queries.

The UI selects a source and detector set, starts or ends monitoring, plays
supported local or remote HLS media through Electron, and shows session state
and alerts.

![Frontend screenshot](./docs/assets/Frontend.png)

Production detector registration is explicit in
[`src/detectors/registry.py`](./src/detectors/registry.py). Experimental blur
and motion work stays in [`detector_lab/`](./detector_lab/README.md) until it
is deliberately promoted. See [adding an analyzer](./docs/adding-an-analyzer.md)
for that promotion path.

## Input Modes

- `video_segments` — local `.ts` segment folders, usually around an `index.m3u8` playlist
- `video_files` — local `.mp4` files or folders
- `api_stream` — direct remote `.m3u8` URLs for bounded HTTP/HLS analysis;
  direct `.mp4` URLs are valid for source selection and playback, not remote
  analysis

## Current Scope And Limits

The project is intentionally narrow: detector coverage currently focuses on
black-screen and blur-related failures, and packaging remains
developer-oriented. It is not ready for public Internet deployment.

FastAPI `local` and temporary `share` access, authentication, rate limits, and
deployment gates are owned by the [FastAPI boundary guide](./docs/fastapi-boundary.md).
The MCP server remains a local `stdio`, read-only surface; see the
[MCP policy](./docs/mcp-server.md). Persistence selection, forward-only
PostgreSQL behavior, and rollout evidence are owned by the
[persistence audit](./docs/session-persistence-audit.md). Focused and
environment-sensitive validation lanes are described in
[testing and validation](./docs/testing-and-validation.md).

## Architecture At A Glance

This is still one local-first project, not a distributed platform, but the
main splits between frontend, backend, and tools are intentional. That fits
the current project stage: an advanced prototype approaching pre-pilot, with
clearer responsibilities than broad operational maturity.

In practice, the flow looks like this:

1. You choose a source, pick detectors, and start monitoring from the UI.
2. The frontend and Electron handle the visible workflow: setup, playback,
   status, alerts, and desktop-only jobs like local media serving and the HLS
   proxy path.
3. Electron starts and talks to the local FastAPI runtime. FastAPI exposes the
   desktop-backed HTTP boundary for session control, source checks, playback
   resolution, and alert/session reads.
4. FastAPI routes session operations into the shared backend services, which
   spawn and track the detached session worker that runs the monitoring flow.
5. Detectors and alert rules process the media, while local session state and
   the shared alert backend keep progress, results, and alerts.

FastAPI and MCP are separate entry points over local persisted data. FastAPI
owns the desktop HTTP path; MCP is the local read-only alert-query adapter
described in the [MCP policy](./docs/mcp-server.md).

The diagram below shows the same flow in one picture.

![Architecture outlook](./docs/assets/diagram_final.png)

### Who Owns What

- **Electron** owns the desktop shell, runtime startup, UI bridge, local media serving, and the HLS proxy path.
- **FastAPI** owns the local HTTP boundary: session control, source validation, playback resolution, and alert/session reads. Its access policy is documented in the [FastAPI boundary guide](./docs/fastapi-boundary.md).
- **Shared backend services and the detached session worker** own session execution, detector/rule processing, and session-state updates behind that HTTP boundary.
- **MCP** remains a separate local `stdio` read-only alert-query surface; its trust boundary is documented in the [MCP policy](./docs/mcp-server.md).
- **Local session data and the shared alert backend** persist progress, results, and alerts through the shared session-store contract.
- **FastAPI and MCP** read through the same persisted alert/session path, not separate stores or monitoring pipelines.

## Installation

Installation is developer-oriented rather than one-click.

You will need:

- Python `3.12+`
- Node.js `22.x` selected from [`.nvmrc`](./.nvmrc)
- npm, which the frontend installer sets to the declared `11.15.0`
- `ffmpeg` and `ffprobe` on `PATH`
- `uv` for the locked contributor and AI-agent setup flow
- `just` for the repository setup and validation commands

Set up the repository with:

```bash
just setup
```

`just setup` synchronizes the locked Python contributor environment, installs
the frontend lockfile, and runs the local environment check. It does not
install host tools, PostgreSQL, Git LFS media, or representative local media.

If setup or a later toolchain change fails, run:

```bash
just env-check
```

Use repo-local Python tools or `just` recipes rather than assuming a global
`python`, `pip`, or `pytest` targets this project. PostgreSQL and
representative media remain optional. The [development-environment audit](./docs/development-environment-audit.md)
owns version policy, alternative installation paths, and optional-capability
details.

## Developer Harness

[`justfile`](./justfile) is the local command entrypoint. Use the smallest
honest focused lane first, then use `just test-fast` for a broad fast check,
`just ci-local` before an ordinary push, and `just docs-check` for docs or
workflow changes. The full command map, slow lanes, and branch workflow live
in [testing and validation](./docs/testing-and-validation.md) and the
[maintainer docs index](./docs/README.md).

## Repo-Local Codex Skills

Repo-local Codex skills provide optional, project-specific help with planning,
review, validation, and documentation. They do not replace tests or CI. Use
[AGENTS.md](./AGENTS.md) for the shortest safe route and the
[skill inventory](./.agents/skills/INVENTORY.md) for the active skill map,
deferred specialists, and deterministic harness evidence.

## Running The Project

From the repository root, start the normal desktop app:

```bash
npm --prefix frontend run dev
```

Wait for the Electron window, select `video_files`, choose a local `.mp4`, and
select `Start Monitoring`. Repository examples are listed in
[Example Inputs](#example-inputs).

Optional configuration is documented in [`.env.example`](./.env.example). The
application does not load it automatically: source it explicitly or export
only the variables needed for a command.

For backend-only, temporary share-mode, or local MCP workflows, use the
[FastAPI boundary guide](./docs/fastapi-boundary.md) and
[MCP server guide](./docs/mcp-server.md). For browser-only frontend work,
builds, and packaging checks, start with [CONTRIBUTING.md](./CONTRIBUTING.md)
or the [maintainer docs index](./docs/README.md).

## Environment Notes

- tested mainly on Ubuntu `24.04`
- desktop workflow tuned mostly for Linux/X11
- playback and media behavior may differ on Wayland, macOS, or Windows

PostgreSQL is optional and not needed for the default local workflow.

### Version Contract

Use this matrix when choosing or reporting a local environment. **Supported**
is the compatibility claim, **default** is the contributor/AI-agent choice,
and **validated** is the version exercised by CI.

| Component | Supported | Default | Validated |
| --- | --- | --- | --- |
| Python | `>=3.12` | `3.12` | `3.12` in CI |
| Node.js | `22.x` | `22` from [`.nvmrc`](./.nvmrc) | `22` in frontend CI |
| npm | `11.x` | `11.15.0` from `packageManager` | `11.15.0` through the frontend installer |
| FFmpeg / FFprobe | available on `PATH` | host-provided | `6.1.1-3ubuntu5` in weekly Ubuntu media CI |

FFmpeg and FFprobe are host tools, not lockfile-managed dependencies. Their
`6.1.1-3ubuntu5` value is the weekly Ubuntu CI reference, not an exact
cross-platform local requirement. Use `uv sync --locked` for a locked
contributor environment; retain `pip` for editable-install and packaging
compatibility.

## Example Inputs

Start with `video_files`; checked-in media is the most reliable first run:

- `tests/fixtures/media/video_files/clean_baseline_long.mp4`
- `tests/fixtures/media/video_segments/`

Public `api_stream` sources can reject automated fetching; use the
[local API-stream validation guide](./docs/api-stream-local-validation.md) for
repeatable trials.

## Known Limitations

- Some public `.m3u8` streams still block automated fetching.
- Playback and monitoring are related but not identical, so one can fail while
  the other keeps running.
- The desktop workflow is tuned mainly for Ubuntu/Linux, and packaging remains
  developer-oriented.
- The runtime is local-first and single-process; remote MCP remains out of
  scope. See the [MCP policy](./docs/mcp-server.md).

## Tests And Validation

Use focused validation when a changed seam is clear; otherwise `just test-fast`
is the normal broad local confidence check. The
[testing guide](./docs/testing-and-validation.md) owns focused, slow, E2E, and
live-validation commands. The [detector-validation ownership guide](./docs/detector-validation-ownership.md)
owns fixture and truth policy.

## Docs

Start with the [maintainer docs index](./docs/README.md). For API, CLI,
persisted-data, or bridge changes, read [contracts.md](./docs/contracts.md)
before editing code.

## Versioning And Releases

The project is in the early `0.6.4` stage: expect active iteration rather than
long-term compatibility guarantees. Release policy lives in
[release-versioning.md](./docs/release-versioning.md); released changes live in
[CHANGELOG.md](./CHANGELOG.md).

## Data And Outputs

Local detector metrics are written under `data/metrics/`; test fixtures live
in [`tests/fixtures/`](./tests/fixtures). The [session model](./docs/session-model.md)
owns durable session-artifact meaning and storage behavior.

## Repo Layout

Quick map:

- `src/` — Python backend, detectors, sessions, stream loading, and FastAPI
- `frontend/` — React/Electron app, playback, and frontend tests
- `tests/` — automated tests, fixtures, and helpers
- `docs/` — architecture, contracts, and workflow notes
- `data/` — local outputs, metrics, and sample inputs
- `scripts/` — small developer and repo utilities
- `.agents/` — repo-local Codex skills
- `.github/` — CI and repo automation

## CI

CI provides path-aware fast feedback for branch and pull-request work, with
slower media, runtime, PostgreSQL, security, dependency, and packaging
confidence kept in weekly or advisory lanes. See
[CI maintainer guidance](./docs/ci-maintainer-guide.md) for gate semantics,
ownership, and failure artifacts.

## Security Notes

Remote media fetching is intentionally limited:

- source validation accepts direct `.m3u8` and `.mp4` URLs; the current remote
  analysis loader supports HTTP/HLS playlists only
- webpage-style player URLs are rejected early, including YouTube links and
  embedded player pages
- local or private-network targets are blocked by default unless deliberately
  allowed, for example `localhost`, `127.0.0.1`, `192.168.x.x`, or `10.x.x.x`

The detailed security model is intentionally maintained outside the root
README: [FastAPI boundary and deployment gates](./docs/fastapi-boundary.md),
[MCP transport and tool policy](./docs/mcp-server.md), and
[validation ownership](./docs/testing-and-validation.md).

## Contributing And Next Steps

Small, focused contributions are welcome. The project favors explicit detector
and alert-rule registration, clear Electron/FastAPI/MCP boundaries, and
readable code over heavy abstraction. Useful work includes detector and rule
extensions, playback and source-handling fixes, runtime diagnostics, local
security hardening, persistence rollout, and first-run usability. Feedback on
first-run clarity, stream reliability, useful detector coverage, and future
MCP or persistence needs is especially valuable.
