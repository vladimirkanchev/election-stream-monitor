Validation target:
- remote HLS and real-media confidence for stream/file behavior that cannot be fully represented by tiny synthetic fixtures

Fixture reality:
- some coverage may rely on checked-in representative media, while other cases still depend on local-only or unstable upstream sources

Flaky or environment-sensitive risk:
- remote timing, socket availability, or upstream playlist drift can make failures look like product regressions when they are really lane or environment issues

Best confidence lane:
- keep deterministic checked-in fixture coverage in focused local or routine automated lanes
- route flaky remote-stream confidence into `just test-real-media`, a slower weekly path, or an explicit manual note

Best next cleanup:
- separate checked-in fixture cases from local-only or unstable-stream cases
- make docs and PR notes say exactly which real-media behavior this lane proves
