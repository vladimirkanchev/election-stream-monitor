# Merge / Readiness Checklist

Use this near the end of a branch or PR, after the main implementation is done.
Keep it practical. This is a final guard, not a second planning document.

## Checklist

- [ ] focused validation is done for the changed seam
- [ ] the PR notes list the actual commands that were run
- [ ] broader validation was added only when the change needed it
- [ ] docs impact and fixture/environment impact are both stated explicitly
- [ ] docs are aligned if workflow, behavior, contracts, or ownership moved
- [ ] any `pyproject.toml` or `uv.lock` change is intentional and explained
- [ ] branch purpose still matches the actual content
- [ ] unrelated files, local notes, generated noise, and stray dependency drift are excluded
- [ ] merge, retarget, or delete actions are safe for the current branch state

## Decision Points

### Focused validation done

- Prefer the smallest honest lane first:
  - `just test-detectors`
  - `just test-processor`
  - `just test-alert-rules`
  - `just test-hls`
  - `just test-frontend`
  - `just test-detector-lab`
  - `just test-real-media`
  - `just docs-check`
  - `just fixture-check`
- Use `just ci-local` as the main local push-readiness lane, not the first answer.
- Treat `pre-commit` as cheap hygiene, not as proof that the branch is ready.
- Make sure the PR notes list the exact commands that were run, not only the lane category.

### Docs aligned if needed

Check whether the change should update:

- root `README.md`
- `docs/README.md`
- `docs/testing-and-validation.md`
- subsystem docs under `docs/`
- code docstrings

### Fixture / environment assumptions checked

Confirm tests do not quietly rely on local-only research assets, optional
tools, sockets, or machine-specific runtime assumptions. State any manual-only
confidence step plainly.

### Branch shape still coherent

Ask:

- does this branch still tell one clear story?
- should any unrelated follow-up move to another branch?
- is the stacked-branch or merged-vs-main state still understood?

### Unrelated files excluded

Check for:

- stray dependency metadata changes
- `pyproject.toml` or `uv.lock` changes that are present but not explained
- commit messages that no longer match the actual change grouped in the commit
- local notes
- generated noise
- fixture data that is not meant to be committed

### Safe to merge / delete / retarget

Confirm:

- branches with unique commits are not deleted blindly
- merged content is really in the intended base branch
- retargeting or stacked merge order is still correct

## Use With

Use this together with:

- [branch-purpose-template.md](./branch-purpose-template.md)
- [`.github/pull_request_template.md`](../.github/pull_request_template.md)
- `just branch-cleanup`
