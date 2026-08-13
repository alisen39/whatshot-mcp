from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
from mcp_types import (
    CLIENT_CAPABILITIES_META_KEY,
    LATEST_PROTOCOL_VERSION,
    PROTOCOL_VERSION_META_KEY,
)

from whats_hot_mcp.contracts.v1 import (
    BackendCapabilities,
    CategoryCurrentData,
    CurrentData,
    ItemKind,
    NavigationData,
    SourceMode,
)
from whats_hot_mcp.errors import UnsupportedCapability
from whats_hot_mcp.server import build_mcp_server, build_streamable_http_app

EXPECTED_NAMES = [
    "whatshot_analyze_hot_event",
    "whatshot_analyze_newsflash_coverage",
    "whatshot_get_capabilities",
    "whatshot_get_current",
    "whatshot_get_current_batch",
    "whatshot_get_data_coverage",
    "whatshot_get_source_schema",
    "whatshot_get_trend_series",
    "whatshot_list_sources",
    "whatshot_query_history",
    "whatshot_search_history",
]

CORE_ONLY_NAMES = [
    "whatshot_get_capabilities",
    "whatshot_get_current",
    "whatshot_get_source_schema",
    "whatshot_list_sources",
]

CLOUD_NAMES = sorted(
    EXPECTED_NAMES + ["whatshot_fetch_category_hotlists", "whatshot_list_navigation"]
)


class StubBackend:
    async def get_capabilities(self) -> BackendCapabilities:
        return BackendCapabilities.model_validate(
            {
                "backend": {"name": "stub", "version": "1"},
                "boardKeyVersion": 1,
                "profiles": ["core-read"],
                "features": {
                    "sources": True,
                    "sourceSchema": True,
                    "current": True,
                    "liveFetch": False,
                    "batchCurrent": False,
                    "history": False,
                    "historySearch": False,
                    "trendSeries": False,
                    "coverage": False,
                    "navigation": False,
                    "semanticSearch": False,
                    "kinds": ["hotlist"],
                },
            }
        )

    async def get_current_batch(self, _request: object) -> object:
        raise UnsupportedCapability("batchCurrent")

    async def query_history(self, _request: object) -> object:
        raise UnsupportedCapability("history")

    async def search_history(self, _request: object) -> object:
        raise UnsupportedCapability("historySearch")

    async def aclose(self) -> None:
        return None


class FullStubBackend(StubBackend):
    async def get_capabilities(self) -> BackendCapabilities:
        return BackendCapabilities.model_validate(
            {
                "backend": {"name": "stub", "version": "1"},
                "boardKeyVersion": 1,
                "profiles": ["core-read", "history-read"],
                "features": {
                    "sources": True,
                    "sourceSchema": True,
                    "current": True,
                    "batchCurrent": True,
                    "history": True,
                    "historySearch": True,
                    "trendSeries": True,
                    "coverage": True,
                    "kinds": ["hotlist", "newsflash"],
                },
            }
        )


class CurrentRecordingBackend(FullStubBackend):
    def __init__(self) -> None:
        self.current_calls: list[object] = []

    async def get_current(self, request: object) -> CurrentData:
        self.current_calls.append(request)
        now = datetime(2026, 8, 13, tzinfo=UTC)
        return CurrentData(
            site=request.site,  # type: ignore[attr-defined]
            board_key=request.board_key or "hot",  # type: ignore[attr-defined]
            kind=ItemKind.HOTLIST,
            title="Example",
            update_time=now,
            observed_at=now,
            source_mode=SourceMode.LIVE,
            items=[],
        )


