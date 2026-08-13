"""Current-board request and response models for Contract v1."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import AwareDatetime, Field, JsonValue

from whats_hot_mcp.contracts.v1.common import (
    BackendErrorCode,
    ContractModel,
    ItemKind,
    SourceMode,
)


class Freshness(StrEnum):
    CACHE_ONLY = "cache_only"
    PREFER_CACHE = "prefer_cache"
    LIVE = "live"


class CurrentRequest(ContractModel):
    site: Annotated[str, Field(min_length=1, max_length=120)]
    board_key: Annotated[str | None, Field(default=None, max_length=2048)]
    freshness: Freshness = Freshness.PREFER_CACHE
    limit: Annotated[int, Field(ge=1, le=200)] = 50


class CurrentItem(ContractModel):
    item_id: Annotated[str, Field(min_length=1, max_length=2048)]
    rank: Annotated[int | None, Field(default=None, ge=1)]
    title: Annotated[str, Field(min_length=1)]
    url: str | None = None
    mobile_url: str | None = None
    hot: int | float | str | None = None
    description: str | None = None
    published_at: AwareDatetime | None = None
    extra: dict[str, JsonValue] = Field(default_factory=dict)


class CurrentData(ContractModel):
    site: Annotated[str, Field(min_length=1, max_length=120)]
    board_key: Annotated[str, Field(min_length=1, max_length=2048)]
    kind: ItemKind
    title: Annotated[str, Field(min_length=1)]
    type: str | None = None
    update_time: AwareDatetime
    observed_at: AwareDatetime
    source_mode: SourceMode
    items: list[CurrentItem]


class BatchCurrentTarget(ContractModel):
    site: Annotated[str, Field(min_length=1, max_length=120)]
    board_key: Annotated[str | None, Field(default=None, max_length=2048)]


class BatchCurrentRequest(ContractModel):
    targets: Annotated[list[BatchCurrentTarget], Field(min_length=1, max_length=100)]
    freshness: Freshness = Freshness.PREFER_CACHE
    limit_per_board: Annotated[int, Field(ge=1, le=200)] = 50


class TargetError(ContractModel):
    site: str
    board_key: str | None = None
    code: BackendErrorCode
    message: Annotated[str, Field(min_length=1, max_length=500)]
    retryable: bool = False


class BatchCurrentData(ContractModel):
    results: list[CurrentData]
    errors: list[TargetError]
    truncated: bool
