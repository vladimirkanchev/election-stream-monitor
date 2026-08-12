# Contributing

Use this as the short human-contributor route for branch flow, setup, and
validation. [docs/README.md](./docs/README.md) routes maintainer and subsystem
work; [AGENTS.md](./AGENTS.md) is the AI-assisted entry point.

## Branch Flow

Use the workflow templates as one small flow:

1. Start with [docs/branch-purpose-template.md](./docs/branch-purpose-template.md).
2. Keep [.github/pull_request_template.md](./.github/pull_request_template.md) current.
3. Finish with [docs/merge-readiness-checklist.md](./docs/merge-readiness-checklist.md).

Move work to another branch when it grows beyond the stated purpose or reaches
an unrelated product/runtime seam. Reuse the branch template instead of
copying a planning checklist into task notes or PR descriptions.

Before implementation, ask whether an existing focused check already proves
the change, whether API/CLI/persisted-data/bridge contracts are affected, and
whether dependency metadata belongs in the branch story.

## Setup And Validation

Start a contributor environment with:

```bash
just setup
```

Use `just env-check` after setup or a toolchain change. Run the smallest honest
focused `just` recipe when the changed seam is clear; use `just test-fast` for
fast multi-seam runtime confidence, `just docs-check` for documentation or
workflow-only changes, and `just ci-local` before push or a routine PR.

[testing-and-validation.md](./docs/testing-and-validation.md) owns focused
recipes, validation depth, fixture handling, dependency checks, and the cases
where `manual confidence only for now` is the honest result.
[ci-maintainer-guide.md](./docs/ci-maintainer-guide.md) owns protected,
advisory, informational, and weekly CI semantics. Cheap local hygiene lives in
[`.pre-commit-config.yaml`](./.pre-commit-config.yaml) and the optional
[pre-push guide](./docs/git-hooks.md); it does not replace focused tests or
`just ci-local`.

## Documentation Responsibility

Update the closest owner when a behavior, contract, lifecycle, trust boundary,
or validation ownership changes. Keep summaries shorter than their owner and
link back instead of duplicating policy.

- [README.md](./README.md): product overview and normal runtime path.
- [docs/README.md](./docs/README.md): maintainer routing and document ownership.
- [docs/testing-and-validation.md](./docs/testing-and-validation.md): commands and validation lanes.
- [docs/development-environment-audit.md](./docs/development-environment-audit.md): prerequisites and optional local capabilities.
- [`.agents/skills/INVENTORY.md`](./.agents/skills/INVENTORY.md): repo-local AI-harness ownership.
