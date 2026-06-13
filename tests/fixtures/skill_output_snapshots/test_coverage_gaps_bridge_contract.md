Gap:
Bridge contract drift is not fully protected for the changed request or response shape.

Why it matters:
The frontend, bridge normalization layer, backend schemas, and docs can silently diverge even when nearby code still compiles.

Best test layer:
Contract-focused backend and frontend boundary tests close to the existing bridge and API schema suites.

Recommended lane:
Fast lane through the nearby contract and bridge suites, because the change is structural and should stay cheap to validate on ordinary branch work.

Cheapest useful test:
Extend the nearby contract tests to assert the changed field shape and add one regression covering the normalized transport result seen by the frontend.
