from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from whatshot_mcp.analysis import (
    analyze_hot_event,
    analyze_newsflash_coverage,
)
from whatshot_mcp.contracts.v1 import (
    BackendCapabilities,
    Coverage,
    Evidence,
    HistoryPageData,
    HotEventAnalysisQuery,
    NewsflashCoverageAnalysisQuery,
)
from whatshot_mcp.errors import BackendProtocolError

NOW = datetime(2026, 8, 13, tzinfo=UTC)


def _coverage(*, complete: bool = True) -> Coverage:
    return Coverage(
        history_enabled=True,
        earliest_available_at=NOW - timedelta(days=30),
        latest_available_at=NOW,
        configured_sites=["weibo", "cls", "wallstreetcn"],
        complete=complete,
        limitations=[] if complete else ["retention-window"],
    )


def _evidence(
    index: int,
    *,
    kind: str = "hotlist",
    site: str = "weibo",
    title: str | None = None,
    minutes: int | None = None,
) -> Evidence:
    observed = NOW + timedelta(minutes=index if minutes is None else minutes)
    return Evidence.model_validate(
        {
            "kind": kind,
            "site": site,
            "boardKey": "default",
            "evidenceId": f"evidence-{index}-{site}",
            "itemId": f"item-{index}",
            "captureId": f"capture-{index}",
            "title": title or f"ACME 事件 {index}",
            "rank": index + 1,
            "hot": 100 + index,
            "observedAt": observed,
            "firstSeenAt": observed,
        }
    )


class PagedBackend:
    def __init__(
        self, pages: list[HistoryPageData], *, max_result_items: int = 200
    ) -> None:
        self.pages = pages
        self.queries = []
        self.capabilities = BackendCapabilities.model_validate(
            {
                "backend": {"name": "stub", "version": "1"},
                "boardKeyVersion": 1,
                "profiles": ["core-read"],
                "features": {
                    "sources": True,
                    "sourceSchema": True,
                    "current": True,
                    "kinds": ["hotlist", "newsflash"],
                },
                "limits": {"maxResultItems": max_result_items},
            }
        )

    async def get_capabilities(self):  # noqa: ANN201
        return self.capabilities

    async def search_history(self, query):  # noqa: ANN001, ANN201
        self.queries.append(query)
        return self.pages[len(self.queries) - 1]


def test_hot_event_auto_paginates_and_separates_scan_and_evidence_limits() -> None:
    backend = PagedBackend(
        [
            HistoryPageData(
                items=[_evidence(0), _evidence(1)],
                next_cursor="opaque+/= next",
                truncated=True,
                as_of=NOW,
                coverage=_coverage(),
            ),
            HistoryPageData(
                items=[_evidence(2)],
                next_cursor=None,
                truncated=False,
                as_of=NOW,
                coverage=_coverage(),
            ),
        ]
    )

    result = asyncio.run(
        analyze_hot_event(
            backend,  # type: ignore[arg-type]
            HotEventAnalysisQuery(keyword="ACME", scan_budget=10, evidence_limit=2),
        )
    )

    assert result.analysis_complete is True
    assert result.scanned_count == 3
    assert len(result.evidence) == 2
    assert len(backend.queries) == 2
    assert backend.queries[0].cursor is None
    assert backend.queries[1].cursor == "opaque+/= next"
    assert backend.queries[0].kind == "hotlist"
    assert result.summary.first_seen_approximate is False
    assert result.summary.last_seen_approximate is False
    assert result.summary.duration_approximate is False
    assert result.coverage.complete is True


def test_scan_budget_marks_lifecycle_approximate_and_preserves_coverage() -> None:
    backend = PagedBackend(
        [
            HistoryPageData(
                items=[_evidence(0), _evidence(1)],
                next_cursor="more",
                truncated=True,
                as_of=NOW,
                coverage=_coverage(complete=False),
            )
        ]
    )
    result = asyncio.run(
        analyze_hot_event(
            backend,  # type: ignore[arg-type]
            HotEventAnalysisQuery(keyword="ACME", scan_budget=2, evidence_limit=20),
        )
    )

    assert result.analysis_complete is False
    assert result.scanned_count == 2
    assert result.summary.first_seen_approximate is True
    assert result.summary.last_seen_approximate is True
    assert result.summary.duration_approximate is True
    assert result.coverage.complete is False
    assert result.coverage.limitations == ["retention-window"]
    assert backend.queries[0].limit == 2


