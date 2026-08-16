"""Cloud navigation request and response models for Contract v1."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_serializer

from whatshot_mcp.contracts.v1.common import ContractModel, ItemKind
from whatshot_mcp.contracts.v1.current import CurrentData, Freshness, TargetError


class NavigationQuery(ContractModel):
    category: Annotated[str | None, Field(default=None, min_length=1, max_length=120)]
    cursor: str | None = None
    limit: Annotated[int, Field(ge=1, le=200)] = 50


class NavigationEntry(ContractModel):
    category: Annotated[str, Field(min_length=1, max_length=120)]
    category_title: Annotated[str, Field(min_length=1, max_length=300)]
    site: Annotated[str, Field(min_length=1, max_length=120)]
    site_title: Annotated[str, Field(min_length=1, max_length=300)]
    kinds: set[ItemKind]
    board_count: Annotated[int, Field(ge=0)]

    @field_serializer("kinds")
    def serialize_kinds(self, kinds: set[ItemKind]) -> list[str]:
        return sorted(kind.value for kind in kinds)


class NavigationData(ContractModel):
    entries: list[NavigationEntry]
    next_cursor: str | None = None
    truncated: bool


class CategoryCurrentRequest(ContractModel):
    category: Annotated[str, Field(min_length=1, max_length=120)]
    freshness: Freshness = Freshness.PREFER_CACHE
    limit_sites: Annotated[int, Field(ge=1, le=50)] = 12
    limit_per_board: Annotated[int, Field(ge=1, le=50)] = 10


class CategoryCurrentData(ContractModel):
    category: Annotated[str, Field(min_length=1, max_length=120)]
    results: list[CurrentData]
    errors: list[TargetError]
    truncated: bool