class NavigationStubBackend(FullStubBackend):
    def __init__(self) -> None:
        self.navigation_calls: list[object] = []
        self.category_calls: list[object] = []

    async def get_capabilities(self) -> BackendCapabilities:
        capabilities = await super().get_capabilities()
        return capabilities.model_copy(
            update={
                "features": capabilities.features.model_copy(
                    update={"navigation": True}
                )
            }
        )

    async def list_navigation(self, query: object) -> NavigationData:
        self.navigation_calls.append(query)
        return NavigationData.model_validate(
            {
                "entries": [
                    {
                        "category": "tech",
                        "categoryTitle": "科技",
                        "site": "github",
                        "siteTitle": "GitHub",
                        "kinds": ["hotlist"],
                        "boardCount": 1,
                    }
                ],
                "nextCursor": None,
                "truncated": False,
            }
        )

    async def fetch_category_hotlists(self, request: object) -> CategoryCurrentData:
        self.category_calls.append(request)
        return CategoryCurrentData(
            category="tech", results=[], errors=[], truncated=False
        )


def _modern_request(
    method: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = dict(params or {})
    merged["_meta"] = {
        PROTOCOL_VERSION_META_KEY: LATEST_PROTOCOL_VERSION,
        CLIENT_CAPABILITIES_META_KEY: {},
    }
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": merged}


def _modern_headers(method: str, *, name: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": LATEST_PROTOCOL_VERSION,
        "Mcp-Method": method,
    }
    if name is not None:
        headers["Mcp-Name"] = name
    return headers


def test_public_mcpserver_catalog_is_frozen_from_deployment_capabilities() -> None:
    async def scenario() -> None:
        backend = StubBackend()
        server = build_mcp_server(  # type: ignore[arg-type]
            backend, await backend.get_capabilities()
        )
        tools = await server.list_tools()
        assert [tool.name for tool in tools] == CORE_ONLY_NAMES
        assert all(
            tool.annotations and tool.annotations.read_only_hint for tool in tools
        )
        assert all(
            tool.meta and tool.meta["top.whatshot/catalogHash"] == server.catalog_hash
            for tool in tools
        )
        assert all(
            tool.meta and "top.whatshot/requiredScopes" in tool.meta for tool in tools
        )

    asyncio.run(scenario())


def test_modern_streamable_http_single_post_and_cache_headers() -> None:
    async def scenario() -> None:
        backend = FullStubBackend()
        server = build_mcp_server(  # type: ignore[arg-type]
            backend, await backend.get_capabilities()
        )
        app = server.streamable_http_app(
            streamable_http_path="/mcp",
            json_response=True,
            stateless_http=True,
        )
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8000"
            ) as client:
                response = await client.post(
                    "/mcp",
                    headers=_modern_headers("tools/list"),
                    json=_modern_request("tools/list"),
                )
                unsupported = await client.post(
                    "/mcp",
                    headers=_modern_headers(
                        "tools/call", name="whatshot_get_current_batch"
                    ),
                    json=_modern_request(
                        "tools/call",
                        {
                            "name": "whatshot_get_current_batch",
                            "arguments": {"targets": [{"site": "weibo"}]},
                        },
                    ),
                )
                unsupported_history = await client.post(
                    "/mcp",
                    headers=_modern_headers(
                        "tools/call", name="whatshot_query_history"
                    ),
                    json=_modern_request(
                        "tools/call",
                        {
                            "name": "whatshot_query_history",
                            "arguments": {"cursor": "opaque+/= cursor"},
                        },
                    ),
                )
                unsupported_analysis = await client.post(
                    "/mcp",
                    headers=_modern_headers(
                        "tools/call", name="whatshot_analyze_hot_event"
                    ),
                    json=_modern_request(
                        "tools/call",
                        {
                            "name": "whatshot_analyze_hot_event",
                            "arguments": {"keyword": "ACME", "scanBudget": 10},
                        },
                    ),
                )
        assert response.status_code == 200
        assert "mcp-session-id" not in response.headers
        result = response.json()["result"]
        assert [tool["name"] for tool in result["tools"]] == EXPECTED_NAMES
        assert result["ttlMs"] == 300_000
        assert result["cacheScope"] == "public"
        assert result["_meta"]["top.whatshot/catalogHash"] == server.catalog_hash
        assert unsupported.status_code == 200
        unsupported_result = unsupported.json()["result"]
        assert unsupported_result["isError"] is True
        assert "CAPABILITY_UNAVAILABLE" in unsupported_result["content"][0]["text"]
        assert unsupported_history.status_code == 200
        history_result = unsupported_history.json()["result"]
        assert history_result["isError"] is True
        assert "CAPABILITY_UNAVAILABLE" in history_result["content"][0]["text"]
        assert unsupported_analysis.status_code == 200
        analysis_result = unsupported_analysis.json()["result"]
        assert analysis_result["isError"] is True
        assert "CAPABILITY_UNAVAILABLE" in analysis_result["content"][0]["text"]

    asyncio.run(scenario())


