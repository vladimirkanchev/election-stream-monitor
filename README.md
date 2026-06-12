# Election Stream Monitor

![License: MIT](https://img.shields.io/badge/license-MIT-green)

Election Stream Monitor is a local-first AI video monitoring system for
election-related media sources.

It watches polling-station streams, archived recordings, or segmented video
feeds and surfaces the quality problems that matter during monitoring.

Today it is a desktop-first advanced prototype with:

- a React/Electron app and local FastAPI backend
- three input modes: local video files, local segmented/HLS-style folders, and direct remote `api_stream` inputs
- two built-in detectors: `Black Screen` and `Blur Check`
- two built-in production alert rules layered on top of those detectors
- a small local MCP server with read-only alert-query tools
- selectable alert backend: file by default, PostgreSQL opt-in

It works best today for local development, demos, and small desktop-backed
monitoring runs.

**Quick try:** run `npm run dev`, choose `video_files`, and test with a local
`.mp4`.

The project is intentionally small. I want it to stay readable, useful, and
easy to extend without turning into a much heavier platform too early.

For maintainer workflow support, the repo also includes a small set of
workflow templates:

- branch start:
  [`docs/branch-purpose-template.md`](./docs/branch-purpose-template.md)
- PR shaping:
  [`.github/pull_request_template.md`](./.github/pull_request_template.md)
- merge/readiness pass:
  [`docs/merge-readiness-checklist.md`](./docs/merge-readiness-checklist.md)

## Why this project exists

This project exists to support more transparent election observation in
Bulgaria with a practical local-first workflow.

If a stream goes black, blurry, broken, or becomes too low quality, that is
not only a technical issue. It can make real-time observation harder and
reduce public oversight when it matters most.

It also gives users a practical way to add new video detectors around a real
civic use case. With an AI-assisted coding agent, they can describe the
monitoring problem they want to catch in plain language instead of needing
strong manual coding skills or deep video-processing knowledge.

## Where To Start

If you are:

- trying the project locally
  - start with [Running The Project](./README.md#running-the-project)
- learning the current product/runtime shape
  - read [Current Capabilities](./README.md#current-capabilities)
  - then [docs/architecture.md](./docs/architecture.md)
- changing detectors or alert rules
  - read [docs/adding-an-analyzer.md](./docs/adding-an-analyzer.md)
  - read [docs/adding-an-alert-rule.md](./docs/adding-an-alert-rule.md)
  - read [docs/testing-and-validation.md](./docs/testing-and-validation.md) for the focused detector/rule test lanes
  - use [detector_lab/README.md](./detector_lab/README.md) if the idea is still experimental
- navigating the whole maintainer docs set
  - use [docs/README.md](./docs/README.md)

## Desktop Runtime Summary

Most people will use the project through the Electron app. Electron starts
and talks to a local FastAPI backend for session control, detector loading,
playback-source resolution, and alert/session reads.

Electron still owns the desktop-only work: app startup, local media serving,
the HLS proxy path, and the UI bridge. Session snapshots are polled by the UI
while a run is active.

Today the local app works like this:

- session metadata, progress, and results stay on local disk
- alerts use one shared backend: file-backed by default, PostgreSQL as an
  explicit opt-in backend
- the session snapshot, alert routes, grouped incident routes, and MCP tools
  all read alerts through that shared alert backend

FastAPI auth and rate limiting are available for shared access. `local` mode
keeps them off by default, while `share` mode turns them on for the alerts
HTTP routes. MCP remains a separate local `stdio` tool surface.

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

### Local mode

```bash
. .venv/bin/activate
PYTHONPATH=src python -m api_server_cli local
```

Auth and rate limiting are off by default. These examples use the default
file-backed alert backend.

### Share mode

```bash
. .venv/bin/activate
PYTHONPATH=src python -m api_server_cli share
```

Auth and rate limiting are on by default. If you do not pass `--api-key`, the
CLI generates one and prints it once.

```bash
. .venv/bin/activate
PYTHONPATH=src python -m api_server_cli share --api-key my-demo-key
```

Use any long random string for `my-demo-key`.
Quick strong-key generator:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

`share` mode is for temporary local/demo sharing, not production deployment.
These examples keep the default file-backed alert backend.

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

- detector: `video_metrics`
- detector: `video_blur`
- alert rule: `video_metrics.default_rule`
- alert rule: `video_blur.default_rule`

Blur and motion-blur experiments beyond that live in
[`detector_lab/`](./detector_lab/README.md) until they are promoted on purpose.

The current detector/rule test split mirrors that boundary:

- production detector contracts
  - [`tests/test_detectors.py`](./tests/test_detectors.py)
- production alert-rule metadata and shared failure handling
  - [`tests/test_alert_rules.py`](./tests/test_alert_rules.py)
- production black-screen rule behavior
  - [`tests/test_alert_rules_black.py`](./tests/test_alert_rules_black.py)
- production blur-rule behavior
  - [`tests/test_alert_rules_blur.py`](./tests/test_alert_rules_blur.py)
- detector-lab experiments and practical alert policies
  - [`tests/test_detector_lab.py`](./tests/test_detector_lab.py)

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
- progress and results are written to local JSON / JSONL files
- alerts use one shared alert backend: file by default, PostgreSQL when you opt in
- the frontend polls session snapshots through Electron and the local FastAPI backend
- sessions can complete, fail, or be cancelled cleanly

The current feature set is still narrow, but easy to extend.

## Input Modes

- `video_segments` — local `.ts` segment folders, usually around an `index.m3u8` playlist
- `video_files` — local `.mp4` files or folders
- `api_stream` — direct remote `.m3u8` or `.mp4` URLs, not generic web pages

## Architecture At A Glance

This is still one local-first project, not a distributed platform, but the
main splits between frontend, backend, and tools are there on purpose. That
fits the current project stage: an advanced prototype moving toward pre-pilot,
with clearer responsibilities than broad operational maturity.

In practice, the flow looks like this:

1. You choose a source, pick detectors, and start monitoring from the UI.
2. The frontend and Electron handle the visible workflow: setup, playback,
   status, alerts, and desktop-only jobs like local media serving and the HLS
   proxy path.
3. FastAPI starts and manages sessions, checks sources, resolves playback
   inputs, and hands the monitoring work to the backend services and worker
   process.
4. Detectors and alert rules process the media, while local session state and
   the shared alert backend keep progress, results, and alerts. File-backed
   alerts stay the default, with PostgreSQL available as an opt-in backend.

FastAPI and MCP are separate entry points over the same local alert/session
data. FastAPI owns the main desktop-backed HTTP path, while MCP stays a local
read-only tool surface over the same saved data.

The diagram below shows the same flow in one picture.

![Architecture outlook](./docs/assets/diagram_final.png)

### Who Owns What

- **Electron** owns the desktop shell, runtime startup, UI bridge, local media serving, and the HLS proxy path.
- **FastAPI** owns the monitoring backend: session control, source validation, stream resolution, detector/rule execution, and session-state updates. In `share` mode, it also applies API-key auth and rate limiting to the alerts routes.
- **MCP** remains a separate local `stdio` read-only alert-reading surface. It reads local alert/session data and stays outside FastAPI auth and rate limiting.
- **Local session data and the shared alert backend** persist progress, results, and alerts for the local-first runtime.
- **FastAPI and MCP** read through the same persisted alert/session path, not separate stores or monitoring pipelines.

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

Design intent:

- focused lanes own one seam each
- broader lanes such as `just test-fast` and `just ci-local` compose those
  focused lanes instead of redefining them
- the harness stays readable and stable by mirroring the current project
  structure rather than hiding it

Current high-value commands:

- `just env-check`
  - lightweight local tool and version sanity check
- `just test-detectors`
  - focused production detector contract and metric lane
- `just test-processor`
  - focused production processor and orchestration lane
- `just test-alert-rules`
  - focused production alert-rule policy lane
- `just test-hls`
  - focused HLS / `api_stream` loader and reconnect-policy lane
- `just test-frontend`
  - focused frontend runtime and bridge checkpoint lane
- `just docs-check`
  - docs/workflow consistency and CI-ownership alignment lane
- `just fixture-check`
  - fixture ownership and environment-assumption policy lane
- `just branch-cleanup`
  - non-destructive branch hygiene and push/review readiness check
- `just test-fast`
  - composed fast production runtime lane
- `just test-detector-lab`
  - fast synthetic detector-lab lane for experiment and runner confidence
- `just test-real-media`
  - slower checked-in fixture lane for detector-lab real-media confidence
- `just lint`
  - backend Ruff plus frontend ESLint
- `just typecheck`
  - backend mypy, backend pyright, and frontend TypeScript typecheck
- `just ci-local`
  - best local “ready to push?” lane for fast branch feedback
  - closer to the current CI feature-gate shape than `just test-fast`

Use the `justfile` to keep local validation readable and repeatable. Use
[docs/testing-and-validation.md](./docs/testing-and-validation.md) when you
need the fuller CI, weekly, or slow-lane picture.

Current lightweight workflow templates:

- [`.github/pull_request_template.md`](./.github/pull_request_template.md)
  - for PR purpose, scope, validation, fixture impact, and docs impact
- [branch-purpose-template.md](./docs/branch-purpose-template.md)
  - for branch purpose, scope, and split trigger
- [merge-readiness-checklist.md](./docs/merge-readiness-checklist.md)
  - for final validation, cleanup, and merge safety

## Repo-Local Codex Skills

The repo includes a small set of repo-local Codex skills under
[`./.agents/skills/`](./.agents/skills) for repo-aware diagnostics and review:

- summaries and incident understanding:
  - `summarization`
  - `incident-timeline`
  - `root-cause-suggestion`
- workflow and branch shaping:
  - `branch-pr-readiness`
  - `ci-failure-triage`
  - `dependency-change-review`
  - `task-planning-evaluation`
- validation and test strategy:
  - `test-strategy-review`
  - `manual-validation-planner`
  - `fixture-environment-safety`
- code and boundary review:
  - `detector-rule-review`
  - `frontend-bridge-review`
  - `alert-backend-parity-review`
  - `security-surface-review`
  - `docs-alignment`

Use these skills when you want quick repo-aware help with:

- summaries, incident timelines, and likely root causes
- branch drift, commit or PR shape, merge readiness, and CI triage
- dependency-file drift and task planning
- test coverage gaps, low-value test cleanup, and smallest honest validation lanes
- manual smoke plans before merge
- fixture and environment safety
- detector/rule review, frontend or bridge review, and alert-backend parity
- project-doc and code-doc alignment

These are mainly for AI-assisted contributors and debugging workflows. They
are lightweight text helpers, not a separate plugin framework, and they are
not required to run the project.

The deterministic tests for these skills live in:

- [test_repo_skills.py](/home/vlad/Projects/election-stream-monitor/tests/test_repo_skills.py)
- [skill_test_support.py](/home/vlad/Projects/election-stream-monitor/tests/skill_test_support.py)
- [skill_output_snapshots](/home/vlad/Projects/election-stream-monitor/tests/fixtures/skill_output_snapshots)

## Running The Project

Normal desktop app:

```bash
npm run dev
```

Backend only:

```bash
. .venv/bin/activate
PYTHONPATH=src python -m api_server_cli local
```

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
manual key, the CLI generates one and prints it once. See
[FastAPI Access Modes](./README.md#fastapi-access-modes).

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

Quick first run:

1. Run `npm run dev` from the repo root.
2. Wait for the Electron window to open.
3. Pick an input mode and choose a source.
4. Hit `Start Monitoring`.

Sample local inputs are listed in [Example Inputs](./README.md#example-inputs).

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

Tested with:

- React `19.1.0`
- Node.js `20.20.0`
- npm `10.8.2`
- `ffmpeg` `6.1.1`
- `ffprobe` `6.1.1`

## Example Inputs

If you are trying the app for the first time, start with `video_files`.

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
. .venv/bin/activate
pip install -e .[test]
pytest -q -m "not e2e and not slow"
npm --prefix frontend run test
npm run build
```

That fast pass focuses on unit and service-level coverage. Use
[`docs/testing-and-validation.md`](./docs/testing-and-validation.md) for the
slower e2e, snapshot-smoke, and live-validation checks.

For more detail:

- [testing-and-validation.md](./docs/testing-and-validation.md)
- [api-stream-local-validation.md](./docs/api-stream-local-validation.md)

## Docs

For the authoritative owner docs, start with
[docs/README.md](./docs/README.md). The main deep dives are:

- [docs/architecture.md](./docs/architecture.md) for the current system shape
- [docs/contracts.md](./docs/contracts.md) for backend and frontend API/data rules
- [docs/session-model.md](./docs/session-model.md) for session lifecycle and local state
- [docs/fastapi-boundary.md](./docs/fastapi-boundary.md) for FastAPI/MCP boundary and access modes
- [docs/frontend-architecture.md](./docs/frontend-architecture.md) for frontend and playback
- [docs/testing-and-validation.md](./docs/testing-and-validation.md) for test scope

## Versioning And Releases

- the project is now in an early `0.4.0` stage
- expect active iteration and improving internal stability rather than strict
  long-term compatibility
- release notes live in [release-versioning.md](./docs/release-versioning.md)
  and [CHANGELOG.md](./CHANGELOG.md)

## Data And Outputs

Useful references:

- [tests/fixtures/](./tests/fixtures)

Outputs are still local-first:

- detector metrics: `data/metrics/`
- per-session metadata, progress, and results: `data/sessions/`
- alerts: file-backed by default, with PostgreSQL available as an opt-in backend

## Repo Layout

Quick map:

- `src/` — Python backend, detectors, sessions, stream loading, and FastAPI
- `frontend/` — React/Electron app, playback, and frontend tests
- `tests/` — automated tests, fixtures, and helpers
- `docs/` — architecture, contracts, and workflow notes
- `data/` — local metrics, session outputs, and sample inputs
- `scripts/` — small developer and repo utilities
- `.agents/` — repo-local Codex skills
- `.github/` — CI and repo automation

## Known Roadmap Areas

What I would work on next:

- add more detectors and keep alerts easy to tune
- improve runtime debugging and status information
- keep hardening the local Electron + FastAPI app
- add more MCP tools and strengthen security carefully
- decide when PostgreSQL-backed alerts should stay opt-in or become the default
- make packaging and releases easier over time

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

- FastAPI `share` mode adds API-key auth and rate limiting on the alerts routes
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

## Easy To Work On

This repo leans toward:

- explicit detector and alert-rule registration
- clear Electron, FastAPI, and MCP boundaries
- simple local session files and selectable alert backend
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
- FastAPI, MCP, and alert-query improvements
- better docs, tests, and first-run usability

Small focused contributions are especially helpful here.
