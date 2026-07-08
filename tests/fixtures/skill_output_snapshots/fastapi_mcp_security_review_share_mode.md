Security surface:
- FastAPI routes and MCP tooling that both touch session or alert data, but through different trust paths

Current protection:
- FastAPI `share` mode uses auth and rate limiting on the intended exposed HTTP path
- MCP stays a local `stdio` tool surface with narrower read-oriented expectations

Checklist gaps:
- confirm the branch did not widen `share` mode outside the intended demo boundary
- confirm MCP tool scope, secret/config handling, and dependency exposure still match the repo's local-first stage

Best next hardening step:
- tighten the narrowest exposed boundary that changed instead of broadening security claims across the whole repo
- keep docs explicit about which protections are `share`-only versus always-on local behavior

Best validation lane:
- run the focused FastAPI or MCP tests nearest the changed route or tool
- if the branch also changed policy wording or CI expectations, follow with the relevant docs or workflow check
