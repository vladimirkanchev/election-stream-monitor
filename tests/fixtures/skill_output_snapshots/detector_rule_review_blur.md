Findings:
- no immediate production regression is obvious from the blur-rule refactor
- the strongest remaining risk is missing focused confidence if the warm-up or recovery path changed

Boundary assessment:
- the change still looks production-runtime shaped rather than detector-lab shaped
- detector scoring and alert entry logic remain in the expected production seams

Missing confidence:
- confirm the nearest focused alert-rule lane still covers the changed blur behavior
- add or adjust a focused production rule test only if the entry, suppression, or recovery semantics changed

Suggested follow-up:
- run `just test-alert-rules`
- if the change also touched detector facts or processor wiring, widen to `just test-fast`
