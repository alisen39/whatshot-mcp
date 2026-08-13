from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from whats_hot_mcp.backend import BackendClient
from whats_hot_mcp.contracts.v1 import (
    BackendErrorCode,
    CategoryCurrentRequest,
    CoverageQuery,
    CurrentRequest,
    HistoryQuery,
    HistorySearchQuery,
    NavigationQuery,
    SourceListQuery,
    TrendQuery,
)
from whats_hot_mcp.errors import (
    BackendAPIError,
    BackendBoardKeyVersionError,
    BackendProtocolError,
    BackendTransportError,
    UnsupportedCapability,
)

ROOT = Path(__file__).resolve().parents[1]


def _fixture(name: str) -> dict[str, Any]:
    path = ROOT / "contracts" / "fixtures" / "v1" / name
    return json.loads(path.read_text(encoding="utf-8"))


def _meta(request_id: str) -> dict[str, str]:
    return {"requestId": request_id, "contractVersion": "1"}


def _success(data: dict[str, Any], request_id: str = "test") -> dict[str, Any]:
    return {"data": data, "meta": _meta(request_id)}


def _capabilities(
    *, batch_current: bool = True, history: bool = False, navigation: bool = False
) -> dict[str, Any]:
    payload = _fixture("capabilities-current.json")
    payload["data"]["features"]["batchCurrent"] = batch_current
    payload["data"]["features"]["navigation"] = navigation
    if history:
        payload["data"]["profiles"].append("history-read")
        for feature in ("history", "historySearch", "trendSeries", "coverage"):
            payload["data"]["features"][feature] = True
    return payload


def test_capabilities_are_cached_and_can_be_refreshed() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        assert request.url.path == "/api/v1/capabilities"
        calls += 1
        return httpx.Response(200, json=_capabilities())

    async def scenario() -> None:
        async with BackendClient(
            "http://127.0.0.1:6690/api/v1",
            transport=httpx.MockTransport(handler),
        ) as client:
            first, second = await asyncio.gather(
                client.get_capabilities(), client.get_capabilities()
            )
            assert first.backend.name == "whatshot-local"
            assert second == first
            assert calls == 1
            await client.get_capabilities(force_refresh=True)
            assert calls == 2

    asyncio.run(scenario())


def test_frozen_capabilities_do_not_change_until_process_restart() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_capabilities())

    async def scenario() -> None:
        async with BackendClient(
            "http://127.0.0.1:6690/api/v1",
            transport=httpx.MockTransport(handler),
        ) as client:
            snapshot = await client.get_capabilities(force_refresh=True)
            client.freeze_capabilities(snapshot)
            assert await client.get_capabilities(force_refresh=True) is snapshot
            assert await client.get_capabilities() is snapshot
            assert calls == 1

    asyncio.run(scenario())


def test_authorization_is_header_only_and_contract_models_are_used() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["user-agent"].startswith("whats-hot-mcp/")
        assert request.headers["authorization"] == "Bearer super-secret"
        if request.url.path.endswith("/capabilities"):
            assert (
                request.headers["x-whatshot-tool-name"] == "whatshot_get_capabilities"
            )
        else:
            assert request.headers["x-whatshot-tool-name"] == "whatshot_get_current"
        assert "super-secret" not in str(request.url)
        assert b"super-secret" not in request.content
        if request.url.path.endswith("/capabilities"):
            return httpx.Response(200, json=_capabilities())
        assert request.url.path.endswith("/current")
        assert json.loads(request.content) == {
            "site": "weibo",
            "boardKey": None,
            "freshness": "prefer_cache",
            "limit": 1,
        }
        return httpx.Response(
            200,
            json=_success(
                {
                    "site": "weibo",
                    "boardKey": "default",
                    "kind": "hotlist",
                    "title": "微博热搜",
                    "type": "热搜榜",
                    "updateTime": "2026-08-13T00:00:00Z",
                    "observedAt": "2026-08-13T00:00:01Z",
                    "sourceMode": "memory_cache",
                    "items": [
                        {
                            "itemId": "1",
                            "rank": 1,
                            "title": "示例",
                            "url": "https://example.test/1",
                            "mobileUrl": None,
                            "hot": 123,
                            "description": None,
                            "publishedAt": None,
                            "extra": {},
                        }
                    ],
                }
            ),
        )

    async def scenario() -> None:
        async with BackendClient(
            "http://127.0.0.1:6690/api/v1",
            api_key="super-secret",
            transport=httpx.MockTransport(handler),
        ) as client:
            result = await client.get_current(CurrentRequest(site="weibo", limit=1))
            assert result.board_key == "default"
            assert result.items[0].title == "示例"
            assert len(requests) == 2

    asyncio.run(scenario())


