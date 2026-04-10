# AGENTS.md

This file is for people using AI-assisted tools for coding and development, as
well as human contributors who need the shortest safe path into the repo.

## Read First

Use these docs before making structural changes:

1. [`docs/README.md`](./docs/README.md)
2. [`docs/architecture.md`](./docs/architecture.md)
3. [`docs/contracts.md`](./docs/contracts.md)
4. [`docs/session-model.md`](./docs/session-model.md)

If you are adding detectors or rules, also read:

- [`docs/adding-an-analyzer.md`](./docs/adding-an-analyzer.md)
- [`docs/adding-an-alert-rule.md`](./docs/adding-an-alert-rule.md)

## Source Of Truth Order

When docs and code disagree, use this order:

1. code and tests
2. contract/lifecycle docs
3. architecture and reviewer docs
4. README / roadmap notes

## What This Repo Is

Election Stream Monitor is a local-first AI video monitoring system with:

- Python backend for validation, sessions, detectors, alert rules, and persistence
- React/Electron frontend for setup, playback, and operator-facing diagnostics
- explicit detector registration and explicit alert-rule mapping

It is not a dynamic plugin framework or service-oriented platform yet.

## Change Map

If you are changing:

- detector logic or metrics
  - [`src/detectors.py`](./src/detectors.py)
  - [`src/analyzer_registry.py`](./src/analyzer_registry.py)
- alert behavior
  - [`src/alert_rules.py`](./src/alert_rules.py)
- session lifecycle or progress semantics
  - [`src/session_runner.py`](./src/session_runner.py)
  - [`src/session_io.py`](./src/session_io.py)
  - [`docs/session-model.md`](./docs/session-model.md)
- `api_stream` transport, trust policy, or HLS loading
  - [`src/source_validation.py`](./src/source_validation.py)
  - [`src/stream_loader.py`](./src/stream_loader.py)
  - [`docs/contracts.md`](./docs/contracts.md)
- renderer playback or local HLS proxy behavior
  - [`frontend/electron/main.mjs`](./frontend/electron/main.mjs)
  - [`frontend/electron/hlsProxy.mjs`](./frontend/electron/hlsProxy.mjs)
  - [`frontend/src/components/VideoPlayerPanel.tsx`](./frontend/src/components/VideoPlayerPanel.tsx)

## Working Rules

- keep detector logic out of the session runner
- keep alert creation in the rule layer, not in detectors
- keep detector outputs flat and easy to serialize
- keep mode support explicit and honest
- prefer small helpers and explicit registration over framework-style abstraction
- do not add dynamic plugin discovery unless the repo is intentionally moving to that model

## Supported Modes

Current modes:

- `video_segments`
- `video_files`
- `api_stream`

Do not expose a detector to every mode by default. Make the supported modes a
deliberate choice.

## Testing Expectations

When you change behavior meaningfully, cover at least:

- detector or rule behavior
- routing/registry visibility if detector exposure changed
- one processor/session path if lifecycle or persistence is affected
- one frontend or bridge test if operator-visible behavior changed

Use [`docs/testing-and-validation.md`](./docs/testing-and-validation.md) for
the current routine commands and manual-validation split.

## Documentation Update Rule

If you change:

- a payload shape
- a lifecycle meaning
- a trust boundary
- a playback/monitoring responsibility split

update the matching doc in the same change. Avoid copying the same guidance
into multiple files; point to the owning doc instead.
