# AGENTS.md

Use this file for the shortest safe route into AI-assisted changes. For product
orientation, start with [README.md](./README.md); for human branch flow, use
[CONTRIBUTING.md](./CONTRIBUTING.md); for maintainer document routing, use
[docs/README.md](./docs/README.md).

## Read First

Before structural changes, read:

1. [docs/README.md](./docs/README.md)
2. [docs/architecture.md](./docs/architecture.md)
3. [docs/contracts.md](./docs/contracts.md)
4. [docs/session-model.md](./docs/session-model.md)

For detector or alert-rule work, also read
[adding-an-analyzer.md](./docs/adding-an-analyzer.md) or
[adding-an-alert-rule.md](./docs/adding-an-alert-rule.md). For repo-local
skill changes, read [the skill inventory](./.agents/skills/INVENTORY.md),
[testing-and-validation.md](./docs/testing-and-validation.md), and
`tests/test_repo_skills.py`.

## Risky Change Routing

Read the owning documents and use the nearest repo-local skill when the work
is review, drift, or validation-shape heavy.

- session or alert persistence or runtime backend selection: read
  [`docs/contracts.md`](./docs/contracts.md),
  [`docs/session-model.md`](./docs/session-model.md), and
  [`docs/testing-and-validation.md`](./docs/testing-and-validation.md). Use
  `persistence-backend-review` or `test-strategy-review`.
- FastAPI or MCP security, auth, `share` mode, secrets, rate limits, or trust boundaries:
  read [`docs/contracts.md`](./docs/contracts.md),
  [fastapi-boundary.md](./docs/fastapi-boundary.md), and
  [mcp-server.md](./docs/mcp-server.md). Use `fastapi-mcp-security-review`.
- real-media, long-running stream, or environment-sensitive validation work:
  read
  [testing-and-validation.md](./docs/testing-and-validation.md) and
  [fixture-environment-policy.md](./docs/fixture-environment-policy.md). Use
  `fixture-environment-safety`, `test-strategy-review`, or
  `manual-validation-planner`.
- detector extension, detector-lab growth, or analyzer/rule ownership changes:
  read [`docs/adding-an-analyzer.md`](./docs/adding-an-analyzer.md),
  [`docs/adding-an-alert-rule.md`](./docs/adding-an-alert-rule.md), and
  [testing-and-validation.md](./docs/testing-and-validation.md). Use
  `detector-rule-review` or `test-strategy-review`.

In this routing section, prefer one primary skill for the main seam. Add
another only when the branch or validation story genuinely crosses that
boundary.

## Source Of Truth

When documentation and implementation disagree, prefer:

1. Code and tests.
2. Contract and lifecycle documents.
3. Architecture and reviewer documents.
4. README and roadmap notes.

## Project Boundaries

Election Stream Monitor is a local-first video-monitoring advanced prototype:

- Python owns validation, sessions, detectors, alert rules, and persistence.
- React/Electron owns setup, playback, and operator-facing diagnostics.
- Detector registration and alert-rule mapping are explicit.
- It is not a dynamic plugin framework or service-oriented platform yet.

Keep detector facts out of the session runner, alert creation in the rule
layer, outputs flat and serializable, and mode support explicit. Prefer small
helpers and explicit registration over framework-style abstractions. Do not
add dynamic plugin discovery without an intentional architecture decision.

Supported source modes are `video_segments`, `video_files`, and `api_stream`.
Do not expose a detector to every mode by default.

## Change Placement

- Detector facts, registration, or metric work: the `src/detectors/` package,
  [adding-an-analyzer.md](./docs/adding-an-analyzer.md), and
  [contracts.md](./docs/contracts.md).
- Alert behavior: [adding-an-alert-rule.md](./docs/adding-an-alert-rule.md),
  [contracts.md](./docs/contracts.md), and the rule layer.
- Session lifecycle or persistence: [session-model.md](./docs/session-model.md),
  [contracts.md](./docs/contracts.md), and [architecture.md](./docs/architecture.md).
- `api_stream`, HLS loading, or source trust: [contracts.md](./docs/contracts.md)
  and [fastapi-boundary.md](./docs/fastapi-boundary.md).
- Renderer, Electron bridge, playback, or local HLS proxy: [frontend-architecture.md](./docs/frontend-architecture.md)
  and [contracts.md](./docs/contracts.md).

## Validation And Documentation

For meaningful behavior changes, cover the affected detector or rule, relevant
registry/routing visibility, one processor or session path when lifecycle or
persistence changes, and one frontend or bridge test when operator-visible
behavior changes. [testing-and-validation.md](./docs/testing-and-validation.md)
owns current commands and manual-validation boundaries.

Update the nearest owning document when changing a payload shape, lifecycle
meaning, trust boundary, playback/monitoring responsibility, or repo-local
skill behavior. Link to that owner instead of copying the same guidance into
multiple files.