def test_scan_page_size_respects_backend_max_result_items() -> None:
    backend = PagedBackend(
        [
            HistoryPageData(
                items=[_evidence(index) for index in range(100)],
                next_cursor="page-2",
                truncated=True,
                as_of=NOW,
                coverage=_coverage(),
            ),
            HistoryPageData(
                items=[_evidence(index) for index in range(100, 150)],
                next_cursor=None,
                truncated=False,
                as_of=NOW,
                coverage=_coverage(),
            ),
        ],
        max_result_items=100,
    )

    result = asyncio.run(
        analyze_hot_event(
            backend,  # type: ignore[arg-type]
            HotEventAnalysisQuery(keyword="ACME", scan_budget=300, evidence_limit=5),
        )
    )

    assert [query.limit for query in backend.queries] == [100, 100]
    assert result.scanned_count == 150
    assert result.analysis_complete is True


def test_newsflash_coverage_groups_events_across_pages() -> None:
    backend = PagedBackend(
        [
            HistoryPageData(
                items=[
                    _evidence(
                        0,
                        kind="newsflash",
                        site="wallstreetcn",
                        title="ACME 获得新订单",
                    ),
                    _evidence(
                        1,
                        kind="newsflash",
                        site="cls",
                        title="ACME 获得新订单",
                    ),
                    _evidence(
                        2,
                        kind="newsflash",
                        site="cls",
                        title="ACME 上调指引",
                    ),
                ],
                next_cursor=None,
                truncated=False,
                as_of=NOW,
                coverage=_coverage(),
            )
        ]
    )

    result = asyncio.run(
        analyze_newsflash_coverage(
            backend,  # type: ignore[arg-type]
            NewsflashCoverageAnalysisQuery(
                keyword="ACME", scan_budget=100, evidence_limit=1
            ),
        )
    )
    assert result.analysis_complete is True
    assert result.scanned_count == 3
    assert result.summary.event_count == 2
    assert result.summary.mention_count == 3
    assert result.summary.platform_count == 2
    assert result.summary.earliest_platform == "wallstreetcn"
    assert result.events[0].platforms == ["cls", "wallstreetcn"]
    assert len(result.evidence) == 1
    assert backend.queries[0].kind == "newsflash"


def test_cyclic_cursor_is_rejected_as_backend_protocol_error() -> None:
    backend = PagedBackend(
        [
            HistoryPageData(
                items=[_evidence(0)],
                next_cursor="same",
                truncated=True,
                as_of=NOW,
                coverage=_coverage(),
            ),
            HistoryPageData(
                items=[_evidence(1)],
                next_cursor="same",
                truncated=True,
                as_of=NOW,
                coverage=_coverage(),
            ),
        ]
    )
    with pytest.raises(BackendProtocolError, match="cyclic"):
        asyncio.run(
            analyze_hot_event(
                backend,  # type: ignore[arg-type]
                HotEventAnalysisQuery(keyword="ACME", scan_budget=10),
            )
        )


def test_analysis_schema_requires_completeness_and_approximation_fields() -> None:
    schema = HotEventAnalysisQuery.model_json_schema(by_alias=True)
    assert "scanBudget" in schema["properties"]
    assert "evidenceLimit" in schema["properties"]

    from whatshot_mcp.contracts.v1 import HotEventAnalysisData

    output = HotEventAnalysisData.model_json_schema(by_alias=True)
    assert {"analysisComplete", "scannedCount", "coverage"} <= set(output["required"])
    summary = output["$defs"]["HotEventSummary"]
    assert {
        "firstSeenApproximate",
        "lastSeenApproximate",
        "durationApproximate",
    } <= set(summary["required"])


def test_hot_event_uses_last_listing_of_item_day_evidence() -> None:
    first = NOW
    last = NOW + timedelta(hours=11)
    item_day = Evidence.model_validate(
        {
            "kind": "hotlist",
            "site": "weibo",
            "boardKey": "default",
            "evidenceId": "hotlist-day:1:2026-08-13:abc",
            "itemId": "abc",
            "captureId": None,
            "title": "ACME 发布",
            "rank": 2,
            "hot": 300,
            "observedAt": first,
            "firstSeenAt": first,
            "lastSeenAt": last,
        }
    )
    backend = PagedBackend(
        [
            HistoryPageData(
                items=[item_day],
                next_cursor=None,
                truncated=False,
                as_of=NOW,
                coverage=_coverage(),
            )
        ]
    )

    result = asyncio.run(
        analyze_hot_event(
            backend,  # type: ignore[arg-type]
            HotEventAnalysisQuery(keyword="ACME", scan_budget=10, evidence_limit=2),
        )
    )

    assert result.summary.first_seen_at == first
    assert result.summary.last_seen_at == last
    assert result.summary.duration_hours == 11
    assert result.summary.sample_count == 1
