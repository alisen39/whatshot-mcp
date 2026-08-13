"""Executable smoke runner for a deployed Backend Contract v1 implementation."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict, dataclass
from typing import Any

from pydantic import SecretStr

from whats_hot_mcp.backend import BackendClient
from whats_hot_mcp.config import BackendSettings
from whats_hot_mcp.contracts.v1 import (
    BatchCurrentRequest,
    BatchCurrentTarget,
    CategoryCurrentRequest,
    CoverageQuery,
    CurrentRequest,
    HistoryQuery,
    HistorySearchQuery,
    NavigationQuery,
    SourceListQuery,
    TrendQuery,
)


@dataclass(frozen=True, slots=True)
class ContractProbeResult:
    backend: str
    backend_version: str
    board_key_version: int
    profiles: list[str]
    checks: list[str]
    skipped: list[str]


async def probe_backend(client: BackendClient) -> ContractProbeResult:
    """Validate envelopes and representative paths through strict models."""

    checks = ["capabilities"]
    skipped: list[str] = []
    capabilities = await client.get_capabilities(force_refresh=True)
    client.freeze_capabilities(capabilities)

    if capabilities.features.navigation:
        navigation = await client.list_navigation(NavigationQuery(limit=1))
        checks.append("navigation")
        if navigation.entries:
            await client.fetch_category_hotlists(
                CategoryCurrentRequest(
                    category=navigation.entries[0].category,
                    limit_sites=1,
                    limit_per_board=1,
                )
            )
            checks.append("categoryCurrent")
        else:
            skipped.append("categoryCurrent:no-navigation-entry")
    else:
        skipped.append("navigation:capability-disabled")

    source_page = await client.list_sources(SourceListQuery(limit=1))
    checks.append("sources")
    if not source_page.sources:
        skipped.extend(["sourceSchema:no-sources", "current:no-sources"])
        return _result(capabilities, checks, skipped)

    source = source_page.sources[0]
    detail = await client.get_source_schema(source.site)
    checks.append("sourceSchema")
    if not detail.boards:
        skipped.append("current:no-enumerated-board")
        return await _history_checks(client, capabilities, checks, skipped, None)

    board = next((item for item in detail.boards if item.is_default), detail.boards[0])
    current = await client.get_current(
        CurrentRequest(site=detail.site, board_key=board.board_key, limit=1)
    )
    checks.append("current")
    if capabilities.features.batch_current:
        await client.get_current_batch(
            BatchCurrentRequest(
                targets=[
                    BatchCurrentTarget(site=detail.site, board_key=board.board_key)
                ],
                limit_per_board=1,
            )
        )
        checks.append("batchCurrent")
    else:
        skipped.append("batchCurrent:capability-disabled")

    item_id = current.items[0].item_id if current.items else None
    return await _history_checks(
        client,
        capabilities,
        checks,
        skipped,
        {
            "site": detail.site,
            "boardKey": board.board_key,
            "itemId": item_id,
            "keyword": current.items[0].title if current.items else None,
        },
    )


async def _history_checks(
    client: BackendClient,
    capabilities: Any,
    checks: list[str],
    skipped: list[str],
    target: dict[str, str | None] | None,
) -> ContractProbeResult:
    if not capabilities.features.history:
        skipped.append("history:capability-disabled")
        return _result(capabilities, checks, skipped)

    history = await client.query_history(
        HistoryQuery(
            site=target["site"] if target else None,
            board_key=target["boardKey"] if target else None,
            limit=1,
        )
    )
    checks.append("history")
    await client.get_data_coverage(
        CoverageQuery(
            site=target["site"] if target else None,
            board_key=target["boardKey"] if target else None,
        )
    )
    checks.append("coverage")

    evidence = history.items[0] if history.items else None
    keyword = target.get("keyword") if target else None
    if not keyword and evidence is not None:
        keyword = evidence.title
    if keyword:
        await client.search_history(
            HistorySearchQuery(
                keyword=keyword,
                site=target["site"] if target else None,
                board_key=target["boardKey"] if target else None,
                limit=1,
            )
        )
        checks.append("historySearch")
    else:
        skipped.append("historySearch:no-evidence-keyword")

    trend_target = target or {}
    item_id = trend_target.get("itemId") or (
        evidence.item_id if evidence is not None else None
    )
    site = trend_target.get("site") or (evidence.site if evidence is not None else None)
    board_key = trend_target.get("boardKey") or (
        evidence.board_key if evidence is not None else None
    )
    if item_id and site and board_key:
        await client.get_trend_series(
            TrendQuery(site=site, board_key=board_key, item_id=item_id)
        )
        checks.append("trendSeries")
    else:
        skipped.append("trendSeries:no-evidence-item")
    return _result(capabilities, checks, skipped)


def _result(
    capabilities: Any, checks: list[str], skipped: list[str]
) -> ContractProbeResult:
    return ContractProbeResult(
        backend=capabilities.backend.name,
        backend_version=capabilities.backend.version,
        board_key_version=capabilities.board_key_version,
        profiles=sorted(profile.value for profile in capabilities.profiles),
        checks=checks,
        skipped=skipped,
    )


async def _run(args: argparse.Namespace) -> int:
    token = os.environ.get(args.token_env) if args.token_env else None
    if args.token_env and not token:
        raise SystemExit(f"token environment variable {args.token_env!r} is not set")
    base_url = BackendSettings(url=args.base_url).url
    async with BackendClient(
        base_url,
        api_key=SecretStr(token) if token else None,
        timeout_seconds=args.timeout,
        capabilities_ttl_seconds=0,
    ) as client:
        result = await probe_backend(client)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe WhatsHot Backend Contract v1")
    parser.add_argument("--base-url", required=True, help="URL ending in /api/v1")
    parser.add_argument(
        "--token-env", help="Environment variable containing Bearer token"
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
