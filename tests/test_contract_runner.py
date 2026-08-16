from __future__ import annotations

import asyncio

from whatshot_mcp.contracts.runner import probe_backend
from whatshot_mcp.contracts.v1 import (
    BackendCapabilities,
    CategoryCurrentData,
    CurrentData,
    NavigationData,
    SourceDetail,
    SourceListData,
)


class ProbeBackend:
    def __init__(self) -> None:
        self.frozen = False

    async def get_capabilities(self, *, force_refresh: bool = False):  # noqa: ANN201
        assert force_refresh is True
        return BackendCapabilities.model_validate(
            {
                "backend": {"name": "fixture", "version": "1"},
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

    def freeze_capabilities(self, _value: BackendCapabilities) -> None:
        self.frozen = True

    async def list_sources(self, _query):  # noqa: ANN001, ANN201
        return SourceListData.model_validate(
            {
                "sources": [
                    {
                        "site": "demo",
                        "title": "Demo",
                        "kinds": ["hotlist"],
                        "enabled": True,
                    }
                ],
                "truncated": False,
            }
        )

    async def get_source_schema(self, _site: str) -> SourceDetail:
        return SourceDetail.model_validate(
            {
                "site": "demo",
                "title": "Demo",
                "kinds": ["hotlist"],
                "dimensions": [],
                "boards": [
                    {
                        "boardKey": "hot",
                        "title": "Hot",
                        "kind": "hotlist",
                        "pathType": "hot",
                        "isDefault": True,
                        "liveFetchSupported": True,
                    }
                ],
            }
        )

    async def get_current(self, _request) -> CurrentData:  # noqa: ANN001
        return CurrentData.model_validate(
            {
                "site": "demo",
                "boardKey": "hot",
                "kind": "hotlist",
                "title": "Hot",
                "updateTime": "2026-08-13T00:00:00Z",
                "observedAt": "2026-08-13T00:00:00Z",
                "sourceMode": "live",
                "items": [],
            }
        )


def test_contract_runner_handles_core_read_only_backend() -> None:
    backend = ProbeBackend()
    result = asyncio.run(probe_backend(backend))  # type: ignore[arg-type]

    assert backend.frozen is True
    assert result.backend == "fixture"
    assert result.checks == ["capabilities", "sources", "sourceSchema", "current"]
    assert result.skipped == [
        "navigation:capability-disabled",
        "batchCurrent:capability-disabled",
        "history:capability-disabled",
    ]


class NavigationProbeBackend(ProbeBackend):
    async def get_capabilities(self, *, force_refresh: bool = False):  # noqa: ANN201
        capabilities = await super().get_capabilities(force_refresh=force_refresh)
        return capabilities.model_copy(
            update={
                "features": capabilities.features.model_copy(
                    update={"navigation": True}
                )
            }
        )

    async def list_navigation(self, _query):  # noqa: ANN001, ANN201
        return NavigationData.model_validate(
            {
                "entries": [
                    {
                        "category": "tech",
                        "categoryTitle": "科技",
                        "site": "demo",
                        "siteTitle": "Demo",
                        "kinds": ["hotlist"],
                        "boardCount": 1,
                    }
                ],
                "truncated": False,
            }
        )

    async def fetch_category_hotlists(self, _request):  # noqa: ANN001, ANN201
        return CategoryCurrentData(
            category="tech", results=[], errors=[], truncated=False
        )


def test_contract_runner_probes_navigation_and_category_current() -> None:
    backend = NavigationProbeBackend()
    result = asyncio.run(probe_backend(backend))  # type: ignore[arg-type]

    assert result.checks == [
        "capabilities",
        "navigation",
        "categoryCurrent",
        "sources",
        "sourceSchema",
        "current",
    ]
    assert result.skipped == [
        "batchCurrent:capability-disabled",
        "history:capability-disabled",
    ]
