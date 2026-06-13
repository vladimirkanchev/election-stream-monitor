# Git Hooks

Keep Git hooks optional and cheap.

Current versioned hook:

- `scripts/git-hooks/pre-push`

Use it for one last local check before `git push`:

- inspect the commits being pushed, not only the current worktree
- run `just test-fast` before pushes that touch runtime, tests, frontend, or
  harness code
- run `just docs-check` before pushes that are docs/workflow-only
- skip broader lanes such as `ci-local`, weekly lanes, or full test suites

Install locally:

```bash
mkdir -p .git/hooks
cp scripts/git-hooks/pre-push .git/hooks/pre-push
chmod +x .git/hooks/pre-push
```

Keep this hook lightweight. If a branch needs deeper confidence, run
`just ci-local` or the slower focused lanes explicitly.
