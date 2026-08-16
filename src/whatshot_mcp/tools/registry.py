"""Open Tool Catalog with capability-selected Universal and Cloud tools."""

from __future__ import annotations

from whatshot_mcp.contracts.v1 import (
    BackendCapabilities,
    BatchCurrentData,
    BatchCurrentRequest,
    CategoryCurrentData,
    CategoryCurrentRequest,
    Coverage,
    CoverageQuery,
    CurrentData,
    CurrentRequest,
    HistoryPageData,
    HistoryQuery,
    HistorySearchQuery,
    HotEventAnalysisData,
    HotEventAnalysisQuery,
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
from whatshot_mcp.tools.models import EmptyInput, SourceSchemaInput
from whatshot_mcp.tools.spec import ToolAvailability, ToolSpec

_DATA_READ = frozenset({"data:read"})

_UNSORTED_TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="whatshot_get_capabilities",
        availability=ToolAvailability.UNIVERSAL,
        required_capability="capabilities",
        input_model=EmptyInput,
        output_model=BackendCapabilities,
        read_only=True,
        description="Describe Backend profiles, features, kinds, and limits.",
    ),
    ToolSpec(
        name="whatshot_list_sources",
        availability=ToolAvailability.UNIVERSAL,
        required_capability="sources",
        input_model=SourceListQuery,
        output_model=SourceListData,
        required_scopes=_DATA_READ,
        read_only=True,
        description="List available WhatsHot sources with cursor pagination.",
    ),
    ToolSpec(
        name="whatshot_get_source_schema",
        availability=ToolAvailability.UNIVERSAL,
        required_capability="sourceSchema",
        input_model=SourceSchemaInput,
        output_model=SourceDetail,
        required_scopes=_DATA_READ,
        read_only=True,
        description="Describe one source and its canonical boards.",
    ),
    ToolSpec(
        name="whatshot_get_current",
        availability=ToolAvailability.UNIVERSAL,
        required_capability="current",
        input_model=CurrentRequest,
        output_model=CurrentData,
        required_scopes=_DATA_READ,
        read_only=True,
        description="Read one current board with an explicit freshness policy.",
    ),
    ToolSpec(
        name="whatshot_get_current_batch",
        availability=ToolAvailability.UNIVERSAL,
        required_capability="batchCurrent",
        input_model=BatchCurrentRequest,
        output_model=BatchCurrentData,
        required_scopes=_DATA_READ,
        read_only=True,
        description="Read multiple explicitly named current boards.",
    ),
    ToolSpec(
        name="whatshot_query_history",
        availability=ToolAvailability.UNIVERSAL,
        required_capability="history",
        input_model=HistoryQuery,
        output_model=HistoryPageData,
        required_scopes=_DATA_READ,
        read_only=True,
        description="Query historical evidence with opaque cursor pagination.",
    ),
    ToolSpec(
        name="whatshot_search_history",
        availability=ToolAvailability.UNIVERSAL,
        required_capability="historySearch",
        input_model=HistorySearchQuery,
        output_model=HistoryPageData,
        required_scopes=_DATA_READ,
        read_only=True,
        description="Search historical evidence with opaque cursor pagination.",
    ),
    ToolSpec(
        name="whatshot_get_trend_series",
        availability=ToolAvailability.UNIVERSAL,
        required_capability="trendSeries",
        input_model=TrendQuery,
        output_model=TrendData,
        required_scopes=_DATA_READ,
        read_only=True,
        description="Read the historical rank and hot-value series for one item.",
    ),
    ToolSpec(
        name="whatshot_get_data_coverage",
        availability=ToolAvailability.UNIVERSAL,
        required_capability="coverage",
        input_model=CoverageQuery,
        output_model=Coverage,
        required_scopes=_DATA_READ,
        read_only=True,
        description="Describe historical data coverage and known limitations.",
    ),
    ToolSpec(
        name="whatshot_analyze_hot_event",
        availability=ToolAvailability.UNIVERSAL,
        required_capability="historySearch",
        input_model=HotEventAnalysisQuery,
        output_model=HotEventAnalysisData,
        required_scopes=_DATA_READ,
        read_only=True,
        description="Analyze a hot-event lifecycle over bounded historical evidence.",
    ),
    ToolSpec(
        name="whatshot_analyze_newsflash_coverage",
        availability=ToolAvailability.UNIVERSAL,
        required_capability="historySearch",
        input_model=NewsflashCoverageAnalysisQuery,
        output_model=NewsflashCoverageAnalysisData,
        required_scopes=_DATA_READ,
        read_only=True,
        description="Analyze newsflash propagation over bounded historical evidence.",
    ),
)

_UNSORTED_CLOUD_TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="whatshot_list_navigation",
        availability=ToolAvailability.CLOUD,
        required_capability="navigation",
        input_model=NavigationQuery,
        output_model=NavigationData,
        required_scopes=_DATA_READ,
        read_only=True,
        description="List category and site navigation entries.",
    ),
    ToolSpec(
        name="whatshot_fetch_category_hotlists",
        availability=ToolAvailability.CLOUD,
        required_capability="navigation",
        input_model=CategoryCurrentRequest,
        output_model=CategoryCurrentData,
        required_scopes=_DATA_READ,
        read_only=True,
        description="Read current boards for sites in one navigation category.",
    ),
)

CORE_READ_TOOL_SPECS: tuple[ToolSpec, ...] = tuple(
    sorted(_UNSORTED_TOOL_SPECS, key=lambda spec: spec.name)
)
CORE_READ_TOOL_MAP = {spec.name: spec for spec in CORE_READ_TOOL_SPECS}
CLOUD_TOOL_SPECS: tuple[ToolSpec, ...] = tuple(
    sorted(_UNSORTED_CLOUD_TOOL_SPECS, key=lambda spec: spec.name)
)
ALL_TOOL_SPECS: tuple[ToolSpec, ...] = tuple(
    sorted((*CORE_READ_TOOL_SPECS, *CLOUD_TOOL_SPECS), key=lambda spec: spec.name)
)
ALL_TOOL_MAP = {spec.name: spec for spec in ALL_TOOL_SPECS}

_CAPABILITY_FEATURE_FIELDS: dict[str, str | None] = {
    "capabilities": None,
    "sources": "sources",
    "sourceSchema": "source_schema",
    "current": "current",
    "batchCurrent": "batch_current",
    "history": "history",
    "historySearch": "history_search",
    "trendSeries": "trend_series",
    "coverage": "coverage",
    "navigation": "navigation",
    "semanticSearch": "semantic_search",
}

if len(ALL_TOOL_MAP) != len(ALL_TOOL_SPECS):  # pragma: no cover
    raise RuntimeError("duplicate names in Tool Catalog")


def list_tool_specs() -> tuple[ToolSpec, ...]:
    """Return the stable catalog in deterministic presentation order."""

    return CORE_READ_TOOL_SPECS


def tool_specs_for_capabilities(
    capabilities: BackendCapabilities,
) -> tuple[ToolSpec, ...]:
    """Freeze the deployment-level catalog from one capabilities snapshot."""

    selected: list[ToolSpec] = []
    for spec in ALL_TOOL_SPECS:
        field = _CAPABILITY_FEATURE_FIELDS.get(spec.required_capability)
        if spec.required_capability not in _CAPABILITY_FEATURE_FIELDS:
            raise RuntimeError(
                f"unknown ToolSpec capability {spec.required_capability!r}"
            )
        if field is None or getattr(capabilities.features, field):
            selected.append(spec)
    return tuple(selected)
