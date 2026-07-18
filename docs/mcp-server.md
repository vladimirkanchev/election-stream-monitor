# MCP Server

The project includes a small local MCP server for read-only alert queries.

## What It Is

The current MCP server:

- runs locally over `stdio`
- is read-only and query-only
- reads persisted local alert and session data
- reads through the same shared alert/session services used by the local
  FastAPI boundary
- stays outside FastAPI auth and rate limiting

It is meant for local MCP clients and coding agents, not for browser or HTTP
access.

In the shared
[security classification vocabulary](./fastapi-boundary.md#security-classification-vocabulary),
this is an `MCP-local-read-only` and `disabled-remotely` surface.

This document owns the MCP transport and tool-policy details. The FastAPI
route, run-mode, and share-mode matrix belongs in
[fastapi-boundary.md](./fastapi-boundary.md#policy-and-regression-ownership).

Today that also means:

- file-backed alerts remain the default backend
- PostgreSQL-backed alerts can back the same read surface when explicitly
  enabled for the local runtime
- moving to a remote/authenticated MCP transport would be a later boundary
  change, not an implied side effect of the current FastAPI security work

## Current Tool Inventory

The server registers exactly these four tools. Each input schema requires a
string `session_id` and accepts optional `detector_id`, `severity`,
`start_time_utc`, and `end_time_utc` filters. The exact tool allowlist and
schema basics are protected by `tests/test_mcp_server_contracts.py`.

| Tool | Classification | Capability and returned data | Shared dependency | Result-size control | Error and secret exposure | Remote availability |
| --- | --- | --- | --- | --- | --- | --- |
| `query_session_alerts` | `MCP-local-read-only` | Read-only raw alert events for one session | `session_alerts.filter_session_alert_events()` | No pagination or result cap | Returns persisted alert content. Known-session, filter, and storage failures become readable tool errors; keys and environment settings are not read or returned. | `disabled-remotely`; local `stdio` only |
| `summarize_session_alerts` | `MCP-local-read-only` | Read-only counts and time bounds for one session's alerts | `session_alerts.summarize_session_alert_events()` | Summary is compact; underlying selected alerts are scanned | Returns aggregate alert data. Validation or storage failures become readable tool errors; keys and environment settings are not read or returned. | `disabled-remotely`; local `stdio` only |
| `query_session_alert_timeline` | `MCP-local-read-only` | Read-only grouped incident entries for one session | `session_alert_incidents.build_session_timeline()` | No pagination or result cap | Returns persisted incident titles, messages, and sources. Validation or storage failures become readable tool errors; keys and environment settings are not read or returned. | `disabled-remotely`; local `stdio` only |
| `summarize_session_alert_incidents` | `MCP-local-read-only` | Read-only grouped incident counts and narrative summary | `session_alert_incidents.build_session_incident_summary()` | Summary is compact; underlying selected alerts are scanned | Returns aggregate incident data. Validation or storage failures become readable tool errors; keys and environment settings are not read or returned. | `disabled-remotely`; local `stdio` only |

No tool starts, cancels, edits, deletes, or resolves playback for a session.
The tool layer deliberately passes user-facing validation and storage-failure
text through as MCP tool errors. That is suitable only for the current
local-trust process boundary. A future networked MCP transport must add its
own authentication, request and result bounds, and reviewed error-sanitization
policy; FastAPI `X-API-Key` checks and HTTP rate limiting do not apply to it.

## How To Run It

From the repo root:

```bash
. .venv/bin/activate
PYTHONPATH=src python -m esm_mcp
```

That starts the MCP server over `stdio`.

## How To Connect

Use an MCP client that can launch a local command. Point it at:

```bash
python -m esm_mcp
```

with:

- working directory: this repository
- environment: `PYTHONPATH=src`

There is no browser URL, no HTTP port, and no `X-API-Key` header for the
current MCP server.

## What It Is Good For

Use it when you want a local MCP client or coding agent to query:

- raw session alerts
- alert summaries
- grouped incident timeline
- grouped incident summary

## Related Files

- [../src/esm_mcp/server.py](../src/esm_mcp/server.py)
- [../src/esm_mcp/alert_tools.py](../src/esm_mcp/alert_tools.py)
- [architecture.md](./architecture.md)
- [contracts.md](./contracts.md)
