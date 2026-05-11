"""Module entrypoint for running the local MCP server with `python -m esm_mcp`.

Use this as the raw-checkout launch path when the editable-install console
script is not present or you intentionally want an explicit module entrypoint.
"""

from esm_mcp.server import main


if __name__ == "__main__":
    main()
