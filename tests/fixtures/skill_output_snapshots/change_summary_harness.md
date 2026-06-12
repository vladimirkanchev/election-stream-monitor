What changed:
- added a repo-local developer harness with focused `just` commands
- aligned the root and maintainer docs with the new local validation entrypoints
- tightened the harness later by composing focused lanes and reducing duplication

Why it matters:
- local validation is easier to discover and run consistently
- the repo now has a clearer fast path for everyday checks and a better “ready to push” lane

Behavior impact:
- mostly behavior-preserving
- this changes developer workflow and validation ergonomics, not core product runtime behavior

Validation:
- focused docs and skill updates moved with the harness
- the change should still mention if live `just` execution was not verified in the current environment

Best concise framing:
- add a local developer harness and align docs around focused validation lanes
