Persistence surface:
- shared session-alert reads across the file-backed default store and the
  opt-in PostgreSQL store

Default versus opt-in behavior:
- raw alert filtering, summary shaping, and grouped-incident reads stay
  consistent across backends
- store selection alone does not change the alert-route contract

Shared contract risk:
- grouped incidents, bootstrap fallback, or FastAPI/MCP adapters may drift on
  one backend while the other still passes
- auth and share-mode policy can change without changing the alert-store
  contract

Current confidence:
- focused parity tests cover the shared alert-store seam
- live PostgreSQL confidence is stronger when real backend wiring changes

Best next check:
- run `tests/test_session_alert_store_parity.py` first
- add focused alert-query and FastAPI/MCP slices when adapters or routes change