def test_cloud_navigation_tools_follow_capabilities_snapshot() -> None:
    async def scenario() -> None:
        backend = NavigationStubBackend()
        server = build_mcp_server(  # type: ignore[arg-type]
            backend, await backend.get_capabilities()
        )
        app = server.streamable_http_app(
            streamable_http_path="/mcp",
            json_response=True,
            stateless_http=True,
        )
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8000"
            ) as client:
                listed = await client.post(
                    "/mcp",
                    headers=_modern_headers("tools/list"),
                    json=_modern_request("tools/list"),
                )
                navigation = await client.post(
                    "/mcp",
                    headers=_modern_headers(
                        "tools/call", name="whatshot_list_navigation"
                    ),
                    json=_modern_request(
                        "tools/call",
                        {
                            "name": "whatshot_list_navigation",
                            "arguments": {"category": "tech", "limit": 1},
                        },
                    ),
                )
                category = await client.post(
                    "/mcp",
                    headers=_modern_headers(
                        "tools/call", name="whatshot_fetch_category_hotlists"
                    ),
                    json=_modern_request(
                        "tools/call",
                        {
                            "name": "whatshot_fetch_category_hotlists",
                            "arguments": {
                                "category": "tech",
                                "freshness": "prefer_cache",
                                "limitSites": 1,
                                "limitPerBoard": 1,
                            },
                        },
                    ),
                )

        tools = listed.json()["result"]["tools"]
        assert [tool["name"] for tool in tools] == CLOUD_NAMES
        cloud_tools = {
            tool["name"]: tool
            for tool in tools
            if tool["name"]
            in {"whatshot_fetch_category_hotlists", "whatshot_list_navigation"}
        }
        assert all(
            tool["_meta"]["top.whatshot/toolAvailability"] == "cloud"
            for tool in cloud_tools.values()
        )
        assert all(
            tool["_meta"]["top.whatshot/requiredScopes"] == ["data:read"]
            for tool in cloud_tools.values()
        )
        category_properties = cloud_tools["whatshot_fetch_category_hotlists"][
            "inputSchema"
        ]["properties"]
        assert category_properties["limitSites"]["maximum"] == 50
        assert category_properties["limitPerBoard"]["default"] == 10
        navigation_properties = cloud_tools["whatshot_list_navigation"]["inputSchema"][
            "properties"
        ]
        assert navigation_properties["limit"]["maximum"] == 200
        assert navigation.json()["result"]["isError"] is False
        assert category.json()["result"]["isError"] is False
        assert len(backend.navigation_calls) == 1
        assert len(backend.category_calls) == 1
        assert backend.category_calls[0].limit_sites == 1  # type: ignore[attr-defined]
        assert backend.category_calls[0].limit_per_board == 1  # type: ignore[attr-defined]

    asyncio.run(scenario())


