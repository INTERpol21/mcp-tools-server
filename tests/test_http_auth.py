"""HTTP bearer gate: streamable-http requires a key; stdio never sees it.

The middleware is tested twice: in isolation against a trivial inner app
(exact 401 contract), and wrapped around the real streamable-HTTP app that
``build_http_app`` hands to uvicorn (an unauthenticated request must die at
the gate, an authenticated MCP ``initialize`` must reach the protocol).
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.core.auth import BearerAuthMiddleware, Receive, Scope, Send
from app.core.settings import Settings
from app.server import build_http_app, create_server

KEYS = frozenset({"sesame", "second-key"})


async def _inner_app(scope: Scope, receive: Receive, send: Send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _client(app: BearerAuthMiddleware) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


@pytest.fixture
def gated() -> BearerAuthMiddleware:
    return BearerAuthMiddleware(_inner_app, KEYS)


async def test_missing_header_is_401_with_www_authenticate(
    gated: BearerAuthMiddleware,
) -> None:
    async with _client(gated) as client:
        resp = await client.get("/anything")
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == "Bearer"
    assert "Bearer <key>" in resp.json()["error"]


async def test_wrong_key_is_401(gated: BearerAuthMiddleware) -> None:
    async with _client(gated) as client:
        resp = await client.get("/", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


async def test_non_bearer_scheme_is_401(gated: BearerAuthMiddleware) -> None:
    async with _client(gated) as client:
        resp = await client.get("/", headers={"Authorization": "Basic sesame"})
    assert resp.status_code == 401


async def test_valid_key_passes_through(gated: BearerAuthMiddleware) -> None:
    async with _client(gated) as client:
        resp = await client.get("/", headers={"Authorization": "Bearer sesame"})
    assert resp.status_code == 200
    assert resp.text == "ok"


async def test_any_configured_key_is_accepted(gated: BearerAuthMiddleware) -> None:
    async with _client(gated) as client:
        resp = await client.get("/", headers={"Authorization": "Bearer second-key"})
    assert resp.status_code == 200


async def test_scheme_is_case_insensitive(gated: BearerAuthMiddleware) -> None:
    async with _client(gated) as client:
        resp = await client.get("/", headers={"Authorization": "bearer sesame"})
    assert resp.status_code == 200


@pytest.fixture
def http_settings(tmp_path: Path) -> Settings:
    (tmp_path / "docs").mkdir()
    return Settings(data_dir=tmp_path, api_keys=frozenset({"sesame"}))


async def test_real_mcp_endpoint_rejects_unauthenticated(http_settings: Settings) -> None:
    app = build_http_app(create_server(http_settings), http_settings)
    async with _client(app) as client:
        resp = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert resp.status_code == 401


async def test_authenticated_initialize_reaches_the_protocol(
    http_settings: Settings,
) -> None:
    server = create_server(http_settings)
    app = build_http_app(server, http_settings)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "auth-test", "version": "0"},
        },
    }
    # The app's own lifespan (which starts the session manager) does not run
    # under ASGITransport, so start it explicitly, as uvicorn's lifespan would.
    async with server.session_manager.run():
        async with _client(app) as client:
            resp = await client.post(
                "/mcp",
                json=payload,
                headers={
                    "Authorization": "Bearer sesame",
                    "Accept": "application/json, text/event-stream",
                },
            )
    assert resp.status_code == 200
    assert "portfolio-tools" in resp.text
