"""Storage-independent analyses over paginated Backend history evidence."""

from __future__ import annotations

import math
import re
import string
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from whatshot_mcp.backend import BackendClient
from whatshot_mcp.contracts.v1 import (
    Coverage,
    Evidence,
    HistorySearchQuery,
    HotEventAnalysisData,
    HotEventAnalysisQuery,
    HotEventSummary,
    HotTimelinePoint,
    ItemKind,
    NewsflashCoverageAnalysisData,
    NewsflashCoverageAnalysisQuery,
    NewsflashCoverageSummary,
    NewsflashEvent,
)
from whatshot_mcp.errors import BackendProtocolError

_SPACE_RE = re.compile(r"\s+")
_EXTRA_PUNCTUATION = "，。！？；：、“”‘’（）【】《》—…"
_PUNCT_TRANSLATION = str.maketrans("", "", string.punctuation + _EXTRA_PUNCTUATION)


@dataclass(frozen=True, slots=True)
class _ScanResult:
    items: list[Evidence]
    analysis_complete: bool
    coverage: Coverage


async def analyze_hot_event(
    backend: BackendClient,
    query: HotEventAnalysisQuery,
) -> HotEventAnalysisData:
    scan = await _scan_history(backend, query, kind=ItemKind.HOTLIST)
    items = sorted(scan.items, key=_event_time)
    incomplete = not scan.analysis_complete
    times = [_event_time(item) for item in items]
    ranks = [item.rank for item in items if item.rank is not None]
    hot_values = [
        value for item in items if (value := _numeric_hot(item.hot)) is not None
    ]
    first_seen = min(times) if times else None
    last_seen = max(times) if times else None

    summary = HotEventSummary(
        keyword=query.keyword,
        first_seen_at=first_seen,
        last_seen_at=last_seen,
        duration_hours=_duration_hours(first_seen, last_seen),
        first_seen_approximate=incomplete,
        last_seen_approximate=incomplete,
        duration_approximate=incomplete,
        unique_topic_count=len({_topic_key(item) for item in items}),
        sample_count=len(items),
        platform_count=len({item.site for item in items}),
        peak_rank=min(ranks) if ranks else None,
        average_rank=round(sum(ranks) / len(ranks), 2) if ranks else None,
        peak_hot=max(hot_values) if hot_values else None,
    )
    return HotEventAnalysisData(
        summary=summary,
        timeline=_hot_timeline(items),
        evidence=_select_hot_evidence(items, query.evidence_limit),
        analysis_complete=scan.analysis_complete,
        scanned_count=len(items),
        coverage=scan.coverage,
    )


async def analyze_newsflash_coverage(
    backend: BackendClient,
    query: NewsflashCoverageAnalysisQuery,
) -> NewsflashCoverageAnalysisData:
    scan = await _scan_history(backend, query, kind=ItemKind.NEWSFLASH)
    items = sorted(scan.items, key=_event_time)
    incomplete = not scan.analysis_complete
    times = [_event_time(item) for item in items]
    first_seen = min(times) if times else None
    last_seen = max(times) if times else None

    grouped: dict[str, list[Evidence]] = defaultdict(list)
    for item in items:
        grouped[_normalized_title(item.title) or item.item_id].append(item)

    events: list[NewsflashEvent] = []
    for group_items in grouped.values():
        group_items.sort(key=_event_time)
        first = group_items[0]
        events.append(
            NewsflashEvent(
                canonical_title=first.title,
                first_seen_at=_event_time(first),
                first_platform=first.site,
                platforms=sorted({item.site for item in group_items}),
                mention_count=len(group_items),
            )
        )
    events.sort(key=lambda event: event.first_seen_at)

    summary = NewsflashCoverageSummary(
        keyword=query.keyword,
        first_seen_at=first_seen,
        last_seen_at=last_seen,
        duration_hours=_duration_hours(first_seen, last_seen),
        first_seen_approximate=incomplete,
        last_seen_approximate=incomplete,
        duration_approximate=incomplete,
        event_count=len(events),
        mention_count=len(items),
        platform_count=len({item.site for item in items}),
        earliest_platform=events[0].first_platform if events else None,
    )
    return NewsflashCoverageAnalysisData(
        summary=summary,
        events=events,
        evidence=items[: query.evidence_limit],
        analysis_complete=scan.analysis_complete,
        scanned_count=len(items),
        coverage=scan.coverage,
    )


