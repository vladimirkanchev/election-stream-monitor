Drift summary:
- the local developer harness changed, but the current docs do not all agree on which file owns command details
- the root README is too broad in a couple of places, while the testing guide should own the fuller CI and lane explanation

Owning docs:
- `README.md` for the short developer harness overview
- `docs/README.md` for maintainer navigation toward the harness
- `docs/testing-and-validation.md` for the fuller lane and CI guidance

Recommended updates:
- keep the root README concise and point readers to the testing guide for deeper validation detail
- keep `docs/README.md` as the maintainer entry point for the harness
- update `docs/testing-and-validation.md` so the focused lanes remain the source of truth

Repetition to remove:
- repeated long command explanations copied into both the root README and maintainer docs
- duplicate wording that re-explains the same fast-versus-slow lane split in several places

Best next doc pass:
- make the smallest edits in the owning docs only
- reread the changed code or harness commands once more before broadening the docs pass
