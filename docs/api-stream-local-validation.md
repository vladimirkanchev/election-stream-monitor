# API Stream Local Validation

This project now keeps a small repeatable local `api_stream` validation set for
pre-real-stream checks.

## Best use of this doc

Use this workflow when you want:

- one repeatable local live-stream check before trying a real provider
- a shared checklist for source input, expected status, logs, and cleanup
- a quick way to compare a finished session against expected metrics

Artifacts:

- `tests/fixtures/media/api_stream_expectations.json`
  - names the current local validation cases
  - defines:
    - selected detectors
    - expected chunk count
    - expected alert count
    - expected final status
- `scripts/api_stream_local_validation.py`
  - serves one checked-in HLS fixture over local HTTP
  - prints a concrete manual checklist
  - standardizes:
    - source input
    - expected status
    - expected logs
    - expected cleanup
  - compares a finished session snapshot against the expected metrics

Typical workflow:

1. List the current validation fixtures
   - `python scripts/api_stream_local_validation.py list-fixtures`
2. Serve one fixture and follow the printed checklist
   - `python scripts/api_stream_local_validation.py serve-fixture --fixture-id api_stream_clean_baseline_long_metrics_only`
3. Start monitoring from the app or with the printed CLI command
4. Poll the session snapshot and watch `processed_count` move
5. Cancel the run if you want to validate live shutdown behavior
6. Compare the final session against the expectation manifest
   - `python scripts/api_stream_local_validation.py check-session --fixture-id <fixture_id> --session-id <session_id>`

## What is standardized

Each validation case now gives you:

- source input
- expected status
- expected chunk count
- expected alert count
- expected logs
- expected cleanup checks

Why this exists:

- manual pre-real-stream validation stays consistent across runs
- failures become easier to interpret because the expected metrics are explicit
- source input, expected terminal state, log hints, and cleanup checks are all
  printed in one place instead of being remembered ad hoc
- chunk progression, cancel behavior, and temp cleanup can be checked with the
  same local fixture every time

## Notes For Agents

- If you change live-loader behavior materially, update the expectation
  manifest or this workflow will become misleading.
- Keep the validation set small and stable; it is meant for repeatability, not
  for covering every possible fixture.
