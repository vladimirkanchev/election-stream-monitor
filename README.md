# Election Stream Monitor

![License: MIT](https://img.shields.io/badge/license-MIT-green)

Election Stream Monitor is a local-first AI video monitoring system for
election-related media sources.

It watches polling-station streams, archived recordings, and segmented video
feeds, then surfaces the quality problems that matter during monitoring.

Today it is an advanced desktop-first prototype with:

- a React/Electron app and local FastAPI backend
- three input modes: local video files, local segmented/HLS-style folders, and direct remote `api_stream` inputs
- two built-in detectors: `Black Screen` and `Blur Check`
- two built-in production alert rules built on top of those detectors
- a small local MCP server with read-only alert-query tools
- selectable alert backend: file by default, PostgreSQL opt-in

It works best today for local development, demos, and small desktop-backed
monitoring runs.

**Quick try:** run `npm run dev`, choose `video_files`, and test with a local
`.mp4`.

The project is intentionally small. The current goal is a readable, useful,
easy-to-extend desktop runtime rather than a heavier platform.

For contributor and maintainer workflows, start with [CONTRIBUTING.md](./CONTRIBUTING.md) and [docs/README.md](./docs/README.md).

## Why this project exists

This project exists to support more transparent election observation in
Bulgaria with a practical local-first workflow.

If a stream goes black, blurry, broken, or becomes too low quality, that is
not only a technical issue. It can make real-time observation harder and
reduce public oversight when it matters most.

Today the project is a desktop-first prototype for exploring that workflow in
practice and extending it with new video detectors as monitoring needs become
clearer.

AI-assisted coding tools can help contributors describe the monitoring problem
in plain language instead of starting from low-level video-processing code.

## Where To Start

Start here if you are:

- trying the project locally
  - start with [Running The Project](./README.md#running-the-project)
- contributing or shaping a maintainer branch
  - start with [CONTRIBUTING.md](./CONTRIBUTING.md)
- learning the current product/runtime shape
  - read [Current Capabilities](./README.md#current-capabilities)
  - then [docs/architecture.md](./docs/architecture.md)
- navigating the whole maintainer docs set
  - use [docs/README.md](./docs/README.md)

## Desktop Runtime Summary

Most people will use the project through the Electron app. The desktop app
talks to a local FastAPI backend that manages sessions, detector execution,
playback-source handling, and alert/session reads.

Today the runtime is local-first:

- session metadata, latest progress, and results read through one shared session-store contract
- the runtime default is still file-backed under `data/sessions/`
- alerts use one shared backend: file-backed by default, PostgreSQL as an explicit opt-in backend
- the UI, alert routes, grouped incident routes, and MCP tools all read alerts
  through that shared backend

FastAPI auth and rate limiting are available for shared access modes. MCP remains a separate local `stdio` tool surface.


## Current Readiness

This works best for:

- local development
- demos
- desktop-backed monitoring use

The repo now also has stronger CI guardrails and more focused regression
coverage across alerts, API/data rules, and workflow targeting.

Still not:

- multi-worker distributed rate limiting
- shared-store production throttling
- remote MCP authentication or limiter coverage
- broad detector coverage for real election-stream failure modes

MCP is still a local `stdio` tool surface over local alert and session data.
FastAPI auth and rate limiting currently protect the alerts HTTP routes in
`share` mode, not the whole local runtime. PostgreSQL-backed alerts now use
the same shared alert backend, but file remains the default.

For local startup, use [Running The Project](./README.md#running-the-project).
For live Postgres validation and weekly confidence runs, use
[docs/testing-and-validation.md](./docs/testing-and-validation.md).

## FastAPI Access Modes

FastAPI currently supports two access modes:

- `local` for normal desktop and development use, with auth and rate limiting
  off by default
- `share` for temporary local or demo sharing, with API-key auth and rate
  limiting on by default

For the exact startup commands and key examples, see
[Running The Project](./README.md#running-the-project).

## Current Capabilities

### Backend

The backend checks inputs, runs sessions, executes detectors and rules, and
writes the local session state the frontend reads.

### Detection

Detectors measure what is happening. Rules decide when that becomes an alert.
Current built-ins:

- `Black Screen`
  - sampled from video files, segment streams, and `api_stream` sources
  - the picture goes fully black or almost black for long enough to matter
- `Blur Check`
  - looks for frames that are too soft or out of focus
  - detail disappears and the image stops looking sharp

Today the production detector and alert surface is intentionally small:

- production black-screen detection and its default alert rule
- production blur detection and its default alert rule

Production detector code lives in [`src/detectors/`](./src/detectors), with
explicit runtime registration in
[`src/detectors/registry.py`](./src/detectors/registry.py).

Blur and motion-blur experiments beyond that live in
[`detector_lab/`](./detector_lab/README.md) until they are promoted on
purpose. For the production promotion rule, use
[`docs/adding-an-analyzer.md`](./docs/adding-an-analyzer.md).

For the detector/rule architecture and the focused validation lanes, use
[`docs/architecture.md`](./docs/architecture.md) and
[`docs/testing-and-validation.md`](./docs/testing-and-validation.md).

### Frontend

In the UI you can:

- choose a source mode, path, and detector set
- use clear `Start Monitoring` and `End Monitoring` controls
- playback for local files, local HLS-style folders, local `.mp4` files, and
  remote HLS streams through the local Electron HLS proxy
- a live alert feed showing issues as they are raised
- simple session status feedback with a `Show debug info` section for more
  backend detail

The screenshot below shows the basic flow: setup on the left, playback in the
center/right, and session state and alerts below.

![Frontend screenshot](./docs/assets/Frontend.png)

### Session Model

This part keeps the session state stable enough for the UI to refresh:

- a session is created when monitoring starts
- progress and results persist through `SessionStore` with a file default
- alerts use one shared alert backend: file by default, PostgreSQL when you opt in
- the frontend polls session snapshots through Electron and the local FastAPI backend
- sessions can complete, fail, or be cancelled cleanly

The feature set is still narrow, but the extension points are explicit.

## Input Modes

- `video_segments` — local `.ts` segment folders, usually around an `index.m3u8` playlist
- `video_files` — local `.mp4` files or folders
- `api_stream` — direct remote `.m3u8` or `.mp4` URLs, not generic web pages

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
   default with PostgreSQL available as an opt-in backend.

FastAPI and MCP are separate entry points over the same local alert and session
data. FastAPI owns the main desktop HTTP path, while MCP remains a local
read-only tool surface over the same saved data.

The diagram below shows the same flow in one picture.

![Architecture outlook](./docs/assets/diagram_final.png)

### Who Owns What

- **Electron** owns the desktop shell, runtime startup, UI bridge, local media serving, and the HLS proxy path.
- **FastAPI** owns the local HTTP boundary: session control, source validation, playback resolution, alert/session reads, and the protected alerts routes in `share` mode.
- **Shared backend services and the detached session worker** own session execution, detector/rule processing, and session-state updates behind that HTTP boundary.
- **MCP** remains a separate local `stdio` read-only alert-reading surface. It reads local alert/session data and stays outside FastAPI auth and rate limiting.
- **Local session data and the shared alert backend** persist progress, results, and alerts for the local-first runtime. Session reads and writes now go through the shared session-store contract, but the default backend still writes under `data/sessions/`.
- **FastAPI and MCP** read through the same persisted alert/session path, not separate stores or monitoring pipelines.

## Installation

Installation is still developer-oriented rather than one-click.

You will need:

- Python `3.12+`
- Node.js and npm
- `ffmpeg` and `ffprobe` on `PATH`
- optionally, `uv` if you prefer that setup flow

Quick setup for the backend and desktop app:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
cd frontend
npm install
```

For repo commands after setup, prefer the repo-local interpreter explicitly:

```bash
./.venv/bin/python -m pytest
./.venv/bin/python your_script.py
```

Do not assume `python3`, `pip`, or `pytest` from `PATH` point at this repo's
virtualenv. This is especially important for AI-assisted tools launched from a
different project shell.

If you use `uv`, the Python part can look like this:

```bash
uv venv
. .venv/bin/activate
uv pip install -e .
```

If you also want the fuller backend test toolchain locally, install the `test`
extra:

```bash
pip install -e .[test]
```

If you want the fuller contributor toolchain, including linting and type-check
tools, install the `dev` extra:

```bash
pip install -e .[dev]
```

Frontend dependencies are installed under [`frontend/`](./frontend).

PostgreSQL is optional and only needed for the opt-in alert backend or live
Postgres validation.

For normal local use, start the Electron app rather than the backend alone.

The normal app startup path is Electron. Direct FastAPI startup is covered
below in [Running The Project](./README.md#running-the-project).

Quick check:

```bash
python --version
node -v
ffmpeg -version | head -n 1
```

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
  - lightweight local tool and version sanity check
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

The repo includes a small set of repo-local Codex skills under
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

Three newer review helpers keep nearby docs work separate on purpose:

- `readme-alignment-review`
  - root README section fit, stage honesty, and trimming
- `docs-drift-check`
  - pre-edit audit of whether docs are really drifting and which file owns the fix
- `architecture-diagram-review`
  - diagram flow clarity, boundaries, visual quality, and stage honesty

Their deterministic skill tests also protect those boundaries so README fit,
docs drift, and diagram review do not collapse into one generic docs mode.

The repo also includes narrower helpers for incident explanation, CI failure
triage, manual validation planning, fixture/environment review, and
security-surface checks.

For the fuller skill map and maintainer-oriented ownership notes, use
[docs/README.md](./docs/README.md).

## Running The Project

1. Start the normal desktop app:

```bash
npm run dev
```

2. For a quick first run:

Run `npm run dev` from the repo root, wait for the Electron window to open,
pick an input mode and choose a source, then hit `Start Monitoring`.

Sample local inputs are listed in [Example Inputs](./README.md#example-inputs).

3. Use these optional entry points when you need a narrower workflow:

Backend only:

```bash
. .venv/bin/activate
PYTHONPATH=src python -m api_server_cli local
```

`local` mode is the normal desktop and development path. Auth and rate
limiting are off by default, and these examples use the default file-backed
alert backend.

Browser-only frontend for UI work:

```bash
npm --prefix frontend run dev:web
```

This does not replace the normal Electron desktop flow.

Temporary shared demo access:

```bash
. .venv/bin/activate
PYTHONPATH=src python -m api_server_cli share
```

`share` mode turns on API-key auth and rate limiting. If you do not pass a
manual key, the CLI generates one and prints it once. `share` mode is for
temporary local or demo sharing, not production deployment.

Explicit shared-demo key:

```bash
. .venv/bin/activate
PYTHONPATH=src python -m api_server_cli share --api-key my-demo-key
```

Use any long random string for `my-demo-key`.

If you want Electron to use a separately started `share` backend:

```bash
ELECTION_API_BASE_URL=http://127.0.0.1:8002 npm run dev
```

Stronger key generator:

```bash
python -c "import secrets; print('esm_demo_' + secrets.token_urlsafe(24))"
```

Then pass that value with `--api-key`.

Local MCP server:

```bash
. .venv/bin/activate
PYTHONPATH=src python -m esm_mcp
```

This runs the MCP server over local `stdio`. See
[docs/mcp-server.md](./docs/mcp-server.md).

Frontend build:

```bash
npm run build
```

If Electron startup behaves differently on your machine, start here:

- [frontend/package.json](./frontend/package.json)
- [frontend/electron/main.mjs](./frontend/electron/main.mjs)
- [frontend/electron/fastApiStartupOrchestrator.mjs](./frontend/electron/fastApiStartupOrchestrator.mjs)
- [docs/frontend-architecture.md](./docs/frontend-architecture.md)

## Environment Notes

- tested mainly on Ubuntu `24.04`
- desktop workflow tuned mostly for Linux/X11
- playback and media behavior may differ on Wayland, macOS, or Windows

PostgreSQL is optional and not needed for the default local workflow.

Tested with:

- React `19.1.0`
- Node.js `20.20.0`
- npm `10.8.2`
- `ffmpeg` `6.1.1`
- `ffprobe` `6.1.1`

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
- FastAPI auth and rate limiting are for local and demo use, not distributed
  deployment.
- MCP is still a local `stdio` read-only query surface over local alert/session
  data, outside that FastAPI protection.
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

Representative-media validation is now split on purpose: reviewed HLS intent,
exact reviewed HLS and MP4 truth, transport-backed `api_stream` confidence,
calibration-only detector-lab checks, and a separate MP4 confidence layer for
capped reviewed-window checks plus full-file soak coverage. The deep owner for
that split is [`docs/testing-and-validation.md`](./docs/testing-and-validation.md).
Low-resolution representative cases now follow that same split: black-negative
runtime guards and broad MP4/HLS parity can be enforced before blur behavior is
promoted into exact truth.
Use the capped representative MP4 lane in ordinary slow local validation when
the branch reaches longer `video_files` behavior and needs output-shape,
positive, or false-positive confidence on reviewed windows. Use `pytest -m
soak` only for the full-file representative MP4 confidence run, and keep that
lane in scheduled or manual-depth validation rather than ordinary PR work.

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

- the project is now in an early `0.5.1` stage
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

The current backend security scope is still intentionally narrow:

- FastAPI `share` mode adds API-key auth and rate limiting on the alert routes
- FastAPI `local` mode keeps auth and rate limiting off
- MCP remains a local `stdio` read-only tool surface over local alert/session
  data, outside FastAPI auth and rate limiting
- PostgreSQL-backed alerts do not change that boundary by themselves; they only
  change where alert data is stored
- session outputs stay on local disk for review and debugging

Owning files:

- [src/source_validation.py](./src/source_validation.py) for remote input and trust rules
- [src/api_boundary_config.py](./src/api_boundary_config.py) for `local` / `share` defaults and boundary settings
- [src/api/alert_route_policy.py](./src/api/alert_route_policy.py) for FastAPI auth and rate-limiting on alerts routes
- [src/esm_mcp/](./src/esm_mcp/) for the local MCP server and tools

## Working Style

This repo leans toward:

- explicit detector and alert-rule registration
- clear Electron, FastAPI, and MCP boundaries
- file-backed session state with a selectable alert backend
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
