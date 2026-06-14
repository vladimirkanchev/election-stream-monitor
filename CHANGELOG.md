# Changelog

All notable changes to this project should be documented in this file.

The format is intentionally lightweight and practical for the current project
stage.

## [Unreleased]

## [0.5.1] - 2026-06-14

Workflow and AI-harness follow-up release.

Highlights:

- planning, validation, docs-alignment, and branch-readiness skills now share
  a clearer lightweight execution pattern
- branch workflow docs now keep one smaller owner per topic and route contract-
  sensitive changes more explicitly
- the harness now asks for explicit test evidence, honest manual-only
  confidence when needed, and dependency-file justification before merge

## [0.5.0] - 2026-06-14

Detector/runtime extension-contract release.

Highlights:

- production detectors now live under `src/detectors/` with explicit runtime
  registration and cleaner shared contracts
- detector catalog parity is now covered across the canonical registry, FastAPI
  route, session CLI, and export CLI
- processor, detector, and alert-rule contract coverage is tighter and easier
  to route through during refactors
- maintainer workflow docs, planning guidance, and validation ownership were
  aligned with the current extension-focused architecture

## [0.4.1] - 2026-06-13

Developer workflow and maintainer-harness follow-up release.

Highlights:

- local `just` harness for focused validation, push-readiness, and lightweight
  branch checks
- workflow templates, contributor guidance, and docs ownership cleanup for
  branch flow and maintainer routing
- lightweight guardrails for fixture/environment policy, dependency drift, and
  PR-template completeness
- expanded focused tests for repo-local skills and optional local hook routing

## [0.4.0] - 2026-05-20

- ongoing transport, session, and operational hardening
- continued frontend/operator UX refinement
- PostgreSQL alert storage is now implemented and supported as an opt-in
  backend, while file-backed alerts remain the default rollout mode

## [0.3.1] - 2026-05-18

CI/CD hardening and test-coverage follow-up release.

Highlights:

- stronger CI ownership and drift guards for workflow targets, path existence,
  split-suite registration, and frontend contract targeting
- short CI maintainer guide plus tighter CI/project doc alignment
- expanded and refactored focused CI-helper regression coverage
- alert-query slice cleanup with tighter typing and direct adapter seam tests

## [0.3.0] - 2026-05-09

FastAPI boundary and MCP feature update.

Highlights:

- local MCP server with read-only alert-query tools
- grouped alert timeline and incident-summary query tools
- explicit FastAPI `local` and `share` access modes
- API-key auth and rate limiting for temporary shared demo access
- split and expanded boundary-focused test coverage

## [0.1.0] - 2026-04-06

Initial public baseline prepared for repository sharing.

Highlights:

- local-first monitoring workflow across frontend, Electron bridge, and Python
  backend
- direct `api_stream` support for remote `.m3u8` and `.mp4` inputs
- local Electron HLS proxy for remote HLS playback
- explicit trust policy for remote media fetching
- documented architecture, contracts, reviewer guide, testing notes, and
  FastAPI boundary
- backend and frontend test coverage plus lightweight CI workflow
