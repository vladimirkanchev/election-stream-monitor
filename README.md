# Election Stream Monitor

![License: MIT](https://img.shields.io/badge/license-MIT-green)

Election Stream Monitor is a local-first AI video monitoring system for
election-related media sources.

It watches polling-station streams, archived recordings, or segmented video
feeds and surfaces the quality problems that matter during monitoring.

Today it runs as a desktop-first Electron app with a local FastAPI backend.
It also includes a small local MCP server with read-only alert tools.

Status:

- desktop-first advanced prototype/pre-pilot
- local-first workflow
- three input modes
- two built-in detectors

Works today:

- local `.mp4` files and local `.ts` segment folders with `index.m3u8`
- direct remote `.m3u8` / `.mp4` `api_stream` inputs
- built-in `Black Screen` and `Blur Check` monitoring
- Electron desktop UI with a local FastAPI-backed backend
- FastAPI API-key auth and rate limiting for shared demo access
- local MCP server with 4 alert-query tools

**Quick try:** run `npm run dev`, choose `video_files`, and test with a local `.mp4`.

**Best fit today:** local development, demos, and small desktop-backed
monitoring runs.

The project is intentionally small. I want it to stay readable, useful, and
easy to extend without turning into a much heavier platform too early.

## Why this project exists

This project exists to support more transparent election observation in
Bulgaria with a practical local-first workflow.

If a stream goes black, blurry, broken, or just becomes too low quality, that
is not only a technical issue. It can stop people from following elections in
real time and make public oversight harder when it matters most.

It also gives me a place to build video analysis and streaming tools around a
real civic use case instead of a purely abstract demo.

## Where To Start

A good place to start:

- this README for the big picture
- [Running The Project](./README.md#running-the-project) to try it locally
- [docs/architecture.md](./docs/architecture.md) for the current system shape
- [docs/contracts.md](./docs/contracts.md) for important backend and frontend contracts
- [docs/session-model.md](./docs/session-model.md) for session lifecycle and persisted state
- [docs/fastapi-boundary.md](./docs/fastapi-boundary.md) for FastAPI/MCP boundary and access modes
- [docs/frontend-architecture.md](./docs/frontend-architecture.md) for frontend and playback details
- [docs/README.md](./docs/README.md) for the full docs map

## Desktop Runtime Summary

Most people will use the project through the Electron app. Electron starts
and talks to a local FastAPI backend for session control, detector loading,
and playback-source resolution.

Electron still owns the desktop-only work: app startup, local media serving,
the HLS proxy path, and the UI bridge. Session snapshots stay on disk and are
polled by the UI while a run is active.

Today the alert backend works like this:

- file-backed alerts remain the default
- PostgreSQL alert storage is available as an opt-in backend
- the main session snapshot, the dedicated alert routes, and the MCP tools now
  all read alerts through the same backend seam

There is also a small local MCP server for read-only alert queries over that
same local data.

## Current Readiness

This works best for:

- local development
- demos
- desktop-backed monitoring use

The repo now also has stronger CI guardrails and more focused regression
coverage across alerts, contracts, and workflow targeting.

Still not:

- multi-worker distributed rate limiting
- shared-store production throttling
- remote MCP authentication or limiter coverage

MCP is still a local `stdio` query surface over local alert and session data.
FastAPI auth and rate limiting currently apply only to the alerts routes.
Current work is centered on detector growth, MCP tooling, runtime hardening,
and PostgreSQL-backed alert persistence for alerts. That backend is now
implemented behind the alert store seam, but file remains the default. Use
`ESM_ALERT_STORE_BACKEND=postgres` to opt into PostgreSQL explicitly.

## FastAPI Access Modes

### Local mode

For normal local development and desktop use:

```bash
. .venv/bin/activate
PYTHONPATH=src python -m api_server_cli local
```

By default, auth and rate limiting are off.

### Share mode

For temporary demo or shared access:

```bash
. .venv/bin/activate
PYTHONPATH=src python -m api_server_cli share
```

By default, auth and rate limiting are on. If you do not pass `--api-key`,
the CLI generates one and prints it once with `X-API-Key` guidance.

Optional manual key:

```bash
. .venv/bin/activate
PYTHONPATH=src python -m api_server_cli share --api-key my-demo-key
```

You can also generate your own stronger key first; see
[Running The Project](./README.md#running-the-project).

`share` mode is for temporary demo/shared access only. MCP remains local
`stdio` and stays outside FastAPI auth and rate limiting.

The current protected FastAPI scope is the alerts surface:
`/sessions/{session_id}/alerts`, `/alerts/summary`, `/alerts/timeline`, and
`/alerts/incident-summary`.

## Current Capabilities

### Backend

The backend validates input, runs sessions, executes detectors and rules, and
writes local session state that the frontend can read.

### Detection

Detectors measure what is happening. Rules decide when that becomes an alert.
Current built-ins:

- `Black Screen`
  - mainly from frames sampled from video files, segment streams, and
    `api_stream` sources
  - the picture goes fully black or almost black for long enough to matter
- `Blur Check`
  - looks for frames that are too soft, smeared, or out of focus
  - details disappear and the image stops looking sharp

### Frontend

In the UI you can:

- a setup panel for source mode, path, and detector selection
- clear `Start Monitoring` and `End Monitoring` controls
- playback for local files, local HLS-style folders, local `.mp4` files, and
  remote HLS streams through the local Electron HLS proxy
- a live alert feed showing issues as they are raised
- simple session status feedback with a `Show debug info` section for more
  backend detail

The screenshot below shows the basic flow: setup on the left, playback in the
center/right, and session state and alerts below.

![Frontend screenshot](./docs/assets/Frontend.png)

### Session Model

This part writes the session files, updates progress, stores alerts and
results, and gives the UI something stable to poll:

- a session is created when monitoring starts
- progress and results are written to local JSON / JSONL files
- alert reads and writes now share one explicit backend seam
- file-backed alerts remain the default, with PostgreSQL available as an opt-in backend
- the session snapshot still keeps metadata, progress, and results file-backed
- the snapshot `alerts` field now follows the active alert backend too
- the frontend polls those snapshots through Electron and the local FastAPI backend
- sessions can complete, fail, or be cancelled cleanly

The current feature set is still narrow, but easy to extend.

## Input Modes

- `video_segments` — local `.ts` segment folders, usually around an `index.m3u8` playlist
- `video_files` — local `.mp4` files or folders
- `api_stream` — direct remote `.m3u8` or `.mp4` URLs, not generic web pages

## Architecture At A Glance

This is still one local-first project, not a distributed platform, but the
main boundaries are there on purpose.

In practice, the flow looks like this:

1. You choose a source, pick detectors, and start monitoring from the UI.
2. The frontend and Electron handle the visible workflow: setup, playback,
   status, alerts, and desktop-only jobs like local media serving and the HLS
   proxy path.
3. FastAPI starts and manages sessions, validates sources, resolves playback
   inputs, and hands the monitoring work to the backend services and worker
   process.
4. Detectors and alert rules process the media, while local session snapshots
   and the shared alert store keep progress, results, and alerts that the UI
   can poll in near real time and MCP tools can query separately.

FastAPI and MCP are separate adapters over the same local alert/session data.
FastAPI owns the main desktop-backed HTTP/runtime path, while MCP stays a
local read-only query surface over that persisted data.

The diagram below shows the same flow in one picture.

![Architecture outlook](./docs/assets/diagram_final.png)

### Who Owns What

- **Electron** owns the desktop shell, runtime startup, UI bridge, local media serving, and the HLS proxy path.
- **FastAPI** owns the monitoring backend: session control, source validation, stream resolution, detector/rule execution, and session-state updates. In `share` mode, it also applies API-key auth and rate limiting to the alerts routes.
- **MCP** remains a separate local `stdio` read-only alert-query surface. It queries local alert/session data and stays outside FastAPI auth and rate limiting.
- **Local alert and session data** persist progress, results, and alerts for the local-first runtime. The UI polls that data through the Electron/FastAPI flow, and MCP tools query it separately.
- **Shared read/query seam** stays backend-owned: FastAPI and MCP are adapters over the same persisted alert/session data rather than separate stores or independent monitoring pipelines.

## Installation

Installation is still developer-oriented rather than one-click.

You will need:

- Python `3.12+`
- Node.js and npm
- `ffmpeg` and `ffprobe` on `PATH`
- optionally `uv` if you prefer that setup flow

Quick setup for the backend runtime plus the desktop app:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
cd frontend
npm install
```

If you use `uv`, the Python part can look like this:

```bash
uv venv
. .venv/bin/activate
uv pip install -e .
```

If you also want backend test tooling locally, install the `test` extra:

```bash
pip install -e .[test]
```

If you want the fuller contributor toolchain, including linting and type-check
tools, install the `dev` extra:

```bash
pip install -e .[dev]
```

Install extras:

- `pip install -e .` for backend runtime dependencies
- `pip install -e .[test]` for backend runtime plus test tooling
- `pip install -e .[dev]` for backend runtime plus test, Ruff, and type-check tools

The normal app startup path is Electron. Direct FastAPI startup is covered
below in [Running The Project](./README.md#running-the-project).

Quick check:

```bash
python --version
node -v
ffmpeg -version | head -n 1
```

## Repo-Local Codex Skills

The repo includes a small set of repo-local Codex skills under
[`./.agents/skills/`](./.agents/skills) for repo-aware diagnostics and review:

- `summarization`
- `incident-timeline`
- `test-coverage-gaps`
- `root-cause-suggestion`

Use these skills when you want quick repo-aware help with summaries, incident
timelines, root-cause suggestions, or test-coverage gaps.

These are lightweight text helpers, not a separate plugin framework.

## Running The Project

Normal desktop app:

```bash
npm run dev
```

This starts the Vite frontend, Electron, and the local FastAPI backend.

Backend only:

```bash
. .venv/bin/activate
PYTHONPATH=src python -m api_server_cli local
```

If you want the browser-only frontend in this split setup, run:

```bash
npm --prefix frontend run dev:web
```

Use that browser path for UI work and frontend debugging. It does not replace
the normal Electron desktop flow.

Temporary shared demo access:

```bash
. .venv/bin/activate
PYTHONPATH=src python -m api_server_cli share
```

`share` mode turns on API-key auth and rate limiting. If you do not pass a
manual key, the CLI generates one and prints it once. Send that key in the
`X-API-Key` header when calling the protected alerts routes. See
[FastAPI Access Modes](./README.md#fastapi-access-modes).

If you want Electron to use a separately started `share` backend:

```bash
ELECTION_API_BASE_URL=http://127.0.0.1:8002 npm run dev
```

If you want to generate your own stronger key first:

```bash
python -c "import secrets; print('esm_demo_' + secrets.token_urlsafe(24))"
```

Then pass that value with `--api-key`.

Local MCP server:

```bash
. .venv/bin/activate
PYTHONPATH=src python -m esm_mcp
```

This runs the MCP server over local `stdio`, so connect to it with an MCP
client rather than a browser or HTTP port. See [docs/mcp-server.md](./docs/mcp-server.md).

Quick first run:

1. Run `npm run dev` from the repo root.
2. Wait for the Electron window to open.
3. Pick an input mode and choose a source.
4. Hit `Start Monitoring`.

Sample local inputs are listed in [Example Inputs](./README.md#example-inputs).

Frontend only:

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

Tested with:

- React `19.1.0`
- Node.js `20.20.0`
- npm `10.8.2`
- `ffmpeg` `6.1.1`
- `ffprobe` `6.1.1`

## Example Inputs

If you are trying the app for the first time, start with `video_files`.

Useful local examples:

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
- The desktop workflow is tuned mainly for Ubuntu/Linux, so other platforms
  may need extra work.
- Packaging is still early, so this is closer to a developer-run app than a
  polished desktop release.
- Detector coverage is still narrow, with a current focus on black-screen and
  blur-related issues.
- The backend is still local-first and single-process in practice.

## Tests And Validation

The test coverage is in good shape for where the project is right now,
including the backend, frontend, FastAPI boundary, and Electron runtime.
The repo also now has stronger focused regression coverage across alerts,
incident grouping, FastAPI/MCP boundaries and CI ownership checks.

Quick local confidence check:

```bash
. .venv/bin/activate
pip install -e .[test]
pytest -q -m "not e2e and not slow"
npm --prefix frontend run test
npm run build
```

That default backend pass keeps the normal fast lane focused on unit and
service-level coverage. Run the dedicated e2e commands from
[`docs/testing-and-validation.md`](./docs/testing-and-validation.md) when you
want the snapshot smoke or slower real-media checks.

For more detail:

- [testing-and-validation.md](./docs/testing-and-validation.md)
- [api-stream-local-validation.md](./docs/api-stream-local-validation.md)

## Docs

For the full docs map, start with [docs/README.md](./docs/README.md). The main
references are:

- [docs/architecture.md](./docs/architecture.md) for the current system shape
- [docs/contracts.md](./docs/contracts.md) for backend and frontend boundaries
- [docs/session-model.md](./docs/session-model.md) for session lifecycle and local state
- [docs/fastapi-boundary.md](./docs/fastapi-boundary.md) for FastAPI/MCP boundary and access modes
- [docs/frontend-architecture.md](./docs/frontend-architecture.md) for frontend and playback
- [docs/testing-and-validation.md](./docs/testing-and-validation.md) for test scope

## Versioning And Releases

- the project is now in an early `0.3.1` stage
- expect active iteration, with improving internal stability rather than strict
  long-term compatibility
- release notes live in [release-versioning.md](./docs/release-versioning.md)
  and [CHANGELOG.md](./CHANGELOG.md)

## Data And Outputs

Useful references:

- [tests/fixtures/](./tests/fixtures)

Outputs are stored locally in files, not a database:

- detector metrics: `data/metrics/`
- per-session progress, results, and alerts: `data/sessions/`

## Repo Layout

Quick map:

- `src/` — Python backend, detectors, sessions, stream loading, FastAPI
- `frontend/` — React/Electron app, playback, frontend tests
- `tests/` — automated tests, fixtures, helpers
- `docs/` — architecture, contracts, workflow notes
- `data/` — local metrics, session data, sample inputs
- `scripts/` — small developer and repo utilities
- `.agents/` — repo-local Codex skills
- `.github/` — CI and repo automation

## Known Roadmap Areas

What I would work on next:

- add more detectors and keep alerts easy to tune
- improve debugging and status information
- keep improving the local Electron + FastAPI app
- add more MCP tools and strengthen security carefully
- make packaging and releases easier over time
- keep the project desktop-first without rushing into service complexity

## Feedback Welcome On

The most useful feedback right now is:

- first-run usability and clarity
- runtime stability, especially which public streams work reliably
- which detectors or alerts would be most useful next
- where MCP or AI help would actually be useful

## CI

- `.github/workflows/ci.yml`
- `.github/workflows/weekly-validation.yml`

The main CI workflow is path-aware and runs the fast checks the repo relies on:

- backend tests and packaging smoke
- backend lint
- frontend checks
- contract and docs consistency checks
- CI ownership and drift guards for target manifests, owned test paths, and
  split-suite registration

It runs on feature-branch pushes and pull requests. Pull requests into `main`
get stricter checks.

The weekly validation workflow runs slower, deeper checks:

- slow end-to-end media tests
- deeper `api_stream` and lifecycle checks
- security audits
- dependency and packaging checks

The CI model now also keeps frontend and backend test targeting more explicit, which makes refactors and split-suite changes safer.

## Security Notes

Remote media fetching is intentionally limited:

- `api_stream` only accepts direct `.m3u8` and `.mp4` URLs
- webpage-style player URLs are rejected early, including YouTube links and
  embedded player pages
- local or private-network targets are blocked by default unless deliberately
  allowed, for example `localhost`, `127.0.0.1`, `192.168.x.x`, or `10.x.x.x`

The current backend security story is still pretty narrow:

- FastAPI `share` mode adds API-key auth and rate limiting on the alerts routes
- FastAPI `local` mode keeps auth and rate limiting off
- MCP remains a local `stdio` read-only query surface over local alert/session
  data, outside FastAPI auth and rate limiting
- session outputs stay on local disk for review and debugging

Owning files:

- [src/source_validation.py](./src/source_validation.py) for remote input and trust rules
- [src/api_boundary_config.py](./src/api_boundary_config.py) for `local` / `share` defaults and boundary settings
- [src/api/alert_route_policy.py](./src/api/alert_route_policy.py) for FastAPI auth and rate-limiting on alerts routes
- [src/esm_mcp/](./src/esm_mcp/) for the local MCP server and tools

## Easy To Work On

This repo leans toward:

- explicit detector and alert-rule registration
- clear Electron, FastAPI, and MCP boundaries
- simple local session and output files
- readable code over heavy abstraction

The easiest extension points are:

- add a detector
- add or update a rule
- expose it in the frontend detector catalog
- follow the matching docs and tests

## Contributing

If you want to contribute, that is very welcome.

Useful contributions right now include:

- new detectors and alert rules for real stream problems
- playback and runtime fixes, especially around difficult public streams
- FastAPI and MCP tool improvements
- better docs, tests, and first-run usability

Small focused contributions are especially helpful here.
