What it is:
Short repo-aware summary of the current MCP/server direction.

What changed or What is happening:
The project is moving from a purely local-first desktop runtime toward a clearer MCP/server seam, while still keeping the current session, bridge, and contract model as the operational truth.

Why it matters:
This affects where future responsibilities should live and helps avoid mixing frontend bridge behavior, backend session lifecycle, and future service concerns too early.

Contract/lifecycle/operator impact:
Current session snapshot, bridge normalization, and lifecycle semantics should stay stable unless there is a deliberate coordinated contract change.

Next safest action:
Keep MCP/server changes explicit at the boundary, update the owning docs when contracts move, and avoid broad structural refactors until the new seam is proven.