def test_source_query_and_path_follow_contract() -> None:
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.raw_path.decode())
        if request.url.path.endswith("/capabilities"):
            return httpx.Response(200, json=_capabilities())
        if request.url.path.endswith("/sources"):
            assert dict(request.url.params) == {"kind": "hotlist", "limit": "10"}
            return httpx.Response(
                200,
                json=_success(
                    {
                        "sources": [
                            {
                                "site": "weibo",
                                "title": "微博",
                                "description": None,
                                "kinds": ["hotlist"],
                                "boardCount": 1,
                                "enabled": True,
                                "capabilities": ["current"],
                            }
                        ],
                        "nextCursor": None,
                        "truncated": False,
                    }
                ),
            )
        return httpx.Response(
            200,
            json=_success(
                {
                    "site": "site/name",
                    "title": "测试",
                    "description": None,
                    "kinds": ["hotlist"],
                    "dimensions": [],
                    "boards": [],
                }
            ),
        )

    async def scenario() -> None:
        async with BackendClient(
            "http://127.0.0.1:6690/api/v1",
            transport=httpx.MockTransport(handler),
        ) as client:
            listed = await client.list_sources(
                SourceListQuery(kind="hotlist", limit=10)
            )
            assert listed.sources[0].site == "weibo"
            detail = await client.get_source_schema("site/name")
            assert detail.site == "site/name"
        assert any("sources/site%2Fname" in path for path in seen_paths)

    asyncio.run(scenario())


def test_stable_error_envelope_is_preserved_without_transport_details() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json=_fixture("error-unknown-source.json"))

    async def scenario() -> None:
        async with BackendClient(
            "http://127.0.0.1:6690/api/v1",
            transport=httpx.MockTransport(handler),
        ) as client:
            with pytest.raises(BackendAPIError) as raised:
                await client.get_capabilities()
        error = raised.value
        assert error.code is BackendErrorCode.UNKNOWN_SOURCE
        assert error.status_code == 404
        assert error.request_id == "fixture-error-unknown-source"
        assert str(error) == "UNKNOWN_SOURCE: Unknown source."

    asyncio.run(scenario())


def test_invalid_or_unreachable_backend_is_sanitized() -> None:
    async def malformed() -> None:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(200, text="not-json")
        )
        async with BackendClient(
            "http://127.0.0.1:6690/api/v1",
            api_key="must-not-leak",
            transport=transport,
        ) as client:
            with pytest.raises(BackendProtocolError) as raised:
                await client.get_capabilities()
        assert "must-not-leak" not in str(raised.value)

    async def unreachable() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("contains must-not-leak", request=request)

        async with BackendClient(
            "http://127.0.0.1:6690/api/v1",
            api_key="must-not-leak",
            transport=httpx.MockTransport(handler),
        ) as client:
            with pytest.raises(BackendTransportError) as raised:
                await client.get_capabilities()
        assert (
            str(raised.value)
            == "UPSTREAM_UNAVAILABLE: WhatsHot Backend is unavailable."
        )

    asyncio.run(malformed())
    asyncio.run(unreachable())


