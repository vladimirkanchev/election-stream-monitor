# Release And Versioning Notes

This project is still in an active `0.x` stage.

Current public stage: `0.6.1`

- `0.5.0` marked the detector/runtime extension-contract refactor stage
- `0.5.1` was the workflow and AI-harness follow-up on top of that stage
- `0.5.2` adds session-store hardening and stream/runtime follow-up work on
  top of that stage
- `0.6.0` marks dual-backend persistence as a supported project stage: file
  remains the default runtime path, while PostgreSQL is now a documented
  supported option for session and alert persistence, with both backends still
  explicit opt-in rollout paths rather than default storage
- `0.6.1` is the AI-harness policy refresh on top of that stage: repo-local
  review skills, routing guidance, and deterministic skill tests now align
  more clearly before the next persistence and security branches

## Current Approach

- versions are expected to move quickly as the architecture hardens
- minor releases may still include meaningful internal changes
- compatibility matters, but strong long-term API stability is not yet the main
  goal

In practice for the current stage:

- use a minor release when the project moves to a new architecture or product
  stage
- use a patch release when the main change is workflow, validation, docs,
  harnessing, or another follow-up that does not widen the product surface

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
   needed, plus any user-facing release references such as `README.md`
2. add the important change notes to [CHANGELOG.md](../CHANGELOG.md)
3. rerun the main verification commands
4. tag and publish from a known-good commit

For this repo, the normal version-bearing files are:

- `pyproject.toml`
- `frontend/package.json`
- `frontend/package-lock.json`
- `src/api/app.py`
- `uv.lock`
- any user-facing stage references such as `README.md`

When a release includes alert-storage changes, state the rollout mode
explicitly in the release notes:

- file-backed alerts remain the default backend
- PostgreSQL alerts are supported behind `ESM_ALERT_STORE_BACKEND=postgres`

That keeps releases honest about the current rollout state and avoids
implying a project-wide default flip too early.

When a release or PR includes session-storage changes, keep the wording just as
explicit:

- say "adds an opt-in PostgreSQL session storage path" when file-backed
  storage still remains the default
- say "forward-only" when PostgreSQL applies to newly created sessions only
- do not say "migrates all sessions" unless the branch truly includes reviewed
  historical backfill behavior and the docs/tests prove it

For shared persistence rollout wording, keep one compact rule:

- say both session and alert PostgreSQL backends are opt-in unless a branch
  truly changes the defaults
- say session historical backfill is not included unless the branch adds,
  validates, and documents that migration path explicitly

That keeps PR summaries and release notes aligned with the current rollout
truth instead of overstating migration completeness.

## Current Project Stage

The current versioning posture matches the actual project state:

- local-first AI video monitoring system
- advanced prototype moving toward pre-pilot
- still hardening operationally before broader pilot-style expectations
- current `0.6.1` work keeps the dual-backend stage intact while tightening
  maintainer-facing review guidance, routing, and harness confidence around it
- both PostgreSQL persistence paths remain explicit opt-in; session historical
  backfill is still a later rollout decision, not part of the current version
