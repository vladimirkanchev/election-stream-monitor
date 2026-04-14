# Election Stream Monitor

![License: MIT](https://img.shields.io/badge/license-MIT-green)

Election Stream Monitor is a local-first AI video monitoring system for
election-related media sources.

It is built around a practical use case: reviewing polling-station streams,
archived recordings, or segmented video feeds and surfacing quality alerts
that matter during election monitoring. Today, the project is best understood
as an advanced prototype with a clear local-first workflow rather than a
finished service platform.

Right now the built-in checks focus on `Black Screen` and `Blur Check`
detector rules.
Supported sources are local `.mp4` video files, local `.ts` segment folders
with `index.m3u8`, and direct remote `.m3u8` / `.mp4` `api_stream` inputs.

I’m trying to keep the project small enough to understand and structured
enough to extend. The goal is to make detector, frontend, and rule changes
feel manageable instead of messy. Over time, I’d like to grow it into an MVP
with a FastAPI-backed service layer and a cloud deployment path, but that is
still a later step rather than the current stage of the project.

## Why this project exists

This project exists to support more transparent election observation in
Bulgaria in a practical, local-first way.

If a stream goes black, blurry, broken, or just becomes too low quality, that
is not only a technical issue. It can stop people from following elections in
real time and make it harder to take part in meaningful public oversight when
it matters most.

It is also a hands-on way to build skills in AI development, video analysis,
and streaming systems while working on something with clear civic value.

## Where To Start

You do not need to read this repo front to back.

Use this quick path:

- overview: this README
- architecture: [docs/architecture.md](./docs/architecture.md),
  [docs/contracts.md](./docs/contracts.md), and
  [docs/session-model.md](./docs/session-model.md)
- setup and docs map: [docs/README.md](./docs/README.md)
- frontend and transport: [docs/frontend-architecture.md](./docs/frontend-architecture.md)
- future FastAPI direction: [docs/fastapi-boundary.md](./docs/fastapi-boundary.md)

## Current Capabilities

### Backend

The backend validates the input, starts the session, steps through the media,
runs detectors, applies rules, and keeps writing local session state that the
frontend can read.

### Detection

The logic stays simple on purpose: detectors measure what is happening, then
rules decide when that should turn into an alert.

Right now it can catch:

- `Black Screen`
  - mainly from frames sampled from video files, segment streams, and
    `api_stream` sources
  - in simple terms: the picture goes fully black or almost black for long
    enough to matter
- `Blur Check`
  - looks for frames that are too soft, smeared, or out of focus
  - in simple terms: details disappear and the image stops looking sharp

### Frontend

The frontend gives you:

- a setup panel for source mode, path, and detector selection
- clear `Start Monitoring` and `End Monitoring` button controls
- playback for local files, local HLS-style folders, local `.mp4` files, and
  remote HLS streams through the local Electron HLS proxy
- a live alert feed showing detected issues as they are raised
- simple session status feedback with operator-friendly diagnostics and a
  `Show debug info` section for more detailed backend session state

If you want a quick feel for how that looks in the real app, the screenshot
below shows the same basic flow in UI form: setup on the left, live playback in
the center/right, and session state and alerts underneath. The original image
file is
[Frontend.png](./docs/assets/Frontend.png).

![Frontend screenshot](./docs/assets/Frontend.png)

### Session Model

This layer creates the session, updates progress, stores alerts and results,
and gives the UI something stable to poll.

Right now it works in a simple local-first way:

- a session is created when monitoring starts
- progress, alerts, and results are written to local JSON / JSONL files
- the frontend polls those files through the Electron/Python bridge
- sessions can complete, fail, or be cancelled cleanly

The current feature set is intentionally narrow, but it is designed to be easy
to extend.

## Input Modes

The project currently supports these input modes:

- `video_segments`
  - local `.ts` segment folders, typically organized around an `index.m3u8`
    playlist
- `video_files`
  - local `.mp4` files or folders containing `.mp4` files
- `api_stream`
  - direct remote `.m3u8` or `.mp4` URLs
  - webpage URLs such as YouTube links or generic HTML player pages are not
    supported

## Architecture At A Glance

It is still one project and one local workflow, not a distributed platform,
but the internal boundaries are deliberate. The detector and alert parts are
also being shaped with explicit extension points, so the analysis layer is
gradually moving toward a more plugin-friendly design.

From your point of view, the flow is pretty simple:

1. You pick a source, choose the detectors you want, and hit `Start Monitoring`.
2. The frontend handles the visible workflow: setup, playback, live status, and
   the basic session controls.
3. Electron acts as the local bridge between the UI and the Python runtime. It
   also handles playback-specific duties such as local media serving and the
   HLS proxy path used when remote streams cannot be played directly in the
   renderer.
4. The backend session runner and stream loader do the monitoring work in the
   background: they open files or stream chunks, move through them step by
   step, and keep the session running.
5. The analyzer registry keeps detector selection explicit, so only the
   detectors that fit the current mode are used.
6. Detectors produce structured results, and the alert-rule layer turns the
   important ones into warnings that are easier to notice and understand.
7. Session state is persisted locally, and the frontend polls snapshots through
   the Electron/Python bridge so you can see progress, status, and alerts in
   near real time instead of guessing whether the run is stuck.

The diagram below shows the runtime flow behind the app: source input,
playback source resolution, the Electron/Python boundary, backend monitoring,
and session-state polling back into the UI. The editable file is
[diagram_final.svg](./docs/assets/diagram_final.svg), and the PDF version is
[diagram_final.pdf](./docs/assets/diagram_final.pdf).

![Architecture outlook](./docs/assets/diagram_final.png)

## Installation

Requirements:

- Python `3.12+`
- Node.js / npm for the frontend
- `ffmpeg` and `ffprobe` on `PATH`
- `uv` for Python package and environment management if you want the `uv`-based
  setup flow

Tested with:

- React `19.1.0`
- Node.js `20.20.0`
- npm `10.8.2`
- `ffmpeg` `6.1.1`
- `ffprobe` `6.1.1`

Python setup:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

If you use `uv`, the same setup can look like this:

```bash
uv venv
. .venv/bin/activate
uv pip install -e .
```

Frontend setup:

```bash
cd frontend
npm install
```

Quick check after install:

```bash
python --version
node -v
ffmpeg -version | head -n 1
```

Environment notes:

- the project is currently tested only on Ubuntu `24.04`
- the desktop workflow is currently tuned for Linux/X11 development
- Electron playback and media behavior may differ on Wayland, macOS, or
  Windows until those paths are tested more broadly

## Running The Project

From the repository root, start the app with:

```bash
npm run dev
```

This starts:

- the Vite frontend
- the Electron shell
- the local Python detector/session bridge used by the app

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
- [frontend-architecture.md](./docs/frontend-architecture.md)

## Example Inputs

Safe public HLS examples for local testing:

- `https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8`
- `https://devimages-cdn.apple.com/samplecode/avfoundationMedia/AVFoundationQueuePlayer_HLS2/master.m3u8`
- `https://tungsten.aaplimg.com/VOD/bipbop_adv_fmp4_example/master.m3u8`

These are useful public test inputs for the `api_stream` mode. For local
fixtures, use the paths listed in [Running The Project](#running-the-project).
For provider quirks and blocked streams, see
[Known Limitations](#known-limitations).

## Known Limitations

- Not every provider is friendly to automated `.m3u8` fetching, so some public
  streams still refuse to cooperate. The local Electron HLS proxy helps with
  playback, but it cannot unlock a blocked upstream stream.
- YouTube page URLs and other webpage-style player links are not supported.
- Playback and monitoring are connected, but they are not the same thing, so
  one can fail while the other keeps going.
- This is still an advanced prototype, so the larger pilot and production
  hardening work is not finished yet.

## Tests And Validation

If you want a quick local confidence check, these are the main commands:

```bash
. .venv/bin/activate
pytest -q
npm --prefix frontend run test
npm run build
```

What is already covered well:

- backend unit and integration tests
- frontend Vitest coverage for playback and session-status UX
- opt-in public-stream smoke tests and a documented local validation workflow

If you want the deeper testing notes, start here:

- [testing-and-validation.md](./docs/testing-and-validation.md)
- [api-stream-local-validation.md](./docs/api-stream-local-validation.md)

## Docs

If you want the broader docs map, start with [docs/README.md](./docs/README.md).
For the most important system references, start with:

- [docs/architecture.md](./docs/architecture.md)
- [docs/contracts.md](./docs/contracts.md)
- [docs/session-model.md](./docs/session-model.md)

## Versioning And Releases

- the project is currently at version `0.1`
- version changes should reflect active iteration rather than strong
  backwards-compatibility guarantees
- release and versioning notes live in
  [release-versioning.md](./docs/release-versioning.md) and
  [CHANGELOG.md](./CHANGELOG.md)

## Data And Outputs

Important repo-safe references:

- [data/README.md](./data/README.md)
- [tests/fixtures/](./tests/fixtures)

For now, persistence is file-based rather than database-backed.

- detector result metrics are stored as CSV files in `data/metrics/`
- per-session results, progress, and alerts are stored as local session data in
  `data/sessions/`

This is good enough for local experimentation and review without introducing
database or service complexity too early.

## Repo Layout

- `src/`
  - Python backend runtime, detectors, session runner, bridge-facing CLI, and
    persistence/stores
- `frontend/`
  - React/Electron UI, playback logic, local bridge integration, and frontend
    tests
- `tests/`
  - backend tests plus checked-in deterministic media fixtures
- `docs/`
  - architecture, contracts, reviewer guidance, and workflow references
- `data/`
  - local-only runtime artifacts such as session outputs and metrics, plus
    local stream/video input data for development
- `.github/`
  - CI workflow and contribution templates

## Known Roadmap Areas

The areas I would work on next are:

- grow the detector set with rules for noise, stillness or frozen-feed
  detection, and other stream artifacts
- make alert rules easier to tune for different monitoring setups
- improve backend and session diagnostics, so it is easier to see what failed,
  what recovered, and what the system is doing right now
- keep hardening `api_stream` handling around tricky providers, trust
  boundaries, and longer runs
- prepare a cleaner FastAPI-backed local deployment path that can later grow
  into a more service-style MVP

## Feedback Welcome On

The most valuable feedback right now is on the parts of the project that are
still actively being shaped:

- streaming / transport architecture
- backend session lifecycle and failure policy
- frontend operator UX for playback vs monitoring state
- FastAPI boundary and local service deployment shape

## CI

A lightweight GitHub Actions workflow is included under
`.github/workflows/ci.yml` to run backend tests plus frontend test/build checks
on pushes and pull requests.

The CI badge can be added after the first public push, once the final GitHub
repository path is settled.

## Security Notes

Remote media fetching is intentionally constrained:

- `api_stream` only accepts direct `.m3u8` and `.mp4` URLs
- webpage-style player URLs are rejected early
- service-mode trust policy is stricter than local mode
- private or loopback targets are rejected by default unless they are
  explicitly allowed

For the current trust model and future service-boundary guidance, start with:

- [contracts.md](./docs/contracts.md)
- [fastapi-boundary.md](./docs/fastapi-boundary.md)

## Easy To Work On

This repo is intentionally structured to stay easy to read and extend. That is
why the design leans toward:

- explicit detector registration
- readable rule definitions
- simple session contracts
- testable pure functions where possible
- no heavy plugin framework yet

If you want to jump in, the main extension points are straightforward:

- add a detector
- register it
- add or update a rule
- expose it in the frontend detector catalog

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
- broader `api_stream` support for additional direct stream types and tricky
  provider behavior
