# Contributing

Use this file as the shortest maintainer and contributor entrypoint.

For the fuller maintainer map, use [docs/README.md](./docs/README.md).

## Branch Flow

Use the workflow templates as one small branch flow:

1. start with [docs/branch-purpose-template.md](./docs/branch-purpose-template.md)
2. keep the PR notes current with
   [.github/pull_request_template.md](./.github/pull_request_template.md)
3. finish with
   [docs/merge-readiness-checklist.md](./docs/merge-readiness-checklist.md)

If a change starts affecting product or runtime behavior outside the branch
purpose, move that work to another branch.

Keep the branch execution pattern light and reuse the short checklist in
[docs/branch-purpose-template.md](./docs/branch-purpose-template.md) instead of
copying it into each task or PR note.

That checklist now forces three useful questions early:

- what existing test or `docs-check` already proves the change?
- does the change also touch API, CLI, persisted data, or bridge shape?
- if `pyproject.toml` or `uv.lock` changed, does that belong to this branch story?

## Local Commands

Use the smallest honest lane first:

- `just setup`
  - recommended first-run setup for contributors and AI agents
- `just env-check`
  - environment readiness diagnostic after setup or toolchain changes
- focused lanes such as `just test-detectors`, `just test-alert-rules`, or
  `just test-hls`
  - use when the changed seam is already clear
- `just test-fast`
  - fast multi-seam runtime validation
- `just fixture-check`
  - use when the change touches fixture paths, shared metadata, docs, or
    environment assumptions
- `just dependency-check`
  - use when `pyproject.toml` or `uv.lock` changed and you want a cheap drift check
- `just ci-local`
  - use before push or PR for the closest fast local CI proxy

If no honest automated lane fits yet, say `manual confidence only for now` and
name the manual step plainly instead of pretending the change is fully covered.

Keep cheap hygiene in:

- [`.pre-commit-config.yaml`](./.pre-commit-config.yaml)
- [`scripts/git-hooks/pre-push`](./scripts/git-hooks/pre-push)
- [docs/git-hooks.md](./docs/git-hooks.md)
  - install notes for the optional push-time guard

Do not treat those as a replacement for `just test-fast` or `just ci-local`.

## Docs Ownership

Keep one clear owner per topic:

- [README.md](./README.md)
  - project and runtime overview
- [docs/README.md](./docs/README.md)
  - maintainer routing
- [docs/testing-and-validation.md](./docs/testing-and-validation.md)
  - validation lanes and CI shape
- [docs/development-environment-audit.md](./docs/development-environment-audit.md)
  - setup ownership, prerequisites, and optional local capabilities
- [`.agents/skills/`](./.agents/skills/)
  - repo-local skill behavior only

If a note starts duplicating an owning doc, shorten it and point back to that
owner instead.
