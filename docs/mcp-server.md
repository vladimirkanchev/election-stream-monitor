# MCP Server

The project includes a small local MCP server for read-only alert queries.

## What It Is

The current MCP server:

- runs locally over `stdio`
- is read-only and query-only
- reads persisted local alert and session data
- stays outside FastAPI auth and rate limiting

It is meant for local MCP clients and coding agents, not for browser or HTTP
access.

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
