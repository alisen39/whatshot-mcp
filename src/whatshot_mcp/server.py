"""MCPServer exposing a deployment-level capabilities snapshot."""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from datetime import datetime
from functools import wraps
from typing import Annotated, Any, Literal

from mcp.server import CacheHint, MCPServer, ServerRequestContext
from mcp.server.context import CallNext, HandlerResult
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field, ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from whatshot_mcp import __version__
from whatshot_mcp.analysis import (
    analyze_hot_event as build_hot_event_analysis,
)
from whatshot_mcp.analysis import (
    analyze_newsflash_coverage as build_newsflash_coverage_analysis,
)
from whatshot_mcp.auth import BearerPassthroughAuthMiddleware
from whatshot_mcp.backend import BackendClient
from whatshot_mcp.contracts.v1 import (
    BackendCapabilities,
    BatchCurrentData,
    BatchCurrentRequest,
    BatchCurrentTarget,
    CategoryCurrentData,
    CategoryCurrentRequest,
    Coverage,
    CoverageQuery,
    CurrentData,
    CurrentRequest,
    Freshness,
    HistoryPageData,
    HistoryQuery,
    HistorySearchQuery,
    HotEventAnalysisData,
    HotEventAnalysisQuery,
    ItemKind,
    NavigationData,
    NavigationQuery,
    NewsflashCoverageAnalysisData,
    NewsflashCoverageAnalysisQuery,
    SourceDetail,
    SourceListData,
    SourceListQuery,
    TrendData,
    TrendQuery,
)
from whatshot_mcp.errors import BackendClientError
from whatshot_mcp.tools import (
    ALL_TOOL_MAP,
    ToolSpec,
    tool_specs_for_capabilities,
)

_READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)


