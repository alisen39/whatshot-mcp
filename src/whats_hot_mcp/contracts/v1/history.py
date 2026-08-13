"""Historical evidence and trend models for Contract v1."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from whats_hot_mcp.contracts.v1.common import ContractModel, Coverage, ItemKind


class HistoryQuery(ContractModel):
    site: str | None = None
    board_key: str | None = None
    kind: ItemKind | None = None
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None
    limit: Annotated[int, Field(ge=1, le=200)] = 50
    cursor: str | None = None


class HistorySearchQuery(HistoryQuery):
    keyword: Annotated[str, Field(min_length=1, max_length=500)]


class CoverageQuery(ContractModel):
    site: str | None = None
    board_key: str | None = None
    kind: ItemKind | None = None


class Evidence(ContractModel):
    kind: ItemKind
    site: Annotated[str, Field(min_length=1, max_length=120)]
    board_key: Annotated[str, Field(min_length=1, max_length=2048)]
    evidence_id: Annotated[str, Field(min_length=1, max_length=2048)]
    item_id: Annotated[str, Field(min_length=1, max_length=2048)]
    capture_id: str | None = None
    title: Annotated[str, Field(min_length=1)]
    url: str | None = None
    description: str | None = None
    rank: Annotated[int | None, Field(default=None, ge=1)]
    hot: int | float | str | None = None
    update_time: AwareDatetime | None = None
    observed_at: AwareDatetime
    first_seen_at: AwareDatetime | None = None
    last_seen_at: AwareDatetime | None = None
    published_at: AwareDatetime | None = None


class HistoryPageData(ContractModel):
    items: list[Evidence]
    next_cursor: str | None = None
    truncated: bool
    as_of: AwareDatetime
    coverage: Coverage


class TrendQuery(ContractModel):
    site: Annotated[str, Field(min_length=1, max_length=120)]
    board_key: Annotated[str, Field(min_length=1, max_length=2048)]
    item_id: Annotated[str, Field(min_length=1, max_length=2048)]
    bucket: Literal["10m", "1h", "6h", "1d"] = "1h"
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None


class TrendPoint(ContractModel):
    bucket_start: AwareDatetime
    best_rank: Annotated[int | None, Field(default=None, ge=1)]
    worst_rank: Annotated[int | None, Field(default=None, ge=1)]
    average_rank: Annotated[float | None, Field(default=None, ge=1)]
    min_hot: int | float | None = None
    max_hot: int | float | None = None
    samples: Annotated[int, Field(ge=0)]


class TrendData(ContractModel):
    site: str
    board_key: str
    item_id: str
    bucket: Literal["10m", "1h", "6h", "1d"]
    series: list[TrendPoint]
    coverage: Coverage
