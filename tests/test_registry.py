from __future__ import annotations

from whatshot_mcp.contracts.v1 import BackendCapabilities
from whatshot_mcp.tools import (
    ALL_TOOL_MAP,
    ALL_TOOL_SPECS,
    CLOUD_TOOL_SPECS,
    CORE_READ_TOOL_MAP,
    CORE_READ_TOOL_SPECS,
    ToolAvailability,
    list_tool_specs,
    tool_specs_for_capabilities,
)

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


def test_core_read_catalog_is_fixed_and_deterministic() -> None:
    assert [spec.name for spec in CORE_READ_TOOL_SPECS] == EXPECTED_NAMES
    assert list_tool_specs() is CORE_READ_TOOL_SPECS
    assert list(CORE_READ_TOOL_MAP) == EXPECTED_NAMES


def test_first_catalog_is_universal_read_only_and_has_contract_schemas() -> None:
    for spec in CORE_READ_TOOL_SPECS:
        assert spec.availability is ToolAvailability.UNIVERSAL
        assert spec.read_only is True
        assert spec.required_capability
        assert spec.input_model.model_json_schema()["type"] == "object"
        assert spec.output_model.model_json_schema()["type"] == "object"
        if spec.name == "whatshot_get_capabilities":
            assert spec.required_scopes == frozenset()
        else:
            assert spec.required_scopes == {"data:read"}


def test_cloud_navigation_catalog_metadata_is_explicit() -> None:
    assert [spec.name for spec in CLOUD_TOOL_SPECS] == [
        "whatshot_fetch_category_hotlists",
        "whatshot_list_navigation",
    ]
    assert [spec.name for spec in ALL_TOOL_SPECS] == sorted(ALL_TOOL_MAP)
    for spec in CLOUD_TOOL_SPECS:
        assert spec.availability is ToolAvailability.CLOUD
        assert spec.required_capability == "navigation"
        assert spec.required_scopes == {"data:read"}
        assert spec.read_only is True


def test_deployment_catalog_uses_features_not_user_identity() -> None:
    capabilities = BackendCapabilities.model_validate(
        {
            "backend": {"name": "local", "version": "1"},
            "boardKeyVersion": 1,
            "profiles": ["core-read"],
            "features": {
                "sources": True,
                "sourceSchema": True,
                "current": True,
                "batchCurrent": False,
                "history": False,
                "kinds": ["hotlist"],
            },
        }
    )

    assert [spec.name for spec in tool_specs_for_capabilities(capabilities)] == [
        "whatshot_get_capabilities",
        "whatshot_get_current",
        "whatshot_get_source_schema",
        "whatshot_list_sources",
    ]

    navigation_capabilities = capabilities.model_copy(
        update={
            "features": capabilities.features.model_copy(update={"navigation": True})
        }
    )
    assert [
        spec.name
        for spec in tool_specs_for_capabilities(navigation_capabilities)
        if spec.availability is ToolAvailability.CLOUD
    ] == [
        "whatshot_fetch_category_hotlists",
        "whatshot_list_navigation",
    ]