def test_capability_gating_happens_before_unsupported_endpoint_call() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json=_capabilities(batch_current=False))

    async def scenario() -> None:
        async with BackendClient(
            "http://127.0.0.1:6690/api/v1",
            transport=httpx.MockTransport(handler),
        ) as client:
            with pytest.raises(UnsupportedCapability) as raised:
                await client.require_capability("batchCurrent")
        assert raised.value.code is BackendErrorCode.CAPABILITY_UNAVAILABLE
        assert raised.value.details == {"capability": "batchCurrent"}
        assert paths == ["/api/v1/capabilities"]

    asyncio.run(scenario())


def test_history_endpoints_use_contract_queries_and_preserve_cursor() -> None:
    seen: list[tuple[str, dict[str, str]]] = []
    opaque_cursor = "opaque+/= cursor"

    def history_page() -> dict[str, Any]:
        return _success(
            {
                "items": [
                    {
                        "kind": "hotlist",
                        "site": "weibo",
                        "boardKey": "default",
                        "evidenceId": "capture-1:item-1",
                        "itemId": "item-1",
                        "captureId": "capture-1",
                        "title": "历史证据",
                        "url": "https://example.test/item-1",
                        "description": None,
                        "rank": 1,
                        "hot": 100,
                        "updateTime": "2026-08-13T00:00:00Z",
                        "observedAt": "2026-08-13T00:00:01Z",
                        "firstSeenAt": None,
                        "lastSeenAt": None,
                        "publishedAt": None,
                    }
                ],
                "nextCursor": "next-opaque",
                "truncated": True,
                "asOf": "2026-08-13T00:00:02Z",
                "coverage": {
                    "historyEnabled": True,
                    "earliestAvailableAt": "2026-08-01T00:00:00Z",
                    "latestAvailableAt": "2026-08-13T00:00:00Z",
                    "configuredSites": ["weibo"],
                    "complete": True,
                    "limitations": [],
                },
            }
        )

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, dict(request.url.params)))
        if request.url.path.endswith("/capabilities"):
            return httpx.Response(200, json=_capabilities(history=True))
        if request.url.path.endswith("/history/trends"):
            return httpx.Response(
                200,
                json=_success(
                    {
                        "site": "weibo",
                        "boardKey": "default",
                        "itemId": "item-1",
                        "bucket": "1h",
                        "series": [
                            {
                                "bucketStart": "2026-08-13T00:00:00Z",
                                "bestRank": 1,
                                "worstRank": 2,
                                "averageRank": 1.5,
                                "minHot": 90,
                                "maxHot": 100,
                                "samples": 2,
                            }
                        ],
                        "coverage": {
                            "historyEnabled": True,
                            "complete": True,
                            "limitations": [],
                        },
                    }
                ),
            )
        if request.url.path.endswith("/coverage"):
            return httpx.Response(
                200,
                json=_success(
                    {
                        "historyEnabled": True,
                        "earliestAvailableAt": "2026-08-01T00:00:00Z",
                        "latestAvailableAt": "2026-08-13T00:00:00Z",
                        "configuredSites": ["weibo"],
                        "complete": True,
                        "limitations": [],
                    }
                ),
            )
        return httpx.Response(200, json=history_page())

    async def scenario() -> None:
        since = datetime(2026, 8, 1, tzinfo=UTC)
        async with BackendClient(
            "http://127.0.0.1:6690/api/v1",
            transport=httpx.MockTransport(handler),
        ) as client:
            page = await client.query_history(
                HistoryQuery(
                    site="weibo",
                    board_key="default",
                    since=since,
                    limit=10,
                    cursor=opaque_cursor,
                )
            )
            searched = await client.search_history(
                HistorySearchQuery(keyword="OpenAI", cursor=opaque_cursor)
            )
            trend = await client.get_trend_series(
                TrendQuery(
                    site="weibo",
                    board_key="default",
                    item_id="item-1",
                )
            )
            coverage = await client.get_data_coverage(CoverageQuery(site="weibo"))
        assert page.next_cursor == "next-opaque"
        assert page.items[0].evidence_id == "capture-1:item-1"
        assert searched.as_of.isoformat().startswith("2026-08-13")
        assert trend.series[0].samples == 2
        assert coverage.history_enabled is True

    asyncio.run(scenario())

    by_path = {path: params for path, params in seen}
    assert by_path["/api/v1/history"]["cursor"] == opaque_cursor
    assert by_path["/api/v1/history"]["boardKey"] == "default"
    assert by_path["/api/v1/history"]["since"] == "2026-08-01T00:00:00Z"
    assert by_path["/api/v1/history/search"]["cursor"] == opaque_cursor
    assert by_path["/api/v1/history/search"]["keyword"] == "OpenAI"
    assert by_path["/api/v1/history/trends"]["itemId"] == "item-1"
    assert by_path["/api/v1/coverage"] == {"site": "weibo"}


