# Release And Versioning Notes

This project is still in an active `0.x` stage.

## Current Approach

- versions are expected to move quickly as the architecture hardens
- minor releases may still include meaningful internal changes
- compatibility matters, but strong long-term API stability is not yet the main
  goal

## What To Version Carefully

Even in an early stage, these areas should change deliberately:

- frontend/backend bridge payloads
- session snapshot structure
- `api_stream` validation and trust-policy behavior
- persisted session/progress fields

Those contracts are documented in:

- [contracts.md](./contracts.md)
- [session-model.md](./session-model.md)

## Practical Release Guidance

For now, a small practical release process is enough:

1. update the version in `pyproject.toml` and any matching frontend metadata if
   needed
2. add the important change notes to [CHANGELOG.md](../CHANGELOG.md)
3. rerun the main verification commands
4. tag and publish from a known-good commit

## Current Project Stage

The current versioning posture matches the actual project state:

- local-first AI video monitoring system
- advanced prototype moving toward pre-pilot
- still hardening operationally before broader pilot-style expectations
