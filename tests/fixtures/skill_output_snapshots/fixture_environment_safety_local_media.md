Risk summary:
- the test appears to rely on local-only media inputs that are not guaranteed in CI

Environment dependency:
- baseline clips from a local research folder rather than a checked-in fixture set

CI safety assessment:
- not safe for the fast default CI lane as written
- either the test should use committed fixtures, or the local-only path should stay outside CI expectations

Best fix shape:
- keep the local research folder ignored
- update the test to use committed fixture inputs or to treat the local-only asset as optional
- if the coverage is still valuable, move it into a slower confidence or manual-only lane

Cheapest validation:
- rerun the focused local test with the committed fixture set only
- then use the relevant detector-lab lane instead of assuming the research folder exists everywhere
