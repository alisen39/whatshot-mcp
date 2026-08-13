from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from mcp_types import (
    CLIENT_CAPABILITIES_META_KEY,
    LATEST_PROTOCOL_VERSION,
    PROTOCOL_VERSION_META_KEY,
)

from whats_hot_mcp.contracts.v1 import BackendCapabilities
from whats_hot_mcp.server import (
    StaticBearerAuthMiddleware,
    build_mcp_server,
    build_streamable_http_app,
)


class StubBackend:
    async def aclose(self) -> None:
        return None


def _capabilities() -> BackendCapabilities:
    return BackendCapabilities.model_validate(
        {
            "backend": {"name": "stub", "version": "1"},
            "boardKeyVersion": 1,
            "profiles": ["core-read"],
            "features": {
                "sources": True,
                "sourceSchema": True,
                "current": True,
                "kinds": ["hotlist"],
            },
        }
    )


def _request() -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {
            "_meta": {
                PROTOCOL_VERSION_META_KEY: LATEST_PROTOCOL_VERSION,
                CLIENT_CAPABILITIES_META_KEY: {},
            }
        },
    }


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": LATEST_PROTOCOL_VERSION,
        "Mcp-Method": "tools/list",
    }
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def test_static_token_guards_streamable_http_and_never_logs_secret(
    caplog: Any,
) -> None:
    secret = "extremely-secret-inbound-token"

    async def scenario() -> tuple[
        httpx.Response,
        httpx.Response,
        httpx.Response,
        httpx.Response,
        httpx.Response,
    ]:
        server = build_mcp_server(  # type: ignore[arg-type]
            StubBackend(), _capabilities()
        )
        app = build_streamable_http_app(server, inbound_token=secret)
        assert isinstance(app, StaticBearerAuthMiddleware)
        inner_app = app.app
        transport = httpx.ASGITransport(app=app)
        async with inner_app.router.lifespan_context(inner_app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8000"
            ) as client:
                missing = await client.post("/mcp", headers=_headers(), json=_request())
                wrong = await client.post(
                    "/mcp", headers=_headers("wrong-token"), json=_request()
                )
                accepted = await client.post(
                    "/mcp", headers=_headers(secret), json=_request()
                )
                health = await client.get("/health")
                ready_without_token = await client.get("/ready")
        return missing, wrong, accepted, health, ready_without_token

    with caplog.at_level(logging.DEBUG):
        missing, wrong, accepted, health, ready_without_token = asyncio.run(scenario())
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert accepted.status_code == 200
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready_without_token.status_code == 401
    combined = missing.text + wrong.text + accepted.text + caplog.text
    assert secret not in combined
    assert "whatshot.invalid" not in combined
