Persistence surface:
- session-store runtime selection across FastAPI/service code, detached workers, and session snapshot reads

Default versus opt-in behavior:
- file-backed storage remains the default runtime path
- PostgreSQL-backed storage is supported as an explicit opt-in when config, adapter wiring, docs, and tests agree

Shared contract risk:
- metadata, latest progress, ordered results, cancel intent, missing-session reads, or snapshot shape may drift between the two backends
- parent and detached-worker backend agreement can break accepted-start then read behavior even when each backend passes in isolation

Current confidence:
- focused store-contract and parity tests already cover the shared session-store behavior
- runtime confidence is stronger when the branch also touches detached-worker startup or backend selection

Best next check:
- run `just test-session-store` first
- if runtime selection changed, follow with `just test-session-runtime`
