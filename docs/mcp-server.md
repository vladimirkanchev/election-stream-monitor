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

The server registers exactly these four tools. Each input schema requires a
string `session_id` and accepts optional `detector_id`, `severity`,
`start_time_utc`, and `end_time_utc` filters. The exact tool allowlist and
schema basics are protected by `tests/test_mcp_server_contracts.py`.

Every tool is read-only and reaches the active alert backend through its shared
read-model service. File-backed alert storage is the default; PostgreSQL is
used only after explicit runtime selection. MCP reads one selected backend and
does not discover or merge history from the other backend.

| Tool | Classification | Capability and returned data | Shared dependency | Result-size control | Error and secret exposure | Remote availability |
| --- | --- | --- | --- | --- | --- | --- |
| `query_session_alerts` | `MCP-local-read-only` | Read-only raw alert events for one session | `session_alerts.filter_session_alert_events()` | No pagination or result cap | Returns persisted alert content. Input errors are readable; storage errors use a safe generic message. | `disabled-remotely`; local `stdio` only |
| `summarize_session_alerts` | `MCP-local-read-only` | Read-only counts and time bounds for one session's alerts | `session_alerts.summarize_session_alert_events()` | Summary is compact; underlying selected alerts are scanned | Returns aggregate alert data. Input errors are readable; storage errors use a safe generic message. | `disabled-remotely`; local `stdio` only |
| `query_session_alert_timeline` | `MCP-local-read-only` | Read-only grouped incident entries for one session | `session_alert_incidents.build_session_timeline()` | No pagination or result cap | Returns persisted incident titles, messages, and sources. Input errors are readable; storage errors use a safe generic message. | `disabled-remotely`; local `stdio` only |
| `summarize_session_alert_incidents` | `MCP-local-read-only` | Read-only grouped incident counts and narrative summary | `session_alert_incidents.build_session_incident_summary()` | Summary is compact; underlying selected alerts are scanned | Returns aggregate incident data. Input errors are readable; storage errors use a safe generic message. | `disabled-remotely`; local `stdio` only |

No tool starts, cancels, edits, deletes, or resolves playback for a session.
Validation and missing-session errors remain readable. Unexpected storage
failures use `Alert storage is unavailable`, so tool responses do not expose
paths, driver detail, PostgreSQL URLs, or key values. A future networked MCP
transport still needs its own authentication, request and result bounds;
FastAPI `X-API-Key` checks and HTTP rate limiting do not apply to stdio.

## Request Validation And Current Bounds

Every tool requires a string `session_id` and accepts the same optional
`detector_id`, enum `severity`, `start_time_utc`, and `end_time_utc` filters.
The tool schema validates argument shape; the shared read-model service
validates UTC timestamp format and rejects an end time earlier than its start.
Input strings and time ranges have no maximum length or span yet.

## Returned Data And Current Bounds

Raw queries return session IDs plus alert timestamps, detector IDs, titles,
messages, severities, source names, and optional window metadata. Timelines
return grouped timestamps, titles, source names, and one sample message.
Summaries return only counts, time bounds, and a grouped narrative. No tool
returns API keys, database URLs, session metadata, result payloads, or playback
paths, but alert messages and source names remain sensitive local monitoring
content.

There is currently no pagination or result cap. Raw and timeline tools can
return every selected row; summaries are compact but scan the selected rows.
This is an explicit local-trust limitation, not resource-abuse protection.

## Deferred Hardening

Request length, time-span, pagination, and result caps remain a bounded
follow-up before any network transport is considered. Storage-error
sanitization is implemented for the current stdio boundary; no remote MCP,
authentication infrastructure, or mutation tool is introduced here.

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
