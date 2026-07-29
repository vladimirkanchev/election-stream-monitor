# Changelog

All notable changes to this project should be documented in this file.

The format is intentionally lightweight and practical for the current project
stage.

## [Unreleased]

## [0.6.4] - 2026-07-29

Detector and alert validation confidence release.

Highlights:

- detector-lab, production detector, alert-rule, processor, real-media, E2E,
  and manual validation lanes now have explicit ownership
- synthetic detector-lab coverage is split into focused owners while retaining
  its behavioral baseline
- duplicate processor coverage was consolidated around canonical test owners
- fixture identity, calibration evidence, exact truth, and promotion rules are
  documented and checked for catalog integrity
- checked-in real-media confidence has a focused lane, stable transition
  assertions, and compact failure diagnostics
- focused detector edge coverage now includes malformed media-tool output,
  incomplete decoder frames, and decoded black-screen negatives
- MCP SDK compatibility is pinned for the current local MCP boundary

## [0.6.3] - 2026-07-26

Runtime security and detector-validation foundation release.

Highlights:

- PostgreSQL alert storage is a documented opt-in, forward-only path with
  parity, live-store, runtime/operator, rollback, and schema-policy coverage
- weekly PostgreSQL and real-media confidence lanes were stabilized, and the
  frontend CI toolchain was pinned for repeatable installs
- share-mode FastAPI exposure, authentication, request bounds, and secret
  handling were hardened while preserving the loopback-local workflow
- the MCP boundary remains explicitly local, stdio-only, read-only, and
  bounded
- detector-validation ownership and duplicate-analysis guidance established
  the foundation for the subsequent focused validation work

## [0.6.2] - 2026-07-11

PostgreSQL session-store rollout-confidence release.

Highlights:

- the opt-in PostgreSQL session store gained live bootstrap, runtime, and
  failure-policy smoke coverage
- session-store bootstrap, forward-only behavior, and migration boundaries are
  documented more explicitly while file-backed storage remains the default
- validation guidance now distinguishes routine checks from explicit live
  PostgreSQL confidence runs

## [0.6.1] - 2026-07-08

AI-harness policy refresh release.

Highlights:

- repo-local review skills now cover persistence backend review, FastAPI/MCP
  security review, real-media validation review, release/version readiness,
  and PostgreSQL migration rollout more explicitly
- routing guidance in `AGENTS.md`, maintainer docs, and validation docs is
  clearer about which skill or harness lane should own a given kind of change
- deterministic repo-skill tests were refactored and expanded so nearby-skill
  overlap, hand-off boundaries, and stable snapshot examples drift less
  quietly over time
- the broad security-surface review and the branch-scoped FastAPI/MCP security
  review now have a cleaner separation of purpose

## [0.6.0] - 2026-07-07

Dual-backend persistence stage release.

Highlights:

- session persistence now has a clearer supported contract across file-backed
  and PostgreSQL-backed stores, with parity coverage around metadata, latest
  progress, ordered results, cancel intent, and snapshot shape
- alert persistence and session persistence can both use PostgreSQL as an
  intentional supported backend option, while file-backed storage remains the
  default rollout mode
- detached-worker runtime confidence is stronger across FastAPI start, read,
  cancel, and early-read behavior, with validation lanes that distinguish fast
  store/service confidence from slower runtime confidence
- session-persistence, contracts, and validation docs now describe the current
  file-default and PostgreSQL-opt-in model more directly

## [0.5.2] - 2026-07-04

Session-store and stream/runtime hardening follow-up release.

Highlights:

- shared `SessionStore` contract coverage is tighter across file-backed and
  PostgreSQL-backed session persistence, including latest-only progress,
  append-ordered results, metadata-only snapshots, and cancel semantics
- PostgreSQL session-store adapter/bootstrap coverage and the default
  in-memory PostgreSQL-like test double are clearer and easier to maintain
- session-store owning docs, contract docs, and validation guidance now align
  more closely with the tested backend behavior
- recent `api_stream` and HTTP/HLS hardening work is now reflected as current
  runtime behavior rather than only older baseline feature notes

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