def test_universal_tool_schema_is_strict_camel_case_and_forwards_board_key() -> None:
    async def scenario() -> None:
        backend = CurrentRecordingBackend()
        server = build_mcp_server(  # type: ignore[arg-type]
            backend, await backend.get_capabilities()
        )
        app = server.streamable_http_app(
            streamable_http_path="/mcp",
            json_response=True,
            stateless_http=True,
        )
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8000"
            ) as client:
                listed = await client.post(
                    "/mcp",
                    headers=_modern_headers("tools/list"),
                    json=_modern_request("tools/list"),
                )
                correct = await client.post(
                    "/mcp",
                    headers=_modern_headers(
                        "tools/call", name="whatshot_get_current"
                    ),
                    json=_modern_request(
                        "tools/call",
                        {
                            "name": "whatshot_get_current",
                            "arguments": {
                                "site": "bilibili",
                                "boardKey": "type=181",
                                "limit": 1,
                            },
                        },
                    ),
                )
                snake_case = await client.post(
                    "/mcp",
                    headers=_modern_headers(
                        "tools/call", name="whatshot_get_current"
                    ),
                    json=_modern_request(
                        "tools/call",
                        {
                            "name": "whatshot_get_current",
                            "arguments": {
                                "site": "bilibili",
                                "board_key": "type=181",
                            },
                        },
                    ),
                )
                string_limit = await client.post(
                    "/mcp",
                    headers=_modern_headers(
                        "tools/call", name="whatshot_get_current"
                    ),
                    json=_modern_request(
                        "tools/call",
                        {
                            "name": "whatshot_get_current",
                            "arguments": {"site": "bilibili", "limit": "1"},
                        },
                    ),
                )

        tools = {
            tool["name"]: tool for tool in listed.json()["result"]["tools"]
        }
        schema = tools["whatshot_get_current"]["inputSchema"]
        assert schema["additionalProperties"] is False
        assert "boardKey" in schema["properties"]
        assert "board_key" not in schema["properties"]
        assert schema["properties"]["limit"]["minimum"] == 1
        assert schema["properties"]["limit"]["maximum"] == 200

        assert correct.json()["result"]["isError"] is False
        assert backend.current_calls[0].board_key == "type=181"  # type: ignore[attr-defined]
        assert snake_case.json()["result"]["isError"] is True
        assert string_limit.json()["result"]["isError"] is True
        for response in (snake_case, string_limit):
            message = response.json()["result"]["content"][0]["text"]
            assert "INVALID_ARGUMENT" in message
            assert "validation error for" not in message

    asyncio.run(scenario())


def test_modern_streamable_http_rejects_method_and_name_header_mismatch() -> None:
    async def scenario() -> None:
        backend = StubBackend()
        server = build_mcp_server(  # type: ignore[arg-type]
            backend, await backend.get_capabilities()
        )
        app = server.streamable_http_app(
            streamable_http_path="/mcp",
            json_response=True,
            stateless_http=True,
        )
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8000"
            ) as client:
                method_mismatch = await client.post(
                    "/mcp",
                    headers=_modern_headers("tools/call"),
                    json=_modern_request("tools/list"),
                )
                name_mismatch = await client.post(
                    "/mcp",
                    headers=_modern_headers("tools/call", name="wrong-name"),
                    json=_modern_request(
                        "tools/call",
                        {
                            "name": "whatshot_get_capabilities",
                            "arguments": {},
                        },
                    ),
                )
        assert method_mismatch.status_code == 400
        assert method_mismatch.json()["error"]["code"] == -32020
        assert name_mismatch.status_code == 400
        assert name_mismatch.json()["error"]["code"] == -32020

    asyncio.run(scenario())


def test_health_and_readiness_expose_deployment_not_user_state() -> None:
    async def scenario() -> None:
        backend = StubBackend()
        server = build_mcp_server(  # type: ignore[arg-type]
            backend, await backend.get_capabilities()
        )
        app = build_streamable_http_app(server)
        transport = httpx.ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8000"
            ) as client,
        ):
            health = await client.get("/health")
            ready = await client.get("/ready")
        assert health.json() == {"status": "ok"}
        assert ready.status_code == 200
        assert ready.json() == {
            "status": "ready",
            "catalogHash": server.catalog_hash,
            "backend": {"name": "stub", "version": "1"},
            "contractVersion": "1",
            "boardKeyVersion": 1,
        }

    asyncio.run(scenario())
