Parity surface:
- shared session-alert read behavior across the file-backed default store and the opt-in PostgreSQL store

What should stay the same:
- raw alert filtering, summary shaping, and grouped-incident read semantics
- store selection should not change alert-route contract behavior by itself
- FastAPI and MCP adapters should keep reading through the same shared alert backend

Main parity risk:
- the refactor may preserve one backend path while grouped incidents or bootstrap fallback drift on the other

Current confidence:
- focused parity tests already exist for the shared alert-store seam
- live Postgres confidence is still a stronger follow-up when the change touches real backend wiring

Best next check:
- run `tests/test_session_alert_store_parity.py` first
- if the change also touched adapters or route behavior, add the focused alert-query and FastAPI/MCP parity slices next
