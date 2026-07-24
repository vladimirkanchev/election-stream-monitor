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

- the selected local alert backend supplies the data; file-backed is the
  default and PostgreSQL remains explicit opt-in
- remote or authenticated MCP is a separate future boundary change, not an
  extension of FastAPI security work

The shared alert response semantics and backend-selection contract are owned
by [contracts.md](./contracts.md#session-alert-query-surfaces).

## Policy Gate For Future Changes

MCP remains local `stdio`, explicitly allowlisted, and read-only. Any mutation
tool or network-capable transport requires a separate security decision before
implementation. That decision must define the transport trust model,
authentication and authorization, request and result bounds, audit needs, and
error-redaction coverage. FastAPI protection is not inherited by MCP.

Local still means that the launched MCP client can read the selected runtime
backend's session-alert data. Treat client launch configuration as part of the
trusted local-process boundary.

`tests/test_mcp_server_contracts.py` locks the exact allowlist, schemas, and
stdio launch. `tests/test_mcp_fastapi_boundary_split.py` confirms every current
tool leaves persisted session data unchanged. The raw and grouped error suites
also lock the generic storage-error response.

## Current Tool Inventory

The server registers exactly these four tools. All are
`MCP-local-read-only`, use local `stdio` only, and call the active alert
backend through shared read models. File-backed storage remains the default;
PostgreSQL requires explicit runtime selection. MCP reads one backend and
never merges history across them.

| Tool | Returned data | Shared dependency | Response bound |
| --- | --- | --- | --- |
| `query_session_alerts` | Raw alert events | `session_alerts.filter_session_alert_events()` | Offset page: default 100, maximum 250 |
| `summarize_session_alerts` | Counts and time bounds | `session_alerts.summarize_session_alert_events()` | Compact summary |
| `query_session_alert_timeline` | Grouped incident entries | `session_alert_incidents.build_session_timeline()` | Offset page: default 100, maximum 250 |
| `summarize_session_alert_incidents` | Grouped counts and narrative | `session_alert_incidents.build_session_incident_summary()` | Compact summary |

Every shared query reads at most 5,000 stored rows and fails instead of
returning a partial result. Validation and missing-session errors remain
readable. Unexpected storage failures use `Alert storage is unavailable`, so
responses do not expose paths, driver detail, PostgreSQL URLs, or key values.
No tool starts, cancels, edits, deletes, or resolves playback. The exact
allowlist, schemas, and stdio launch are protected by
`tests/test_mcp_server_contracts.py`.

## Request Validation And Current Bounds

Every tool requires a string `session_id` and accepts the same optional
`detector_id`, enum `severity`, `start_time_utc`, and `end_time_utc` filters.
The tool schema trims outer whitespace and requires nonblank values. Session
and detector IDs are capped at 128 characters; timestamp filters are capped
at 64. The shared read-model service validates UTC timestamp format and
rejects an end time earlier than its start. Time-span caps remain deferred.

## Returned Data And Current Bounds

Raw queries return session IDs plus alert timestamps, detector IDs, titles,
messages, severities, source names, and optional window metadata. Timelines
return grouped timestamps, titles, source names, and one sample message.
Summaries return only counts, time bounds, and a grouped narrative. No tool
returns API keys, database URLs, session metadata, result payloads, or playback
paths, but alert messages and source names remain sensitive local monitoring
content.

Raw and timeline tools use the same `offset` and `limit` contract as FastAPI.
The 5,000-row ceiling bounds application/store work; it does not guarantee
that every future backend query scans no more than 5,000 rows. Backend-native
filtering and indexing can be strengthened as alert history grows.

## Deferred Hardening

Broader request/body-size and time-span caps remain bounded follow-ups before
any network transport is considered. Storage-error sanitization is implemented
for the current stdio boundary; no remote MCP, authentication infrastructure,
or mutation tool is introduced here.

## How To Run It

From the repo root:

```bash
. .venv/bin/activate
PYTHONPATH=src python -m esm_mcp
```

That starts the MCP server over `stdio`.

The installed `esm-mcp` command and `python -m esm_mcp` both delegate to the
same stdio entrypoint. Neither starts a FastAPI application or opens an HTTP
listener.

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
