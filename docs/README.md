# Docs Index

This folder is the internal reference set for contributors, reviewers, and
people using AI-assisted tools for coding and development. Use it as the
intent layer for the current repo state, not as end-user documentation.

## Best First Reads

If you are new to the repo, read these in order:

1. [../NEXT_SESSION.md](../NEXT_SESSION.md) if you are returning after a break
2. [architecture.md](./architecture.md)
3. [contracts.md](./contracts.md)
4. [session-model.md](./session-model.md)
5. then the task-specific doc for the subsystem you want to change

## Document Ownership

Use each doc for one main question:

- [architecture.md](./architecture.md)
  - system responsibilities
  - runtime boundaries
  - where a change belongs
- [contracts.md](./contracts.md)
  - stable payloads and bridge contracts
  - `api_stream` trust, failure, and playback contracts
- [session-model.md](./session-model.md)
  - persisted session files
  - lifecycle meaning
  - progress semantics
- [data-models.md](./data-models.md)
  - compact field guide for detector, alert, and session shapes
- [frontend-architecture.md](./frontend-architecture.md)
  - React/Electron split
  - playback state
  - frontend transport boundary
- [fastapi-boundary.md](./fastapi-boundary.md)
  - what a future FastAPI layer should own
  - what should stay local/runtime-specific
- [testing-and-validation.md](./testing-and-validation.md)
  - routine verification commands
  - CI scope
  - manual vs automated validation
- [api-stream-local-validation.md](./api-stream-local-validation.md)
  - repeatable local `api_stream` trial workflow
  - expected status, logs, and cleanup
- [reviewer-guide.md](./reviewer-guide.md)
  - fastest review order
  - best feedback targets for the current project stage
- [release-versioning.md](./release-versioning.md)
  - `0.x` release expectations

## Extension Guides

Use these when changing the detector/rule surface:

- [adding-an-analyzer.md](./adding-an-analyzer.md)
- [adding-an-alert-rule.md](./adding-an-alert-rule.md)
- [detector-template.md](./detector-template.md)

## Visual References

- [runtime-flow.svg](./runtime-flow.svg)
- [plugin-structure.svg](./plugin-structure.svg)
- [frontend-overview.svg](./frontend-overview.svg)
- [frontend-flow.svg](./frontend-flow.svg)
- [detector-and-alert-extension-flow.svg](./detector-and-alert-extension-flow.svg)

## Task-Based Reading Paths

If you are working on:

- transport / streaming
  - [architecture.md](./architecture.md)
  - [contracts.md](./contracts.md)
  - [testing-and-validation.md](./testing-and-validation.md)
- session lifecycle / persistence
  - [session-model.md](./session-model.md)
  - [contracts.md](./contracts.md)
- frontend playback / monitoring UX
  - [frontend-architecture.md](./frontend-architecture.md)
  - [contracts.md](./contracts.md)
- detector or alert extension
  - [adding-an-analyzer.md](./adding-an-analyzer.md)
  - [adding-an-alert-rule.md](./adding-an-alert-rule.md)
  - [data-models.md](./data-models.md)
- review / onboarding
  - [reviewer-guide.md](./reviewer-guide.md)
  - [architecture.md](./architecture.md)

## Update Rules

- Prefer code and tests as the final source of truth when a doc drifts.
- If you change a boundary, lifecycle meaning, or payload shape, update the
  matching doc in the same change.
- Avoid copying large blocks of guidance across files. Link to the owning doc
  instead.