def test_history_capability_gating_avoids_endpoint_call() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json=_capabilities())

    async def scenario() -> None:
        async with BackendClient(
            "http://127.0.0.1:6690/api/v1",
            transport=httpx.MockTransport(handler),
        ) as client:
            with pytest.raises(UnsupportedCapability) as raised:
                await client.query_history(HistoryQuery(cursor="opaque"))
        assert raised.value.capability == "history"

    asyncio.run(scenario())
    assert paths == ["/api/v1/capabilities"]


def test_navigation_endpoints_use_contract_queries_and_body() -> None:
    seen: list[tuple[str, str, dict[str, str], dict[str, Any] | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path, dict(request.url.params), body))
        if request.url.path.endswith("/capabilities"):
            return httpx.Response(200, json=_capabilities(navigation=True))
        if request.url.path.endswith("/navigation"):
            assert request.headers["x-whatshot-tool-name"] == "whatshot_list_navigation"
            return httpx.Response(200, json=_fixture("navigation-page.json"))
        assert request.url.path.endswith("/category/current")
        assert (
            request.headers["x-whatshot-tool-name"]
            == "whatshot_fetch_category_hotlists"
        )
        return httpx.Response(200, json=_fixture("category-current.json"))

    async def scenario() -> None:
        async with BackendClient(
            "http://127.0.0.1:6690/api/v1",
            transport=httpx.MockTransport(handler),
        ) as client:
            navigation = await client.list_navigation(
                NavigationQuery(category="tech", cursor="opaque+/= cursor", limit=10)
            )
            category = await client.fetch_category_hotlists(
                CategoryCurrentRequest(
                    category="tech",
                    freshness="live",
                    limit_sites=2,
                    limit_per_board=3,
                )
            )
        assert navigation.entries[0].site == "github"
        assert category.results[0].board_key == "default"

    asyncio.run(scenario())

    by_path = {path: (method, params, body) for method, path, params, body in seen}
    assert by_path["/api/v1/navigation"] == (
        "GET",
        {"category": "tech", "cursor": "opaque+/= cursor", "limit": "10"},
        None,
    )
    assert by_path["/api/v1/category/current"] == (
        "POST",
        {},
        {
            "category": "tech",
            "freshness": "live",
            "limitSites": 2,
            "limitPerBoard": 3,
        },
    )


def test_navigation_capability_gating_avoids_endpoint_call() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json=_capabilities(navigation=False))

    async def scenario() -> None:
        async with BackendClient(
            "http://127.0.0.1:6690/api/v1",
            transport=httpx.MockTransport(handler),
        ) as client:
            with pytest.raises(UnsupportedCapability) as raised:
                await client.list_navigation(NavigationQuery())
        assert raised.value.capability == "navigation"

    asyncio.run(scenario())
    assert paths == ["/api/v1/capabilities"]


def test_capabilities_reports_board_key_version_mismatch_separately() -> None:
    payload = _capabilities()
    payload["data"]["boardKeyVersion"] = 2

    async def scenario() -> None:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(200, json=payload)
        )
        async with BackendClient(
            "http://127.0.0.1:6690/api/v1", transport=transport
        ) as client:
            with pytest.raises(BackendBoardKeyVersionError):
                await client.get_capabilities()

    asyncio.run(scenario())
