Findings:
- the polling hook change is readable overall, but some retry-state wording now depends on bridge-shaped details that may belong lower

Ownership assessment:
- renderer hook state is the right owner for visible loading and retry state
- bridge normalization should stay responsible for transport and snapshot-shape cleanup
- backend session semantics should not be reinterpreted in the React layer

UI/runtime impact:
- operator-facing polling text could drift if the hook starts inferring too much from raw transport details
- the first visible regression would likely be incorrect status-panel wording or a premature idle fallback

Missing confidence:
- one focused frontend checkpoint or hook-level polling test would give better confidence than a broad suite rerun
- a small manual smoke pass is still useful if the wording change is operator-visible

Suggested follow-up:
- run `just test-frontend`
- if the change is still user-visible after that, use `manual-validation-planner` for one short desktop smoke path
