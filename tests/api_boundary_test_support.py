"""Small ASGI request helpers for FastAPI boundary tests.

The alert/auth/rate-limit adapter tests exercise the FastAPI app in-process
through HTTPX's ASGI transport. These helpers deliberately stay tiny:

- one async request helper that owns the transport setup
- one sync wrapper so the scenario files can read like plain HTTP examples

That keeps the route tests explicit without repeating low-value transport
boilerplate in every file.
"""

import asyncio

import httpx

from api.app import app


async def _request(
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json: dict[str, object] | None = None,
    content: bytes | None = None,
) -> httpx.Response:
    """Issue one in-process request, including raw bodies when needed."""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.request(
            method,
            path,
            json=json,
            content=content,
            headers=headers,
        )


def request(
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json: dict[str, object] | None = None,
    content: bytes | None = None,
) -> httpx.Response:
    """Synchronously issue one FastAPI request for boundary tests."""
    return asyncio.run(
        _request(method, path, headers=headers, json=json, content=content)
    )
