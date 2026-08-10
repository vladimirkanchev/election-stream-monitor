Most likely root cause:
GitHub merge-state or branch-protection evaluation remained blocked even though the visible CI checks were green.

Confidence:
Medium-high, because the symptom matches a protected-merge or stale status-reconciliation problem more than a failing code path.

Evidence for it:
The PR was green, mergeable in principle, and the remaining symptom lived at the policy or merge-state layer rather than inside the repo runtime.

Evidence against it:
If a required status context was actually missing or mismatched on the latest head SHA, the blocker would be a real CI contract issue rather than stale merge evaluation.

Cheapest next validation:
Check the current required merge gate and compare it directly with the latest reported status contexts on the PR head.
