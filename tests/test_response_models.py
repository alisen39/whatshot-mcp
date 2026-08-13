from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from whats_hot_mcp.contracts.v1 import (
    CategoryCurrentData,
    CategoryCurrentRequest,
    Coverage,
    CurrentData,
    HistoryPageData,
    ItemKind,
    NavigationData,
    NavigationQuery,
    SourceDetail,
    SourceMode,
    SuccessEnvelope,
)

NOW = datetime(2026, 8, 13, tzinfo=UTC)


def test_current_response_serializes_contract_aliases() -> None:
    data = CurrentData(
        site="weibo",
        board_key="hot",
        kind=ItemKind.HOTLIST,
        title="微博",
        type="热搜榜",
        update_time=NOW,
        observed_at=NOW,
        source_mode=SourceMode.DATABASE,
        items=[{"item_id": "1", "rank": 1, "title": "示例"}],
    )
    response = SuccessEnvelope[CurrentData](
        data=data,
        meta={"request_id": "current-1"},
    )

    payload = response.model_dump(mode="json")

    assert payload["data"]["boardKey"] == "hot"
    assert payload["data"]["updateTime"].endswith("Z")
    assert payload["data"]["items"][0]["itemId"] == "1"


def test_history_page_requires_snapshot_and_coverage() -> None:
    page = HistoryPageData(
        items=[],
        truncated=False,
        as_of=NOW,
        coverage=Coverage(history_enabled=True, complete=True),
    )

    assert page.as_of == NOW
    schema = HistoryPageData.model_json_schema(by_alias=True)
    assert {"items", "truncated", "asOf", "coverage"} <= set(schema["required"])


def test_source_schema_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SourceDetail(
            site="weibo",
            title="微博",
            kinds={ItemKind.HOTLIST},
            dimensions=[],
            boards=[],
            database_table="secret",
        )


def test_source_schema_describes_finite_and_dynamic_dimensions() -> None:
    detail = SourceDetail(
        site="weather",
        title="天气预警",
        kinds={ItemKind.HOTLIST},
        dimensions=[
            {
                "key": "type",
                "label": "榜单",
                "location": "path",
                "dynamic": False,
                "options": [{"value": "hot", "label": "热门"}],
            },
            {
                "key": "province",
                "label": "省份",
                "location": "query",
                "dynamic": True,
            },
        ],
        boards=[],
    )

    payload = detail.model_dump(mode="json")
    assert payload["dimensions"][0]["location"] == "path"
    assert payload["dimensions"][1]["dynamic"] is True


def test_timestamps_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError):
        CurrentData(
            site="weibo",
            board_key="hot",
            kind=ItemKind.HOTLIST,
            title="微博",
            update_time=datetime(2026, 8, 13),
            observed_at=NOW,
            source_mode=SourceMode.LIVE,
            items=[],
        )


def test_navigation_and_category_current_contract_shapes() -> None:
    navigation = NavigationData.model_validate(
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
            "nextCursor": "opaque",
            "truncated": True,
        }
    )
    category = CategoryCurrentData(
        category="tech",
        results=[],
        errors=[],
        truncated=False,
    )

    assert navigation.model_dump(mode="json")["entries"][0]["boardCount"] == 1
    assert category.model_dump(mode="json") == {
        "category": "tech",
        "results": [],
        "errors": [],
        "truncated": False,
    }

    with pytest.raises(ValidationError):
        NavigationQuery(limit=201)
    with pytest.raises(ValidationError):
        CategoryCurrentRequest(category="tech", limit_sites=51)
