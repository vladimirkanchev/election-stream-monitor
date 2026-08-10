# Election Stream Monitor

![License: MIT](https://img.shields.io/badge/license-MIT-green)

Election Stream Monitor is a local-first AI video-monitoring prototype for
election-related media. It helps surface video-quality problems that can make
real-time observation harder: a black picture, excessive blur, or a broken
source.

It is an advanced, desktop-oriented prototype for local development, demos,
and small monitoring runs, not a public Internet service or a finished
monitoring platform.

**Quick try:** run `npm run dev`, choose `video_files`, and select a local
`.mp4`.

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
- `api_stream` — direct remote `.m3u8` or `.mp4` URLs, not generic web pages

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
   the shared alert backend keep progress, results, and alerts. Session data
   still defaults to the file-backed store, while alerts stay file-backed by
   default with PostgreSQL available as an opt-in backend. Session PostgreSQL
   is also opt-in and currently forward-only rather than a historical
   migration path.

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
- **Local session data and the shared alert backend** persist progress, results, and alerts for the local-first runtime. Session reads and writes now go through the shared session-store contract, but the default backend still writes under `data/sessions/`.
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

The repo now includes a small local command harness in
[`justfile`](./justfile). Use it as the default entrypoint for the most common
developer validation loops.

The harness is intentionally small and repo-shaped: it helps local
development and branch readiness, but it is not a deployment or runtime
orchestration layer.

Design intent:

- focused lanes own one seam each
- broader lanes such as `just test-fast` and `just ci-local` compose those
  focused lanes instead of redefining them
- the harness stays readable and stable by mirroring the current project
  structure rather than hiding it

Workflow ownership stays split on purpose:

- [docs/branch-purpose-template.md](./docs/branch-purpose-template.md)
  - lightweight execution pattern and medium-task checklist
- [docs/testing-and-validation.md](./docs/testing-and-validation.md)
  - local lanes, CI shape, and confidence depth
- [docs/README.md](./docs/README.md)
  - maintainer routing and docs ownership

Current high-value commands:

- `just env-check`
  - environment readiness diagnostic after setup or toolchain changes
- focused lanes first
  - use `just test-detectors`, `just test-processor`, `just test-alert-rules`,
    `just test-hls`, or `just test-frontend` when the changed seam is already clear
- `just test-fast`
  - best default fast runtime validation lane for everyday backend/frontend work
- `just ci-local`
  - best local push-readiness lane after focused checks or `just test-fast`
- `just docs-check`
  - docs/workflow consistency and CI-ownership alignment lane

Use the smallest honest lane first. For the full validation map, slow lanes,
and detector-lab confidence paths, use
[docs/testing-and-validation.md](./docs/testing-and-validation.md).

Harness layers:

- [`justfile`](./justfile)
  - daily local validation commands
- [`pre-commit`](./.pre-commit-config.yaml)
  - cheap commit-time hygiene only
- [`.editorconfig`](./.editorconfig)
  - shared whitespace and indentation defaults

Cheap local guardrails in [`pre-commit`](./.pre-commit-config.yaml):

- Ruff
- trailing whitespace / EOF fixes
- YAML / JSON / TOML validation
- the fixture/environment policy guard

Branch workflow templates:
- [branch-purpose-template.md](./docs/branch-purpose-template.md)
- [`.github/pull_request_template.md`](./.github/pull_request_template.md)
- [merge-readiness-checklist.md](./docs/merge-readiness-checklist.md)

That branch flow keeps three checks explicit:

- what existing test or `docs-check` already proves the change?
- if the change touches API, CLI, persisted data, or bridge shape, should
  [docs/contracts.md](./docs/contracts.md) and nearby tests move with it?
- if `pyproject.toml` or `uv.lock` changed, does that belong to the branch story?

## Repo-Local Codex Skills

The repo includes a focused set of repo-local Codex skills under
[`./.agents/skills/`](./.agents/skills) for repo-aware diagnostics and review.

These are mainly for AI-assisted contributors and debugging workflows. They
are lightweight text helpers, not a separate plugin framework, and they are
not required to run the project.

The most common workflow helpers are:

- `task-planning-evaluation`
  - scales planning depth to the task and reuses the branch template for the
    execution pattern
- `test-strategy-review`
  - chooses the smallest honest validation lane before broader checks
  - says `manual confidence only for now` when no honest automated lane fits yet
- `docs-alignment`
  - routes doc updates to the owning file and flags contract-sensitive changes
- `branch-pr-readiness`
  - checks branch drift, commit grouping, merge readiness, and dependency-file fit

These skills help with local planning, validation, docs alignment, and review,
but they do not replace the project's tests or CI lanes.

Two newer review helpers keep nearby docs work separate on purpose:

- `readme-alignment-review`
  - root README section fit, stage honesty, and trimming
- `docs-drift-check`
  - pre-edit audit of whether docs are really drifting and which file owns the fix
Their deterministic skill tests protect those boundaries so README fit and
docs drift do not collapse into one generic docs mode.

The repo also includes narrower helpers for incident explanation, CI failure
triage, manual validation planning, fixture/environment review, and
security-surface checks.

For the fuller skill map and maintainer-oriented ownership notes, use
[docs/README.md](./docs/README.md).

## Running The Project

From the repository root, start the normal desktop app:

```bash
npm run dev
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

If you are trying the app for the first time, start with `video_files`.
Repo-local examples are the most reliable first run.

Useful repo-local examples:

- `tests/fixtures/media/video_files/`
- `tests/fixtures/media/video_segments/`
- `tests/fixtures/media/video_files/clean_baseline_long.mp4`

Useful `api_stream` examples:

- `https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8`
- `https://devimages-cdn.apple.com/samplecode/avfoundationMedia/AVFoundationQueuePlayer_HLS2/master.m3u8`
- `https://tungsten.aaplimg.com/VOD/bipbop_adv_fmp4_example/master.m3u8`

Some public streams still reject automated fetching. See
[Known Limitations](#known-limitations).

## Known Limitations

- Some public `.m3u8` streams still block automated fetching.
- Playback and monitoring are related but not identical, so one can fail while
  the other keeps running.
- FastAPI and MCP security are designed for local and demo use, not distributed
  public deployment; see the [FastAPI boundary guide](./docs/fastapi-boundary.md)
  and [MCP policy](./docs/mcp-server.md).
- The desktop workflow is tuned mainly for Ubuntu/Linux.
- Packaging is still early and closer to a developer-run app than a polished release.
- Detector coverage is still narrow, with a current focus on black-screen and blur-related issues.
- PostgreSQL alert storage is opt-in and still requires manual local database setup.
- The backend remains local-first and single-process in practice.

## Tests And Validation

Test coverage is in good shape for the current project stage, including the
backend, frontend, FastAPI boundary, and Electron runtime. The repo also has
focused regression coverage across alerts, incident grouping, and key
FastAPI/MCP boundary behavior.

Quick local confidence check:

```bash
just test-fast
```

That fast lane is the best default local confidence pass for everyday backend
and frontend changes. Use
[`docs/testing-and-validation.md`](./docs/testing-and-validation.md) for
focused lanes, slower e2e coverage, snapshot-smoke checks, and live
validation.
Use a focused lane first when the changed area is already clear.

Representative media is opt-in local confidence: catalog guards are
deterministic, while calibration, exact-truth, transport, and soak lanes run
only when the changed seam needs them. The [testing guide](./docs/testing-and-validation.md)
owns commands; the [detector-validation ownership guide](./docs/detector-validation-ownership.md)
owns fixture and truth policy.

For more detail:

- [testing-and-validation.md](./docs/testing-and-validation.md)
- [api-stream-local-validation.md](./docs/api-stream-local-validation.md)

## Docs

For the main owner docs, start with
[docs/README.md](./docs/README.md). The main deep dives are:

If a change affects API, CLI, persisted data, or bridge shape, start with
[docs/contracts.md](./docs/contracts.md).

- [docs/architecture.md](./docs/architecture.md) for the current system shape
- [docs/contracts.md](./docs/contracts.md) for backend and frontend API/data rules
- [docs/session-model.md](./docs/session-model.md) for session lifecycle and local state
- [docs/fastapi-boundary.md](./docs/fastapi-boundary.md) for FastAPI/MCP boundary and access modes
- [docs/frontend-architecture.md](./docs/frontend-architecture.md) for frontend and playback
- [docs/testing-and-validation.md](./docs/testing-and-validation.md) for test scope

## Versioning And Releases

- the project is now in an early `0.6.4` stage
- expect active iteration and improving internal stability rather than strict
  long-term compatibility
- release notes live in [release-versioning.md](./docs/release-versioning.md)
  and [CHANGELOG.md](./CHANGELOG.md)

## Data And Outputs

Useful references:

- [tests/fixtures/](./tests/fixtures)

Outputs are still local-first:

- detector metrics: `data/metrics/`
- per-session metadata, latest progress, and results: `SessionStore` with a file default under `data/sessions/`
- alerts: file-backed by default, with PostgreSQL available as an opt-in backend

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

## Known Roadmap Areas

Likely next areas of work::

- add more detectors and keep alerts easy to tune
- improve runtime debugging and status information
- keep hardening the local Electron + FastAPI app
- strengthen MCP tools security carefully
- decide when PostgreSQL-backed alerts should stay opt-in or or become the default
- implement the session-data PostgreSQL transition

## Feedback Welcome On

The most useful feedback right now is:

- first-run usability and clarity
- runtime stability, especially which public streams work reliably
- which detectors or alerts would be most useful next
- session-data persistence and PostgreSQL migration priorities
- where MCP or AI help would actually be useful

## CI

- `.github/workflows/ci.yml`
- `.github/workflows/weekly-validation.yml`

The main CI workflow is path-aware and runs the fast checks the repo relies on:

- backend tests, packaging smoke, and small backend tooling smoke checks
- backend lint
- frontend checks
- API/data rules, docs, and CI drift checks

It runs on feature-branch pushes and pull requests. Pull requests into `main`
get stricter checks, while the weekly workflow runs the slower deep checks:

- slow end-to-end media tests and deeper `api_stream` / lifecycle checks
- weekly live PostgreSQL alert-confidence checks
- security, dependency, and packaging checks
- failure-only logs, plus persisted session files for the weekly lifecycle lane

CI also keeps frontend and backend test targeting explicit, which makes
refactors and split-suite changes safer.

## Security Notes

Remote media fetching is intentionally limited:

- `api_stream` only accepts direct `.m3u8` and `.mp4` URLs
- webpage-style player URLs are rejected early, including YouTube links and
  embedded player pages
- local or private-network targets are blocked by default unless deliberately
  allowed, for example `localhost`, `127.0.0.1`, `192.168.x.x`, or `10.x.x.x`

The detailed security model is intentionally maintained outside the root
README: [FastAPI boundary and deployment gates](./docs/fastapi-boundary.md),
[MCP transport and tool policy](./docs/mcp-server.md), and
[validation ownership](./docs/testing-and-validation.md).

## Working Style

This repo leans toward:

- explicit detector and alert-rule registration
- clear Electron, FastAPI, and MCP boundaries
- file-backed default persistence with explicit PostgreSQL opt-in backends for
  sessions and alerts
- readable code over heavy abstraction
- promote experiments into production only on purpose

The easiest extension points are:

- add a detector
- add or update a rule
- expose it in the frontend detector catalog
- follow the matching docs and tests

## Contributing

If you want to contribute, that is very welcome.

Useful contributions right now include:

- new detectors and alert rules for real stream problems
- playback, runtime, and source-handling fixes, especially around difficult public streams
- MCP boundary improvements and local security hardening
- session-data persistence and PostgreSQL transition work
- better docs, tests, and first-run usability

Small focused contributions are especially helpful here.
