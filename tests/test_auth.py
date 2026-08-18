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

from whatshot_mcp.auth import (
    BearerPassthroughAuthMiddleware,
    current_developer_api_key,
)
from whatshot_mcp.backend import BackendClient
from whatshot_mcp.contracts.v1 import BackendCapabilities
from whatshot_mcp.server import build_mcp_server, build_streamable_http_app


def _api_key(marker: str) -> str:
    return "wh_live_" + marker * 43


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


def _request(
    method: str = "tools/list",
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = dict(params or {})
    merged["_meta"] = {
        PROTOCOL_VERSION_META_KEY: LATEST_PROTOCOL_VERSION,
        CLIENT_CAPABILITIES_META_KEY: {},
    }
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": merged}


def _headers(
    token: str | None = None,
    *,
    scheme: str = "Bearer",
    method: str = "tools/list",
    name: str | None = None,
) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": LATEST_PROTOCOL_VERSION,
        "Mcp-Method": method,
    }
    if name is not None:
        headers["Mcp-Name"] = name
    if token is not None:
        headers["Authorization"] = f"{scheme} {token}"
    return headers


def test_bearer_passthrough_guards_http_and_never_logs_secret(caplog: Any) -> None:
    secret = _api_key("a")

    async def scenario() -> tuple[httpx.Response, ...]:
        backend = BackendClient("http://127.0.0.1:6690/api/v1")
        server = build_mcp_server(backend, _capabilities())
        app = build_streamable_http_app(server, bearer_passthrough=True)
        assert isinstance(app, BearerPassthroughAuthMiddleware)
        inner_app = app.app
        transport = httpx.ASGITransport(app=app)
        async with inner_app.router.lifespan_context(inner_app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8000"
            ) as client:
                missing = await client.post("/mcp", headers=_headers(), json=_request())
                old_static = await client.post(
                    "/mcp", headers=_headers("shared-static-token"), json=_request()
                )
                jwt = await client.post(
                    "/mcp",
                    headers=_headers("eyJhbGciOiJIUzI1NiJ9.payload.signature"),
                    json=_request(),
                )
                wrong_scheme = await client.post(
                    "/mcp",
                    headers=_headers(secret, scheme="ApiKey"),
                    json=_request(),
                )
                accepted = await client.post(
                    "/mcp", headers=_headers(secret), json=_request()
                )
                health = await client.get("/health")
                ready_without_key = await client.get("/ready")
                ready_with_key = await client.get(
                    "/ready", headers={"Authorization": f"Bearer {secret}"}
                )
        await backend.aclose()
        return (
            missing,
            old_static,
            jwt,
            wrong_scheme,
            accepted,
            health,
            ready_without_key,
            ready_with_key,
        )

    with caplog.at_level(logging.DEBUG):
        responses = asyncio.run(scenario())
    missing, old_static, jwt, wrong_scheme, accepted, health, ready_without, ready = (
        responses
    )
    assert all(
        response.status_code == 401
        for response in (missing, old_static, jwt, wrong_scheme, ready_without)
    )
    assert missing.headers["www-authenticate"] == "Bearer"
    assert missing.headers["cache-control"] == "no-store"
    assert accepted.status_code == 200
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    combined = "".join(response.text for response in responses) + caplog.text
    assert secret not in combined
    assert current_developer_api_key() is None


def test_duplicate_authorization_headers_are_rejected() -> None:
    async def scenario() -> httpx.Response:
        backend = BackendClient("http://127.0.0.1:6690/api/v1")
        server = build_mcp_server(backend, _capabilities())
        app = build_streamable_http_app(server, bearer_passthrough=True)
        inner_app = app.app  # type: ignore[attr-defined]
        transport = httpx.ASGITransport(app=app)
        headers = list(_headers().items()) + [
            ("Authorization", f"Bearer {_api_key('a')}"),
            ("Authorization", f"Bearer {_api_key('b')}"),
        ]
        async with inner_app.router.lifespan_context(inner_app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8000"
            ) as client:
                response = await client.post("/mcp", headers=headers, json=_request())
        await backend.aclose()
        return response

    assert asyncio.run(scenario()).status_code == 401


def test_public_host_must_be_explicitly_allowed() -> None:
    async def request(allowed_hosts: list[str] | None) -> httpx.Response:
        backend = BackendClient("http://127.0.0.1:6690/api/v1")
        server = build_mcp_server(backend, _capabilities())
        app = build_streamable_http_app(
            server,
            bearer_passthrough=True,
            allowed_hosts=allowed_hosts,
        )
        inner_app = app.app  # type: ignore[attr-defined]
        transport = httpx.ASGITransport(app=app)
        async with inner_app.router.lifespan_context(inner_app):
            async with httpx.AsyncClient(
                transport=transport,
                base_url="https://mcp.whatshot.top",
            ) as client:
                response = await client.post(
                    "/mcp",
                    headers=_headers(_api_key("a")),
                    json=_request(),
                )
        await backend.aclose()
        return response

    rejected = asyncio.run(request(None))
    accepted = asyncio.run(request(["mcp.whatshot.top"]))
    assert rejected.status_code == 421
    assert accepted.status_code == 200


def test_concurrent_requests_forward_their_own_api_key() -> None:
    first_key = _api_key("a")
    second_key = _api_key("b")
    seen_authorizations: list[str] = []

    async def backend_handler(request: httpx.Request) -> httpx.Response:
        authorization = request.headers["authorization"]
        await asyncio.sleep(0 if authorization.endswith("a") else 0.01)
        seen_authorizations.append(authorization)
        return httpx.Response(
            200,
            json={
                "data": {"sources": [], "nextCursor": None, "truncated": False},
                "meta": {"requestId": authorization[-1], "contractVersion": "1"},
            },
        )

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        backend = BackendClient(
            "http://127.0.0.1:6690/api/v1",
            api_key_provider=current_developer_api_key,
            transport=httpx.MockTransport(backend_handler),
        )
        server = build_mcp_server(backend, _capabilities())
        app = build_streamable_http_app(server, bearer_passthrough=True)
        inner_app = app.app  # type: ignore[attr-defined]
        transport = httpx.ASGITransport(app=app)

        async with inner_app.router.lifespan_context(inner_app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8000"
            ) as client:
                call = _request(
                    "tools/call",
                    {"name": "whatshot_list_sources", "arguments": {}},
                )
                first, second = await asyncio.gather(
                    client.post(
                        "/mcp",
                        headers=_headers(
                            first_key,
                            method="tools/call",
                            name="whatshot_list_sources",
                        ),
                        json=call,
                    ),
                    client.post(
                        "/mcp",
                        headers=_headers(
                            second_key,
                            method="tools/call",
                            name="whatshot_list_sources",
                        ),
                        json=call,
                    ),
                )
        await backend.aclose()
        return first, second

    first, second = asyncio.run(scenario())
    assert first.status_code == second.status_code == 200
    assert first.json()["result"]["isError"] is False
    assert second.json()["result"]["isError"] is False
    assert sorted(seen_authorizations) == sorted(
        [f"Bearer {first_key}", f"Bearer {second_key}"]
    )
    assert current_developer_api_key() is None