async def _scan_history(
    backend: BackendClient,
    query: HotEventAnalysisQuery | NewsflashCoverageAnalysisQuery,
    *,
    kind: ItemKind,
) -> _ScanResult:
    items: list[Evidence] = []
    coverages: list[Coverage] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()
    analysis_complete = False

    while len(items) < query.scan_budget:
        remaining = query.scan_budget - len(items)
        page = await backend.search_history(
            HistorySearchQuery(
                keyword=query.keyword,
                site=query.site,
                board_key=query.board_key,
                kind=kind,
                since=query.since,
                until=query.until,
                limit=min(200, remaining),
                cursor=cursor,
            )
        )
        coverages.append(page.coverage)
        items.extend(page.items[:remaining])

        next_cursor = page.next_cursor
        if next_cursor is None:
            analysis_complete = not page.truncated
            break
        if next_cursor in seen_cursors or next_cursor == cursor:
            raise BackendProtocolError("Backend returned a cyclic history cursor.")
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    if not coverages:  # scan_budget is >= 1, retained as a defensive invariant.
        raise BackendProtocolError("Backend returned no history page.")
    return _ScanResult(
        items=items,
        analysis_complete=analysis_complete,
        coverage=_merge_coverage(coverages),
    )


def _merge_coverage(coverages: list[Coverage]) -> Coverage:
    earliest = [
        value.earliest_available_at
        for value in coverages
        if value.earliest_available_at
    ]
    latest = [
        value.latest_available_at for value in coverages if value.latest_available_at
    ]
    configured_sites = (
        sorted({site for value in coverages for site in (value.configured_sites or [])})
        if all(value.configured_sites is not None for value in coverages)
        else None
    )
    return Coverage(
        history_enabled=all(value.history_enabled for value in coverages),
        earliest_available_at=min(earliest) if earliest else None,
        latest_available_at=max(latest) if latest else None,
        configured_sites=configured_sites,
        complete=all(value.complete for value in coverages),
        limitations=list(
            dict.fromkeys(
                limitation for value in coverages for limitation in value.limitations
            )
        ),
    )


def _hot_timeline(items: list[Evidence]) -> list[HotTimelinePoint]:
    buckets: dict[datetime, list[Evidence]] = defaultdict(list)
    for item in items:
        buckets[_event_time(item).replace(minute=0, second=0, microsecond=0)].append(
            item
        )

    timeline: list[HotTimelinePoint] = []
    for bucket, bucket_items in sorted(buckets.items()):
        ranks = [item.rank for item in bucket_items if item.rank is not None]
        hot_values = [
            value
            for item in bucket_items
            if (value := _numeric_hot(item.hot)) is not None
        ]
        timeline.append(
            HotTimelinePoint(
                time=bucket,
                sample_count=len(bucket_items),
                unique_topic_count=len({_topic_key(item) for item in bucket_items}),
                best_rank=min(ranks) if ranks else None,
                peak_hot=max(hot_values) if hot_values else None,
                sites=sorted({item.site for item in bucket_items}),
            )
        )
    return timeline


def _select_hot_evidence(items: list[Evidence], limit: int) -> list[Evidence]:
    if limit <= 0 or not items:
        return []
    selected: list[Evidence] = []
    selected_ids: set[str] = set()

    def add(item: Evidence | None) -> None:
        if item is None or item.evidence_id in selected_ids or len(selected) >= limit:
            return
        selected.append(item)
        selected_ids.add(item.evidence_id)

    add(items[0])
    add(items[-1])
    ranked = [item for item in items if item.rank is not None]
    numeric_hot = [item for item in items if _numeric_hot(item.hot) is not None]
    add(min(ranked, key=lambda item: item.rank or math.inf) if ranked else None)
    add(
        max(numeric_hot, key=lambda item: _numeric_hot(item.hot) or -math.inf)
        if numeric_hot
        else None
    )
    for item in reversed(items):
        add(item)
    return sorted(selected, key=_event_time)


def _event_time(item: Evidence) -> datetime:
    return item.first_seen_at or item.observed_at


def _topic_key(item: Evidence) -> str:
    return item.item_id or _normalized_title(item.title)


def _normalized_title(title: str) -> str:
    return _SPACE_RE.sub("", title.strip().casefold().translate(_PUNCT_TRANSLATION))


def _numeric_hot(value: int | float | str | None) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return value
    if isinstance(value, str):
        try:
            parsed = float(value.replace(",", "").strip())
        except ValueError:
            return None
        return int(parsed) if parsed.is_integer() else parsed
    return None


def _duration_hours(first: datetime | None, last: datetime | None) -> float:
    if first is None or last is None:
        return 0
    return round(max(0.0, (last - first).total_seconds() / 3600), 2)
