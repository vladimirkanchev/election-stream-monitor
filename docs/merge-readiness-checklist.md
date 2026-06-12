# Merge / Readiness Checklist

Use this near the end of a branch or PR, after the main implementation is done.
Keep it practical. This is a final guard, not a second planning document.

## Checklist

- [ ] focused validation is done for the changed seam
- [ ] broader validation is run only if the change really needs it
- [ ] docs are aligned if the change moved workflow, behavior, contracts, or ownership
- [ ] fixture and environment assumptions are checked
- [ ] branch purpose still matches the actual content
- [ ] unrelated files, local notes, or dependency drift are excluded
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

### Docs aligned if needed

Check whether the change should update:

- root `README.md`
- `docs/README.md`
- `docs/testing-and-validation.md`
- subsystem docs under `docs/`
- code docstrings

### Fixture / environment assumptions checked

Confirm:

- tests do not rely on local-only research assets unless explicitly intended
- socket, tool, or runtime assumptions are still honest
- any manual-only confidence step is stated plainly

### Branch shape still coherent

Ask:

- does this branch still tell one clear story?
- should any unrelated follow-up move to another branch?
- is the stacked-branch or merged-vs-main state still understood?

### Unrelated files excluded

Check for:

- stray dependency metadata changes
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
