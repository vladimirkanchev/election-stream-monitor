# Advisory Coverage Evidence

This document records dated, subsystem-level coverage snapshots. It does not
set a threshold or replace behavior-oriented detector, runtime, and real-media
tests. Commands and measurement boundaries belong in
[testing-and-validation.md](./testing-and-validation.md#advisory-coverage-evidence).

## 2026-08-05 Baseline

- Source revision: `8a7c274`; captured with the coverage setup introduced on
  this branch.
- Backend command: `just coverage-backend`.
- Frontend command: `npm --prefix frontend run test:coverage` with Node 22.23.2
  and npm 11.15.0.
- Scope: fast in-process Python tests and the full Vitest suite only. Slow
  media, runtime E2E, soak, external streams, live PostgreSQL, detached
  workers, and external subprocesses remain outside this baseline.
- Raw JSON, XML, and LCOV reports are local ignored output under `coverage/`
  and `frontend/coverage/`.

| Subsystem | Files | Line coverage | Branch coverage | Reading the result |
| --- | ---: | ---: | ---: | --- |
| Detectors and rules | 12 | 94.1% | 84.0% | Fast synthetic behavior has broad execution evidence. |
| Session, runtime, and persistence | 28 | 93.8% | 82.2% | File-backed and synthetic runtime paths dominate this scope. |
| API and security | 19 | 97.3% | 93.1% | Share, route, configuration, and error paths are in the fast suite. |
| MCP | 4 | 94.4% | 62.5% | Small stdio surface; branch gaps are review leads. |
| Stream and media | 15 | 63.7% | 51.2% | HTTP/HLS and external/real-media confidence intentionally remain partly outside the fast baseline. |
| Shared application support | 3 | 95.9% | 76.7% | Process entry, configuration, and logging helpers. |
| Renderer | 31 | 79.2% | 75.0% | Includes production `frontend/src` outside the bridge. |
| Bridge | 8 | 47.8% | 59.2% | Normalization and transport gaps are visible without treating demo-only paths as failures. |
| Electron runtime | 15 | 67.1% | 72.1% | Startup and preload remain useful integration-test candidates. |

The backend aggregate is 87.7% lines and 74.7% branches across 81 files. The
frontend aggregate is 71.7% lines and 71.7% branches across 54 files. All
tracked production paths in the measurement boundary are assigned above; there
are no unassigned production files.

Compare future snapshots only when the commands, source boundaries, and tool
families are compatible. Review substantial drops or newly unexecuted critical
paths, then add tests only for a meaningful missing behavior. Do not use this
table as a product-quality, detector-accuracy, or deployment-readiness score.

## Critical Review Backlog

This is a behavior backlog derived from the baseline, not a coverage target.
It lists only meaningful missing behavior.

| Priority | Surface | Smallest useful next test |
| --- | --- | --- |
| High | `session_io.read_api_stream_seen_chunk_keys()` | In `tests/test_session_io.py`, prove a mixed de-dup log skips blank, malformed, and non-object entries while retaining later valid keys. |
| High | HTTP/HLS loader bootstrap and iterator lifecycle | Extend the nearest `test_stream_loader_http_hls_core_*.py` owner with one fake-transport `connect -> one slice -> close` contract; do not add a live-provider test. |
| Medium | `localMediaResponses.mjs` failure responses | Extend `localMediaResponses.test.mjs` with missing-local-file `404` and remote-fetch `502` response assertions. |
| Medium | `usePlaybackSource` source changes | Extend `usePlaybackSource.test.tsx` with a deferred stale resolution that cannot overwrite a newer source or error state. |

No new authentication or rate-limit work is indicated: both modules are fully
executed in this baseline and retain dedicated boundary-policy tests. The
remaining PostgreSQL row-shape fallbacks are acceptable defensive code until a
new driver requires them. Electron `main.mjs` is a subprocess measurement
limitation; keep its extracted-helper tests and use Electron smoke confidence
for composition changes. Legacy playlist utilities and the demo bridge remain
low-value targets until they become active product paths.
