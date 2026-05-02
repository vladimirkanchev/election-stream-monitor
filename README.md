# Election Stream Monitor

![License: MIT](https://img.shields.io/badge/license-MIT-green)

Election Stream Monitor is a local-first AI video monitoring system for
election-related media sources.

It watches polling-station streams, archived recordings, or segmented video
feeds and surfaces the quality problems that matter during monitoring.

This repo is a desktop-first prototype with an owned FastAPI-backed desktop
runtime, not a finished platform.

Status:

- desktop-first prototype
- local-first workflow
- three input modes
- two built-in detectors

Works today:

- local `.mp4` video files
- local `.ts` segment folders with `index.m3u8`
- direct remote `.m3u8` / `.mp4` `api_stream` inputs
- built-in `Black Screen` and `Blur Check` monitoring
- Electron desktop UI with a local FastAPI-backed backend

The project is still intentionally small. The goal is to keep it readable,
easy to extend, and useful for real monitoring work without adding platform
weight too early.

## Why this project exists

This project exists to support more transparent election observation in
Bulgaria with a practical local-first workflow.

If a stream goes black, blurry, broken, or just becomes too low quality, that
is not only a technical issue. It can stop people from following elections in
real time and make public oversight harder when it matters most.

It also gives me a place to build the AI, video analysis, and streaming
pieces behind something with clear civic value.

## Where To Start

You do not need to read this repo front to back.

Start here:

- this README for the big picture
- want the current system shape: [docs/architecture.md](./docs/architecture.md)
- want the important contracts: [docs/contracts.md](./docs/contracts.md)
- want the session model: [docs/session-model.md](./docs/session-model.md)
- working on frontend or playback: [docs/frontend-architecture.md](./docs/frontend-architecture.md)
- want the full docs map: [docs/README.md](./docs/README.md)

## Desktop Runtime Summary

The Electron app uses the local FastAPI backend as the normal runtime
path. The app window, session controls, detector loading, and playback-source
resolution all go through that desktop flow.

Electron still handles the desktop-only jobs: app startup, local media
serving, the HLS proxy path, and the UI bridge. Session state stays local and
is polled by the UI while a run is active. Packaging and broader platform
support remain separate concerns.

## Current Capabilities

### Backend

The backend validates input, starts the session, steps through the media, runs
detectors, applies rules, and keeps writing local session state that the
frontend can read.

### Detection

Detectors measure what is happening. Rules decide when that should turn into
an alert.

Right now it can catch:

- `Black Screen`
  - mainly from frames sampled from video files, segment streams, and
    `api_stream` sources
  - the picture goes fully black or almost black for long enough to matter
- `Blur Check`
  - looks for frames that are too soft, smeared, or out of focus
  - details disappear and the image stops looking sharp

### Frontend

The frontend gives you:

- a setup panel for source mode, path, and detector selection
- clear `Start Monitoring` and `End Monitoring` button controls
- playback for local files, local HLS-style folders, local `.mp4` files, and
  remote HLS streams through the local Electron HLS proxy
- a live alert feed showing detected issues as they are raised
- simple session status feedback with operator-friendly diagnostics and a
  `Show debug info` section for more detailed backend session state

The screenshot below shows the basic flow in the UI form: setup on the left, playback in the
center/right, and session state and alerts below.

![Frontend screenshot](./docs/assets/Frontend.png)

### Session Model

This layer writes the session files, updates progress, stores alerts and
results, and gives the UI something stable to poll.

Right now it works in a simple local-first way:

- a session is created when monitoring starts
- progress, alerts, and results are written to local JSON / JSONL files
- the frontend polls those snapshots through Electron and the local FastAPI backend
- sessions can complete, fail, or be cancelled cleanly

The current feature set is narrow, but it is easy to extend.

## Input Modes

The project currently supports these input modes:

- `video_segments`
  - local folders of `.ts` video chunks, usually organized around an
    `index.m3u8` playlist
- `video_files`
  - local `.mp4` files or folders containing `.mp4` files
- `api_stream`
  - direct remote `.m3u8` or `.mp4` URLs
  - webpage URLs such as YouTube links or generic HTML player pages are not
    supported

## Architecture At A Glance

This is still one local-first project, not a distributed platform, but the
internal boundaries are deliberate. The goal is to keep the flow simple to use
while keeping the code structured enough to extend.

In practice, the flow looks like this:

1. You pick a source, choose the detectors you want, and hit `Start Monitoring`.
2. The frontend handles the visible workflow: setup, playback, live status,
   and the basic session controls.
3. Electron acts as the local bridge between the UI and the FastAPI-backed
   Python runtime. It also handles desktop-only playback jobs like local media
   serving and the HLS proxy path used for some remote streams.
4. The backend session runner and stream loader do the monitoring work in the
   background: they open files or stream chunks, move through them step by
   step, and keep the session running.
5. The detector list keeps selection explicit, so only detectors that fit the
   current mode are used.
6. Detectors produce structured results, and the alert rules turn the
   important ones into warnings that are easier to notice.
7. Session state is persisted locally, and the frontend polls snapshots through
   Electron and the local FastAPI backend so you can see progress, status, and
   alerts in near real time.

If you want the visual version, the diagram below shows the same runtime flow.

![Architecture outlook](./docs/assets/diagram_final.png)

### Who Owns What

Today:

- **Electron** owns the desktop shell, runtime startup, UI bridge, local media serving, and the HLS proxy path.
- **FastAPI** owns the monitoring backend: session control, source validation, stream resolution, detector/rule execution, and session-state updates.
- **Local session files** persist progress, results, and alerts for the local-first runtime, which the UI reads through the Electron/FastAPI flow.

In short: **Electron** handles the desktop runtime and playback bridge, while
FastAPI handles the monitoring backend.

## Installation

For now, installation is still developer-oriented rather than one-click.
The Python package is installable for local backend/runtime work, but this repo
is still not presented as a polished published desktop or backend distribution.

You will need:

- Python `3.12+`
- Node.js and npm
- `ffmpeg` and `ffprobe` on `PATH`
- optionally `uv` if you prefer that Python setup flow

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

The current split is deliberate:

- `pip install -e .`
  - backend runtime dependencies only
- `pip install -e .[test]`
  - backend runtime plus backend test tooling
- `pip install -e .[dev]`
  - backend runtime plus test, Ruff lint, and type-check tooling

That installability is mainly for:

- local backend development
- FastAPI/session debugging
- CI and future container-friendly backend setup

The normal desktop startup path is still Electron, not a standalone Python app
entrypoint.

Current backend import/run expectations:

- use `npm run dev` for the normal desktop application path
- use `pip install -e .` or `pip install -e .[test]` when you want the backend
  import surface available through an editable install
- use `PYTHONPATH=src` for backend-only import/debug work from a raw checkout
  when you are intentionally not relying on an editable install
- use `uvicorn api.app:app --app-dir src --reload` for backend HTTP startup
  from the current flat `src/` layout

Quick check:

```bash
python --version
node -v
ffmpeg -version | head -n 1
```

CI note:

- feature branches get a quick frontend checkpoint, the full test/build job,
  and a single feature-branch merge gate
- pull requests into `main` also run a small integration smoke test and a
  lightweight workflow/docs/contract consistency check

Environment notes:

- the project is currently tested mainly on Ubuntu `24.04`
- the desktop workflow is currently tuned for Linux/X11 development
- Electron playback and media behavior may differ on Wayland, macOS, or
  Windows until those paths are tested more broadly

Tested with:

- React `19.1.0`
- Node.js `20.20.0`
- npm `10.8.2`
- `ffmpeg` `6.1.1`
- `ffprobe` `6.1.1`

## Running The Project

From the repository root, start the app with:

```bash
npm run dev
```

This starts:

- the Vite frontend
- the Electron shell
- the local FastAPI-backed Python runtime used by the app

This is still the normal way to run the project as an application.

If you only want the backend for development or debugging, you can start
FastAPI directly instead:

```bash
. .venv/bin/activate
uvicorn api.app:app --app-dir src --reload
```

That backend-only path is mainly for API-focused development, contract
inspection, and troubleshooting. It is not the primary desktop-app startup
experience.

If you are debugging backend imports directly from a raw checkout rather than
through an editable install, use `PYTHONPATH=src` so the current flat `src/`
module layout is on `sys.path`.

The CLI remains available for session tooling and debugging, but it is not a
normal application startup path. It is an adapter over the same shared backend
session logic used by FastAPI.

The easiest first run is `video_files` mode with a local `.mp4`.

For a quick first run:

1. Run `npm run dev` from the repo root.
2. Wait for the Electron window to open.
3. Pick one of the supported input modes.
4. Choose a local file, local segment folder, or a direct stream URL.
5. Hit `Start Monitoring` and watch the playback panel, session status, and
   alert feed update.

Useful local paths:

- `tests/fixtures/media/video_segments/`
- `tests/fixtures/media/video_files/`

If you only want to build the frontend:

```bash
npm run build
```

If Electron startup behaves differently on your machine, start by checking:

- [frontend/package.json](./frontend/package.json)
- [frontend/electron/main.mjs](./frontend/electron/main.mjs)
- [frontend/electron/fastApiStartupOrchestrator.mjs](./frontend/electron/fastApiStartupOrchestrator.mjs)
- [docs/frontend-architecture.md](./docs/frontend-architecture.md)

## Example Inputs

If you are trying the app for the first time, start with `video_files`.

For local examples, start with these fixture paths:

- `tests/fixtures/media/video_files/`
- `tests/fixtures/media/video_segments/`

One simple local example is:

- `tests/fixtures/media/video_files/clean_baseline_long.mp4`

If you want to try `api_stream`, these public HLS examples are a good place to
start:

- `https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8`
- `https://devimages-cdn.apple.com/samplecode/avfoundationMedia/AVFoundationQueuePlayer_HLS2/master.m3u8`
- `https://tungsten.aaplimg.com/VOD/bipbop_adv_fmp4_example/master.m3u8`

Some public streams may play in a browser but still reject automated fetching.
For provider quirks and blocked streams, see [Known Limitations](#known-limitations).

## Known Limitations

- Remote inputs are still limited. Some public `.m3u8` streams block
  automated fetching.
- Playback and monitoring are connected, but they are not the same thing, so
  one can fail while the other keeps going.
- The desktop workflow is still tuned mainly for local Ubuntu/Linux
  development, so other platforms may need extra work.
- Packaging and installation are still early, so this is closer to a
  developer-run app than a polished desktop release.
- Detector coverage is still intentionally narrow. Right now the built-in focus
  is on black-screen and blur-related issues.
- This is still an advanced prototype, so the larger pilot and production
  hardening work is not finished yet.

## Tests And Validation

The test surface is strong for this stage. The
main coverage is around backend lifecycle behavior, `api_stream` loading,
FastAPI/API boundaries, frontend bridge normalization, and Electron runtime
seams.

If you want a quick local confidence check, start with:

```bash
. .venv/bin/activate
pip install -e .[test]
pytest -q
npm --prefix frontend run test
npm run build
```

What is already covered well:

- backend unit and integration tests
- targeted `api_stream` and HLS loader coverage
- FastAPI boundary and contract checks
- frontend bridge, hook, and UI error coverage
- Electron startup, bridge, and local-media runtime coverage
- opt-in public-stream smoke tests and local validation workflows

If you want the deeper testing notes, start here:

- [testing-and-validation.md](./docs/testing-and-validation.md)
- [api-stream-local-validation.md](./docs/api-stream-local-validation.md)

## Docs

For the full docs map, start with [docs/README.md](./docs/README.md). The main
project references are:

- [docs/architecture.md](./docs/architecture.md) for the current system shape
- [docs/contracts.md](./docs/contracts.md) for the important boundaries
- [docs/session-model.md](./docs/session-model.md) for lifecycle and local session state
- [docs/frontend-architecture.md](./docs/frontend-architecture.md) for the Electron/React side
- [docs/testing-and-validation.md](./docs/testing-and-validation.md) for checks, commands, and test scope

## Versioning And Releases

- the project is still in an early `0.2.0` stage
- expect active iteration rather than strict stability
- features, docs, and internal structure should keep getting better as the project moves from structured prototype toward MVP
- release and versioning notes live in
  [release-versioning.md](./docs/release-versioning.md) and
  [CHANGELOG.md](./CHANGELOG.md)
- usable for local runs, but not yet a polished stable release

## Data And Outputs

Important repo-safe references:

- [data/README.md](./data/README.md)
- [tests/fixtures/](./tests/fixtures)

After a run, the project gives you stored metrics, session progress, results,
and alerts that can be reviewed locally.

For now, persistence is file-based rather than database-backed.

- detector result metrics are stored in CSV format in `data/metrics/`
- per-session results, progress, and alerts are stored as local session data in
  `data/sessions/`

This makes it easy to inspect runs locally without setting up a database or
service stack. The current output model is meant for local review, debugging,
and prototype workflows.

## Repo Layout

If you are browsing the repo for the first time, this is the basic layout:

- `src/`
  - Python backend code for detectors, sessions, live stream loading, FastAPI
    routes, and saved outputs
- `frontend/`
  - React/Electron desktop app GUI, playback logic, local app integration, and
    frontend tests
- `tests/`
  - automated tests plus media fixtures (`.mp4`, `.ts`, `.m3u8`) and test
    helpers
- `docs/`
  - project docs, architecture notes, and workflow guides
- `data/`
  - local output files, metrics, session data, and development input media;
    outputs are mainly stored as CSV plus local session files such as JSON and
    JSONL
- `.github/`
  - CI and repo automation files

## Known Roadmap Areas

Next up, I would focus on:

- grow the detector set beyond black-screen and blur
  and make alert rules easier to tune for different monitoring setups
- improve backend, session, and operator-facing diagnostics
- add a lightweight database layer for metrics, session history, and better diagnostics
- keep polishing the local FastAPI-backed desktop app runtime
- move the project toward a stronger desktop-first MVP without rushing into cloud or service complexity too early
- explore small MCP and agent-assisted features

The first thing I would keep tightening is the FastAPI boundary and the local
media/proxy path.


## Feedback Welcome On

The most helpful feedback right now is the kind that comes from real use:

- first-run usability and general clarity
- runtime stability, including which public streams actually work and which ones still fail
- what the strongest production direction for the project really is
- how much AI or agent help is actually useful, and where it would help most

## CI

CI is handled with a small GitHub Actions workflow in
`.github/workflows/ci.yml`. It runs backend tests plus frontend test and build
checks on pushes and pull requests, so the main desktop runtime path stays in
good shape as the project grows.

Over time, this can expand into packaging, platform, and release checks as the
desktop app matures.

The CI badge can be added after the first public push, once the final GitHub
repository path is settled.

## Security Notes

Remote media fetching is intentionally limited so the app only works with
sources we can reason about clearly:

- `api_stream` only accepts direct `.m3u8` and `.mp4` URLs such as a playlist
  URL or direct media file URL
- webpage-style player URLs are rejected early, including YouTube links and
  embedded player pages
- remote-input rules get stricter when the backend is used more like a
  service than when you run the app locally
- local or private-network targets are blocked by default unless they are
  deliberately allowed, for example `localhost`, `127.0.0.1`, `192.168.x.x`,
  or `10.x.x.x`
- the current backend is designed for local desktop use, and local session
  outputs stay on disk for review and debugging
- the trust boundary around remote inputs and the local FastAPI path is
  covered by targeted tests

For the current rules and the longer-term service boundary, start with:

- [contracts.md](./docs/contracts.md)
- [fastapi-boundary.md](./docs/fastapi-boundary.md)
- [testing-and-validation.md](./docs/testing-and-validation.md)

## Easy To Work On

This repo is intentionally structured to stay easy to read and extend. That is
why the design leans toward:

- explicit detector registration
- readable rule definitions
- simple session contracts
- split backend, Electron, and bridge responsibilities
- testable pure functions where possible
- no heavy plugin framework yet

If you want to jump in, the main extension points are straightforward:

- add a detector
- register it
- add or update a rule
- expose it in the frontend detector catalog
- follow the matching docs for sessions, contracts, frontend runtime, or tests

## Contributing

Contributions are very welcome, especially if you care about transparent
elections, practical monitoring tools, and building solid AI/streaming systems
around real civic use cases.

Useful contributions right now include:

- new stream-quality detectors for things like noise, stillness, and
  frozen-feed detection
- improvements to alert rules
- better examples and documentation
- careful test additions
- broader `api_stream` support for additional direct stream types and tricky provider behavior
- small focused contributions are especially welcome
