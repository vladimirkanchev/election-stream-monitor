Branch story:
- developer productivity and workflow hardening without changing core product behavior

Recommended commit shape:
- one commit for the main harness or skill feature
- one commit for aligned docs
- one small cleanup or refactor commit only if it is meaningfully separate

Recommended PR shape:
- one PR if the branch still tells one coherent workflow story
- split only if dependency drift or unrelated product behavior changes are mixed in

What should stay out:
- unrelated dependency metadata churn
- local-only research assets or notes
- runtime or detector behavior changes that belong to a different branch story

Best next step:
- inspect the remaining changed files
- group them by change story, not by file count
- then commit the branch in the smallest readable structure
