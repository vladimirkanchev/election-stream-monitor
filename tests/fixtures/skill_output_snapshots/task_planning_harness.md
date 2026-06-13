Task:
- add a repo-local CI failure triage skill for the developer productivity harness branch

Importance:
- 9/10

Urgency:
- 8/10

Scope:
- 4/10

Complexity:
- 4/10

Why it matters now:
- CI debugging and branch workflow friction are already real costs in this repo
- the skill improves repeatable workflow without changing core product behavior

Recommended phase:
- near-term branch work
- it fits well after the command harness and before broader optional skill expansion

Best next step:
- add one concrete repo-local skill with deterministic tests and one snapshot fixture
- keep the first version narrow around failure classification and smallest-lane reproduction
