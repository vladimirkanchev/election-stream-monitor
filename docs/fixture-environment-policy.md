# Fixture / Environment Policy

Use this as the short source of truth for fixture ownership and environment
assumptions in tests, local validation, and CI.

## Definitions

### Committed fixture

A committed fixture is test data checked into the repo and intended for shared,
repeatable use.

In this repo, that usually means:

- files under `tests/fixtures/media/video_files/`
- files under `tests/fixtures/media/video_segments/`
- checked-in catalogs or expectations such as:
  - `tests/fixtures/media/fixture_catalog.json`
  - `tests/fixtures/media/ground_truth.json`
  - `tests/fixtures/media/api_stream_expectations.json`

Committed fixtures are allowed in local validation and CI when the lane is
meant to use them.

### Local-only asset

A local-only asset is developer-owned input that is not part of the shared test
contract.

In this repo, that includes:

- ignored media under `tests/fixtures/media/election_clips/`
- local research datasets
- machine-specific runtime data under `data/`
- ad hoc files added only for one debugging or analysis session

Local-only assets may help local exploration, but they must not be required by
default tests, default harness commands, or default CI.

### Environment-coupled test

An environment-coupled test depends on tools, sockets, runtime policy, or host
behavior that is not guaranteed everywhere.

Common examples here:

- tests that need `ffmpeg` or `ffprobe`
- tests that need local socket binding or HTTP fixture serving
- tests that depend on Electron-local runtime policy
- tests that need a real PostgreSQL instance

These tests are allowed when their lane is explicit and the assumption is
stated plainly.

## Default Fast CI Rules

Default fast CI must never assume:

- local-only media or research datasets
- developer-specific paths or repo-external files
- manual setup beyond normal project install
- optional tools unless the lane explicitly installs or declares them
- host-specific socket behavior unless the test already treats that as optional

If a test needs one of those, keep it out of the default fast lane or mark the
assumption clearly.

## Practical Rules

- Prefer committed fixtures for shared automated confidence.
- Prefer synthetic inputs when committed real fixtures are not needed.
- Keep local-only assets out of default fixture sets and default harness lanes.
- Name environment-coupled tests honestly instead of making them look universal.
- If a behavior is only safe to verify manually or in a slower lane, say that plainly.

## Checker Scope

The lightweight policy check currently scans:

- maintainer docs and selected repo docs
- Python tests
- shared fixture metadata files

It does not try to infer every environment assumption in the repo. It only
catches the highest-signal drift:

- local-only fixture references outside the small allowlist
- hardcoded developer repo-root paths in Python tests

## Where To Apply This

- `docs/testing-and-validation.md`
- `tests/fixtures/media/README.md`
- local `just` validation commands
- future fixture or environment safety checks
