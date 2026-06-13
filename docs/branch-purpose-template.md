# Branch Purpose Template

Use this at branch start or when scope starts to drift.
Keep it short. One clear sentence is better than a broad mini-spec.

## Template

```text
Branch purpose:
Improve __________________ without changing __________________.

In scope:
- 
- 

Out of scope:
- 
- 

Split trigger:
If this changes product/runtime behavior outside the stated scope, use another branch.
```

## Example

```text
Branch purpose:
Improve repeatable engineering workflow for this repo without changing core product behavior.

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
- If the sentence needs multiple `and` clauses, the branch is probably too broad.
- If a change only supports the stated goal, it likely belongs here.
- If it introduces unrelated product behavior, move it out.