def catalog_hash(specs: tuple[ToolSpec, ...]) -> str:
    payload = [
        {
            "name": spec.name,
            "availability": spec.availability.value,
            "requiredCapability": spec.required_capability,
            "readOnly": spec.read_only,
            "requiredScopes": sorted(spec.required_scopes),
            "inputSchema": spec.input_model.model_json_schema(by_alias=True),
            "outputSchema": spec.output_model.model_json_schema(by_alias=True),
        }
        for spec in specs
    ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class WhatsHotMCPServer(MCPServer):
    """MCPServer with a deterministic public catalog ordering."""

    catalog_hash: str
    capabilities_snapshot: BackendCapabilities

    async def list_tools(self):  # noqa: ANN201
        return sorted(await super().list_tools(), key=lambda tool: tool.name)

    def add_tool(
        self,
        function: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Register one tool with a fail-closed top-level argument model.

        MCP SDK v2 intentionally permits extra function arguments by default.
        WhatsHot's public Contract does not: misspelled camelCase fields must fail
        instead of being ignored and silently selecting a default board.
        """

        super().add_tool(function, *args, **kwargs)
        registered_name = kwargs.get("name") or function.__name__
        tool = self._tool_manager.get_tool(registered_name)
        if tool is None:  # pragma: no cover - the SDK has just registered it
            raise RuntimeError(f"Tool registration failed: {registered_name}")
        argument_model = tool.fn_metadata.arg_model
        argument_model.model_config["extra"] = "forbid"
        argument_model.model_rebuild(force=True)
        tool.parameters = argument_model.model_json_schema(by_alias=True)

    async def call_tool(self, name, arguments, context=None):  # noqa: ANN001, ANN201
        """Return stable validation feedback without Pydantic implementation text."""

        try:
            return await super().call_tool(name, arguments, context)
        except ToolError as exc:
            cause = exc.__cause__
            if isinstance(cause, ValidationError):
                first = cause.errors(include_url=False)[0]
                location = ".".join(str(part) for part in first["loc"])
                message = str(first["msg"])
                detail = f"{location}: {message}" if location else message
                raise ToolError(f"INVALID_ARGUMENT: {detail}") from None
            raise


class ToolCatalogMetadata:
    """Attach the fixed-catalog identity through SDK v2 public middleware."""

    def __init__(self, value: str) -> None:
        self._catalog_hash = value

    async def __call__(
        self,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        result = await call_next(ctx)
        if ctx.method == "tools/list":
            # SDK v2 resolves protocol-version-specific result classes at the
            # dispatch boundary, so avoid coupling this public middleware to
            # one facade class identity.
            if isinstance(result, BaseModel) and hasattr(result, "meta"):
                meta = dict(getattr(result, "meta") or {})
                meta["top.whatshot/catalogHash"] = self._catalog_hash
                return result.model_copy(update={"meta": meta})
            if isinstance(result, dict):
                updated = dict(result)
                meta = dict(updated.get("_meta") or {})
                meta["top.whatshot/catalogHash"] = self._catalog_hash
                updated["_meta"] = meta
                return updated
        return result


def _tool_meta(spec: ToolSpec, value: str) -> dict[str, Any]:
    return {
        "top.whatshot/toolAvailability": spec.availability.value,
        "top.whatshot/requiredCapability": spec.required_capability,
        "top.whatshot/requiredScopes": sorted(spec.required_scopes),
        "top.whatshot/catalogHash": value,
    }


def _tool_boundary(function: Callable[..., Coroutine[Any, Any, Any]]):  # noqa: ANN202
    @wraps(function)
    async def guarded(*args: Any, **kwargs: Any) -> Any:
        try:
            return await function(*args, **kwargs)
        except BackendClientError as exc:
            # MCPServer converts ordinary handler failures into a tool-level
            # isError result. BackendClientError has already removed transport
            # details and secrets, so only the stable code/message cross here.
            raise RuntimeError(str(exc)) from None

    return guarded


def build_mcp_server(
    backend: BackendClient,
    capabilities: BackendCapabilities,
    *,
    close_backend_on_shutdown: bool = False,
) -> WhatsHotMCPServer:
    selected_specs = tool_specs_for_capabilities(capabilities)
    selected_names = {spec.name for spec in selected_specs}
    frozen_catalog_hash = catalog_hash(selected_specs)
    freeze_capabilities = getattr(backend, "freeze_capabilities", None)
    if callable(freeze_capabilities):
        freeze_capabilities(capabilities)

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if close_backend_on_shutdown:
                await backend.aclose()

    server = WhatsHotMCPServer(
        "whatshot",
        title="WhatsHot",
        description="WhatsHot board discovery, current data, and historical evidence.",
        version=__version__,
        instructions=(
            "Use the tools for source discovery, current boards, and historical evidence. "
            "The Tool Catalog is frozen from the Backend's deployment-level "
            "capabilities snapshot until process restart."
        ),
        lifespan=lifespan,
        cache_hints={"tools/list": CacheHint(ttl_ms=300_000, scope="public")},
        middleware=[ToolCatalogMetadata(frozen_catalog_hash)],
    )
    server.catalog_hash = frozen_catalog_hash
    server.capabilities_snapshot = capabilities

    def spec(name: str) -> ToolSpec:
        return ALL_TOOL_MAP[name]

    def register(name: str):  # noqa: ANN202
        current = spec(name)

        def decorator(function):  # noqa: ANN001, ANN202
            guarded = _tool_boundary(function)
            if name not in selected_names:
                return guarded
            return server.tool(
                name=current.name,
                description=current.description,
                annotations=_READ_ONLY,
                meta=_tool_meta(current, frozen_catalog_hash),
            )(guarded)

        return decorator

    @register("whatshot_get_capabilities")
    async def whatshot_get_capabilities() -> BackendCapabilities:
        return capabilities

    @register("whatshot_list_sources")
    async def whatshot_list_sources(
        kind: ItemKind | None = None,
        cursor: Annotated[str | None, Field(max_length=4096)] = None,
        limit: Annotated[int, Field(strict=True, ge=1, le=200)] = 50,
    ) -> SourceListData:
        return await backend.list_sources(
            SourceListQuery(kind=kind, cursor=cursor, limit=limit)
        )

    @register("whatshot_get_source_schema")
    async def whatshot_get_source_schema(
        site: Annotated[str, Field(min_length=1, max_length=120)],
    ) -> SourceDetail:
        return await backend.get_source_schema(site)

    @register("whatshot_get_current")
    async def whatshot_get_current(
        site: Annotated[str, Field(min_length=1, max_length=120)],
        boardKey: Annotated[str | None, Field(max_length=2048)] = None,
        freshness: Freshness = Freshness.PREFER_CACHE,
        limit: Annotated[int, Field(strict=True, ge=1, le=200)] = 50,
    ) -> CurrentData:
        return await backend.get_current(
            CurrentRequest(
                site=site,
                board_key=boardKey,
                freshness=freshness,
                limit=limit,
            )
        )

    @register("whatshot_get_current_batch")
    async def whatshot_get_current_batch(
        targets: list[BatchCurrentTarget],
        freshness: Freshness = Freshness.PREFER_CACHE,
        limitPerBoard: Annotated[int, Field(strict=True, ge=1, le=200)] = 50,
    ) -> BatchCurrentData:
        return await backend.get_current_batch(
            BatchCurrentRequest(
                targets=targets,
                freshness=freshness,
                limit_per_board=limitPerBoard,
            )
        )

    @register("whatshot_list_navigation")
    async def whatshot_list_navigation(
        category: str | None = None,
        cursor: str | None = None,
        limit: Annotated[int, Field(strict=True, ge=1, le=200)] = 50,
    ) -> NavigationData:
        return await backend.list_navigation(
            NavigationQuery(category=category, cursor=cursor, limit=limit)
        )

    @register("whatshot_fetch_category_hotlists")
    async def whatshot_fetch_category_hotlists(
        category: Annotated[str, Field(min_length=1, max_length=120)],
        freshness: Freshness = Freshness.PREFER_CACHE,
        limitSites: Annotated[int, Field(strict=True, ge=1, le=50)] = 12,
        limitPerBoard: Annotated[int, Field(strict=True, ge=1, le=50)] = 10,
    ) -> CategoryCurrentData:
        return await backend.fetch_category_hotlists(
            CategoryCurrentRequest(
                category=category,
                freshness=freshness,
                limit_sites=limitSites,
                limit_per_board=limitPerBoard,
            )
        )

    @register("whatshot_query_history")
    async def whatshot_query_history(
        site: Annotated[str | None, Field(max_length=120)] = None,
        boardKey: Annotated[str | None, Field(max_length=2048)] = None,
        kind: ItemKind | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: Annotated[int, Field(strict=True, ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Field(max_length=4096)] = None,
    ) -> HistoryPageData:
        return await backend.query_history(
            HistoryQuery(
                site=site,
                board_key=boardKey,
                kind=kind,
                since=since,
                until=until,
                limit=limit,
                cursor=cursor,
            )
        )

    @register("whatshot_search_history")
    async def whatshot_search_history(
        keyword: Annotated[str, Field(min_length=1, max_length=500)],
        site: Annotated[str | None, Field(max_length=120)] = None,
        boardKey: Annotated[str | None, Field(max_length=2048)] = None,
        kind: ItemKind | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: Annotated[int, Field(strict=True, ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Field(max_length=4096)] = None,
    ) -> HistoryPageData:
        return await backend.search_history(
            HistorySearchQuery(
                keyword=keyword,
                site=site,
                board_key=boardKey,
                kind=kind,
                since=since,
                until=until,
                limit=limit,
                cursor=cursor,
            )
        )

    @register("whatshot_get_trend_series")
    async def whatshot_get_trend_series(
        site: Annotated[str, Field(min_length=1, max_length=120)],
        boardKey: Annotated[str, Field(min_length=1, max_length=2048)],
        itemId: Annotated[str, Field(min_length=1, max_length=2048)],
        bucket: Literal["10m", "1h", "6h", "1d"] = "1h",
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> TrendData:
        return await backend.get_trend_series(
            TrendQuery(
                site=site,
                board_key=boardKey,
                item_id=itemId,
                bucket=bucket,
                since=since,
                until=until,
            )
        )

    @register("whatshot_get_data_coverage")
    async def whatshot_get_data_coverage(
        site: Annotated[str | None, Field(max_length=120)] = None,
        boardKey: Annotated[str | None, Field(max_length=2048)] = None,
        kind: ItemKind | None = None,
    ) -> Coverage:
        return await backend.get_data_coverage(
            CoverageQuery(site=site, board_key=boardKey, kind=kind)
        )

    @register("whatshot_analyze_hot_event")
    async def whatshot_analyze_hot_event(
        keyword: Annotated[str, Field(min_length=1, max_length=500)],
        site: Annotated[str | None, Field(max_length=120)] = None,
        boardKey: Annotated[str | None, Field(max_length=2048)] = None,
        since: datetime | None = None,
        until: datetime | None = None,
        scanBudget: Annotated[int, Field(strict=True, ge=1, le=10_000)] = 1_000,
        evidenceLimit: Annotated[int, Field(strict=True, ge=0, le=200)] = 30,
    ) -> HotEventAnalysisData:
        return await build_hot_event_analysis(
            backend,
            HotEventAnalysisQuery(
                keyword=keyword,
                site=site,
                board_key=boardKey,
                since=since,
                until=until,
                scan_budget=scanBudget,
                evidence_limit=evidenceLimit,
            ),
        )

    @register("whatshot_analyze_newsflash_coverage")
    async def whatshot_analyze_newsflash_coverage(
        keyword: Annotated[str, Field(min_length=1, max_length=500)],
        site: Annotated[str | None, Field(max_length=120)] = None,
        boardKey: Annotated[str | None, Field(max_length=2048)] = None,
        since: datetime | None = None,
        until: datetime | None = None,
        scanBudget: Annotated[int, Field(strict=True, ge=1, le=10_000)] = 1_000,
        evidenceLimit: Annotated[int, Field(strict=True, ge=0, le=200)] = 40,
    ) -> NewsflashCoverageAnalysisData:
        return await build_newsflash_coverage_analysis(
            backend,
            NewsflashCoverageAnalysisQuery(
                keyword=keyword,
                site=site,
                board_key=boardKey,
                since=since,
                until=until,
                scan_budget=scanBudget,
                evidence_limit=evidenceLimit,
            ),
        )

    return server


def build_streamable_http_app(
    server: MCPServer,
    *,
    path: str = "/mcp",
    host: str = "127.0.0.1",
    bearer_passthrough: bool = False,
    allowed_hosts: list[str] | None = None,
    allowed_origins: list[str] | None = None,
) -> ASGIApp:
    """Build the SDK v2 HTTP app with optional Developer key passthrough."""

    transport_security = None
    if allowed_hosts or allowed_origins:
        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[
                "127.0.0.1:*",
                "localhost:*",
                "[::1]:*",
                *(allowed_hosts or []),
            ],
            allowed_origins=[
                "http://127.0.0.1:*",
                "http://localhost:*",
                "http://[::1]:*",
                *(allowed_origins or []),
            ],
        )

    app: Starlette = server.streamable_http_app(
        streamable_http_path=path,
        json_response=True,
        stateless_http=True,
        transport_security=transport_security,
        host=host,
    )

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def ready(_request: Request) -> JSONResponse:
        catalog = getattr(server, "catalog_hash", None)
        capabilities = getattr(server, "capabilities_snapshot", None)
        if not isinstance(catalog, str) or capabilities is None:
            return JSONResponse({"status": "not-ready"}, status_code=503)
        return JSONResponse(
            {
                "status": "ready",
                "catalogHash": catalog,
                "backend": capabilities.backend.model_dump(mode="json"),
                "contractVersion": "1",
                "boardKeyVersion": capabilities.board_key_version,
            }
        )

    app.add_route("/health", health, methods=["GET"])
    app.add_route("/ready", ready, methods=["GET"])
    if bearer_passthrough:
        return BearerPassthroughAuthMiddleware(app)
    return app
