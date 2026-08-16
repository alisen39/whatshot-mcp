"""Additive MCP-side analysis models built from Contract v1 evidence."""

from __future__ import annotations

from typing import Annotated

from pydantic import AwareDatetime, Field

from whatshot_mcp.contracts.v1.common import ContractModel, Coverage
from whatshot_mcp.contracts.v1.history import Evidence


class AnalysisQuery(ContractModel):
    keyword: Annotated[str, Field(min_length=1, max_length=500)]
    site: str | None = None
    board_key: str | None = None
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None
    scan_budget: Annotated[int, Field(ge=1, le=10_000)] = 1_000
    evidence_limit: Annotated[int, Field(ge=0, le=200)] = 30


class HotEventAnalysisQuery(AnalysisQuery):
    pass


class NewsflashCoverageAnalysisQuery(AnalysisQuery):
    evidence_limit: Annotated[int, Field(ge=0, le=200)] = 40


class LifecycleSummary(ContractModel):
    keyword: str
    first_seen_at: AwareDatetime | None = None
    last_seen_at: AwareDatetime | None = None
    duration_hours: Annotated[float, Field(ge=0)] = 0
    first_seen_approximate: bool
    last_seen_approximate: bool
    duration_approximate: bool


class HotEventSummary(LifecycleSummary):
    unique_topic_count: Annotated[int, Field(ge=0)]
    sample_count: Annotated[int, Field(ge=0)]
    platform_count: Annotated[int, Field(ge=0)]
    peak_rank: Annotated[int | None, Field(default=None, ge=1)]
    average_rank: Annotated[float | None, Field(default=None, ge=1)]
    peak_hot: int | float | None = None


class HotTimelinePoint(ContractModel):
    time: AwareDatetime
    sample_count: Annotated[int, Field(ge=0)]
    unique_topic_count: Annotated[int, Field(ge=0)]
    best_rank: Annotated[int | None, Field(default=None, ge=1)]
    peak_hot: int | float | None = None
    sites: list[str]


class HotEventAnalysisData(ContractModel):
    summary: HotEventSummary
    timeline: list[HotTimelinePoint]
    evidence: list[Evidence]
    analysis_complete: bool
    scanned_count: Annotated[int, Field(ge=0)]
    coverage: Coverage


class NewsflashCoverageSummary(LifecycleSummary):
    event_count: Annotated[int, Field(ge=0)]
    mention_count: Annotated[int, Field(ge=0)]
    platform_count: Annotated[int, Field(ge=0)]
    earliest_platform: str | None = None


class NewsflashEvent(ContractModel):
    canonical_title: Annotated[str, Field(min_length=1)]
    first_seen_at: AwareDatetime
    first_platform: str
    platforms: list[str]
    mention_count: Annotated[int, Field(ge=1)]


class NewsflashCoverageAnalysisData(ContractModel):
    summary: NewsflashCoverageSummary
    events: list[NewsflashEvent]
    evidence: list[Evidence]
    analysis_complete: bool
    scanned_count: Annotated[int, Field(ge=0)]
    coverage: Coverage
