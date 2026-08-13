"""Contract v1 HTTP client shared by Universal and Cloud Tools."""

from __future__ import annotations

import asyncio
import time
from typing import Any, TypeVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel, SecretStr, ValidationError

from whats_hot_mcp import __version__
from whats_hot_mcp.contracts.v1 import (
    BOARD_KEY_VERSION,
    BackendCapabilities,
    BatchCurrentData,
    BatchCurrentRequest,
    CategoryCurrentData,
    CategoryCurrentRequest,
    Coverage,
    CoverageQuery,
    CurrentData,
    CurrentRequest,
    ErrorEnvelope,
    HistoryPageData,
    HistoryQuery,
    HistorySearchQuery,
    NavigationData,
    NavigationQuery,
    SourceDetail,
    SourceListData,
    SourceListQuery,
    SuccessEnvelope,
    TrendData,
    TrendQuery,
)
from whats_hot_mcp.errors import (
    BackendAPIError,
    BackendBoardKeyVersionError,
    BackendProtocolError,
    BackendTransportError,
    UnsupportedCapability,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


class BackendClient:
    """Typed, sanitized client for the storage-independent Backend Contract."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: SecretStr | str | None = None,
        timeout_seconds: float = 15.0,
        capabilities_ttl_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self._api_key = (
            api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        )
        self._capabilities_ttl = capabilities_ttl_seconds
        self._cached_capabilities: BackendCapabilities | None = None
        self._capabilities_expires_at = 0.0
        self._capabilities_lock = asyncio.Lock()
        self._capabilities_frozen = False
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout_seconds,
            follow_redirects=False,
            transport=transport,
        )

    async def __aenter__(self) -> BackendClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_capabilities(
        self, *, force_refresh: bool = False
    ) -> BackendCapabilities:
        if self._capabilities_frozen and self._cached_capabilities is not None:
            return self._cached_capabilities
        now = time.monotonic()
        if (
            not force_refresh
            and self._cached_capabilities is not None
            and now < self._capabilities_expires_at
        ):
            return self._cached_capabilities
        async with self._capabilities_lock:
            now = time.monotonic()
            if (
                not force_refresh
                and self._cached_capabilities is not None
                and now < self._capabilities_expires_at
            ):
                return self._cached_capabilities
            capabilities = await self._request(
                "GET",
                "capabilities",
                BackendCapabilities,
                tool_name="whatshot_get_capabilities",
            )
            self._cached_capabilities = capabilities
            self._capabilities_expires_at = now + self._capabilities_ttl
            return capabilities

    def freeze_capabilities(self, capabilities: BackendCapabilities) -> None:
        """Use one startup snapshot until this client/process is restarted."""

        if (
            self._capabilities_frozen
            and self._cached_capabilities is not None
            and self._cached_capabilities != capabilities
        ):
            raise ValueError("Backend capabilities are already frozen")
        self._cached_capabilities = capabilities
        self._capabilities_expires_at = float("inf")
        self._capabilities_frozen = True

    async def list_sources(self, query: SourceListQuery) -> SourceListData:
        await self.require_capability("sources")
        return await self._request(
            "GET",
            "sources",
            SourceListData,
            tool_name="whatshot_list_sources",
            params=query.model_dump(mode="json", exclude_none=True),
        )

    async def get_source_schema(self, site: str) -> SourceDetail:
        await self.require_capability("sourceSchema")
        return await self._request(
            "GET",
            f"sources/{quote(site, safe='')}",
            SourceDetail,
            tool_name="whatshot_get_source_schema",
        )

    async def get_current(self, request: CurrentRequest) -> CurrentData:
        await self.require_capability("current")
        return await self._request(
            "POST",
            "current",
            CurrentData,
            tool_name="whatshot_get_current",
            json_body=request.model_dump(mode="json"),
        )

    async def get_current_batch(self, request: BatchCurrentRequest) -> BatchCurrentData:
        await self.require_capability("batchCurrent")
        return await self._request(
            "POST",
            "current/batch",
            BatchCurrentData,
            tool_name="whatshot_get_current_batch",
            json_body=request.model_dump(mode="json"),
        )

    async def list_navigation(self, query: NavigationQuery) -> NavigationData:
        await self.require_capability("navigation")
        return await self._request(
            "GET",
            "navigation",
            NavigationData,
            tool_name="whatshot_list_navigation",
            params=query.model_dump(mode="json", exclude_none=True),
        )

    async def fetch_category_hotlists(
        self, request: CategoryCurrentRequest
    ) -> CategoryCurrentData:
        await self.require_capability("navigation")
        return await self._request(
            "POST",
            "category/current",
            CategoryCurrentData,
            tool_name="whatshot_fetch_category_hotlists",
            json_body=request.model_dump(mode="json"),
        )

    async def query_history(self, query: HistoryQuery) -> HistoryPageData:
        await self.require_capability("history")
        return await self._request(
            "GET",
            "history",
            HistoryPageData,
            tool_name="whatshot_query_history",
            params=query.model_dump(mode="json", exclude_none=True),
        )

    async def search_history(self, query: HistorySearchQuery) -> HistoryPageData:
        await self.require_capability("historySearch")
        return await self._request(
            "GET",
            "history/search",
            HistoryPageData,
            tool_name="whatshot_search_history",
            params=query.model_dump(mode="json", exclude_none=True),
        )

    async def get_trend_series(self, query: TrendQuery) -> TrendData:
        await self.require_capability("trendSeries")
        return await self._request(
            "GET",
            "history/trends",
            TrendData,
            tool_name="whatshot_get_trend_series",
            params=query.model_dump(mode="json", exclude_none=True),
        )

    async def get_data_coverage(self, query: CoverageQuery) -> Coverage:
        await self.require_capability("coverage")
        return await self._request(
            "GET",
            "coverage",
            Coverage,
            tool_name="whatshot_get_data_coverage",
            params=query.model_dump(mode="json", exclude_none=True),
        )

    async def require_capability(self, capability: str) -> None:
        capabilities = await self.get_capabilities()
        attribute = _CAPABILITY_FIELDS.get(capability)
        if attribute is None or not getattr(capabilities.features, attribute):
            raise UnsupportedCapability(capability)

    async def _request(
        self,
        method: str,
        path: str,
        model: type[ModelT],
        *,
        tool_name: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> ModelT:
        headers = {
            "Accept": "application/json",
            "User-Agent": f"whats-hot-mcp/{__version__}",
            "X-Whatshot-Tool-Name": tool_name,
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = await self._client.request(
                method,
                path,
                params=params,
                json=json_body,
                headers=headers,
            )
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise BackendTransportError() from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise BackendProtocolError() from exc

        if response.is_success:
            try:
                envelope = SuccessEnvelope[model].model_validate(payload)
            except ValidationError as exc:
                if model is BackendCapabilities and isinstance(payload, dict):
                    data = payload.get("data")
                    if (
                        isinstance(data, dict)
                        and "boardKeyVersion" in data
                        and data["boardKeyVersion"] != BOARD_KEY_VERSION
                    ):
                        raise BackendBoardKeyVersionError() from None
                raise BackendProtocolError() from exc
            return envelope.data

        try:
            envelope = ErrorEnvelope.model_validate(payload)
        except ValidationError as exc:
            raise BackendProtocolError() from exc
        raise BackendAPIError(
            envelope.error.code,
            envelope.error.message,
            retryable=envelope.error.retryable,
            status_code=response.status_code,
            request_id=envelope.meta.request_id,
            details=envelope.error.details,
        )


_CAPABILITY_FIELDS = {
    "sources": "sources",
    "sourceSchema": "source_schema",
    "current": "current",
    "batchCurrent": "batch_current",
    "history": "history",
    "historySearch": "history_search",
    "trendSeries": "trend_series",
    "coverage": "coverage",
    "navigation": "navigation",
}
