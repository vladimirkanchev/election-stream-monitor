Branch purpose:
- keep the branch focused on one coherent change story without changing core product behavior outside that scope

Drift assessment:
- medium drift
- the branch started around one detector/runtime theme but now also carries workflow and detector-lab follow-up work

Most likely branch shape:
- one parent runtime branch plus one child detector-lab or workflow branch
- the current diff looks more like stacked PR work than one clean review unit

Recommended PR shape:
- PR 1 for the lower-level runtime or contract change
- PR 2 for the dependent detector-lab or workflow layer
- keep unrelated dependency churn out unless it is required by the feature

Merged-vs-main state:
- check whether the parent branch content is already in `main` before merging anything else
- if the top branch already matches `main`, do cleanup instead of opening another merge

Safe cleanup actions:
- run `just branch-cleanup`
- compare `main..branch` or `git diff --stat main..branch`
- delete branches only after confirming they are merged or intentionally abandoned

Best next step:
- verify the parent-child merge order
- retarget or close redundant PRs
- then delete stale local and remote branches that no longer hold unique work
