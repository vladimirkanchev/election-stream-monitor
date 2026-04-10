# PLANS.md

This file keeps the practical roadmap visible for contributors and people using
AI-assisted tools for coding and development. It is intentionally shorter than
the architecture docs and should be read as a current roadmap, not as the
source of truth for behavior.

## Current Stage

The project is best described as:

- local-first AI video monitoring system
- advanced prototype moving toward pre-pilot
- stronger in architecture/runtime shape than in full operational maturity

## Quick Return After A Break

If you are coming back after a few days away, start with
[`NEXT_SESSION.md`](./NEXT_SESSION.md). It is the shortest way to recover repo
context before going deeper into the docs or code.

## High-Priority Next Work

### 1. Detector growth through the current explicit pattern

Most useful next candidates:

- freeze-frame / stuck video
- low bitrate / weak segment quality
- missing segment / broken continuity
- missing audio / silent stream

### 2. Alert-rule growth without overcomplicating the rule layer

Keep the rule layer in [`src/alert_rules.py`](./src/alert_rules.py):

- readable
- cheap to compute
- session-local for rolling state only
- easy to tune from explicit thresholds

### 3. More operational hardening for `api_stream`

Continue improving:

- source trust policy
- reconnect/provider-failure behavior
- session reason/detail semantics
- real-provider confidence and playback diagnostics

### 4. Service-boundary preparation

The next service-friendly work should stay focused on:

- session start/read/cancel
- detector catalog
- playback resolution
- explicit trust boundaries for remote fetches

See [`docs/fastapi-boundary.md`](./docs/fastapi-boundary.md).

## Mid-Priority Work

- broader real-stream/manual validation coverage
- more operator-facing diagnostics and UX polish
- release/versioning discipline while the project stays in `0.x`
- screenshots or short demo assets for public presentation

## Things To Avoid For Now

- dynamic plugin loading
- deep inheritance trees
- large framework-style refactors
- coupling detector logic and alert logic together
- redesigning the frontend without a concrete operator need

## Preferred Contribution Order

For detector/rule changes, the safest order is:

1. detector output
2. schema/store update if needed
3. registry entry
4. alert rule
5. tests
6. frontend polish only if needed

Use:

- [`docs/adding-an-analyzer.md`](./docs/adding-an-analyzer.md)
- [`docs/adding-an-alert-rule.md`](./docs/adding-an-alert-rule.md)
