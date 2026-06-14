# Branch Purpose Template

Use this at branch start or when scope starts to drift.
Keep it short. One clear sentence is better than a broad mini-spec.
This file owns the lightweight execution pattern and the medium-task checklist.

## Template

```text
Branch purpose:
Improve __________________ without changing __________________.

Execution pattern:
Protect behavior first, change one boundary at a time, update tests with the change, run the smallest honest validation lane, align docs and harness only if ownership changed.

In scope:
- 
- 

Out of scope:
- 
- 

Split trigger:
If this changes product/runtime behavior outside the stated scope, use another branch.
```

## Short Checklist

Use this when the task is moderate but does not need a full plan.

```text
1. What boundary changes?
2. What behavior must stay the same?
3. What existing test or docs-check proves this change?
4. If none, is one focused test worth adding?
5. What smallest validation command should run?
6. Any docs or harness update needed?
7. Still inside branch scope?
```

## Example

```text
Branch purpose:
Improve repeatable engineering workflow for this repo without changing core product behavior.

Execution pattern:
Protect behavior first, change one boundary at a time, update tests with the change, run the smallest honest validation lane, align docs and harness only if ownership changed.

In scope:
- local validation harness commands
- repo-local AI skills and their deterministic tests
- maintainer docs for workflow, validation, and review support

Out of scope:
- detector or alert-rule behavior changes
- frontend feature work
- runtime backend feature work

Split trigger:
If this changes product/runtime behavior outside the stated scope, use another branch.
```

## When To Use It

- branch creation
- PR description setup
- sanity check before adding new work
- deciding whether a follow-up fix still belongs in the same branch

## Notes

- Prefer one branch purpose sentence, not a list of half-purposes.
- Keep the execution pattern lightweight. It is a working rhythm, not a second plan.
- If the sentence needs multiple `and` clauses, the branch is probably too broad.
- If a change only supports the stated goal, it likely belongs here.
- If it introduces unrelated product behavior, move it out.
