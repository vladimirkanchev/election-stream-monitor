Rollout surface:
- PostgreSQL session-store rollout across runtime config, detached workers, persisted reads, and optional live smoke confidence

Current rollout state:
- PostgreSQL is available as an explicit opt-in path, while the default runtime remains file-backed

Main rollout risks:
- schema ownership may still be unclear
- rollback may be underspecified if the branch needs to fall back to file-backed behavior
- parent and worker startup may disagree on backend state even when parity tests pass

Missing rollout evidence:
- a plain answer about whether backfill is required or whether the path is forward-only
- focused live-smoke evidence for the real database path, even if that smoke stays optional

Best next rollout check:
- document schema ownership and rollback behavior explicitly
- run the focused parity and runtime lanes first, then add or rerun optional live PostgreSQL smoke if the branch changed real rollout wiring
