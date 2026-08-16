"""Source discovery models for Contract v1."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, JsonValue, field_serializer

from whatshot_mcp.contracts.v1.common import ContractModel, ItemKind


class SourceListQuery(ContractModel):
    kind: ItemKind | None = None
    cursor: str | None = None
    limit: Annotated[int, Field(ge=1, le=200)] = 50


class SourceSummary(ContractModel):
    site: Annotated[str, Field(min_length=1, max_length=120)]
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: str | None = None
    kinds: set[ItemKind]
    board_count: Annotated[int | None, Field(default=None, ge=0)]
    enabled: bool
    capabilities: set[str] = Field(default_factory=set)

    @field_serializer("kinds")
    def serialize_kinds(self, kinds: set[ItemKind]) -> list[str]:
        return sorted(kind.value for kind in kinds)

    @field_serializer("capabilities")
    def serialize_capabilities(self, capabilities: set[str]) -> list[str]:
        return sorted(capabilities)


class SourceListData(ContractModel):
    sources: list[SourceSummary]
    next_cursor: str | None = None
    truncated: bool


class DimensionLocation(StrEnum):
    PATH = "path"
    QUERY = "query"


class DimensionOption(ContractModel):
    value: Annotated[str, Field(min_length=1, max_length=500)]
    label: Annotated[str, Field(min_length=1, max_length=500)]


class SourceDimension(ContractModel):
    """One board identity dimension declared by a source.

    ``dynamic`` means the Backend cannot publish a finite option set.  The
    source's explicitly enumerated ``boards`` still lists finite/default
    boards, while callers can use this descriptor to understand dynamic
    dimensions such as province, day, and month.
    """

    key: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=80)]
    label: Annotated[str | None, Field(default=None, max_length=200)]
    location: DimensionLocation
    dynamic: bool
    options: list[DimensionOption] = Field(default_factory=list)


class BoardDescriptor(ContractModel):
    board_key: Annotated[str, Field(min_length=1, max_length=2048)]
    title: Annotated[str, Field(min_length=1, max_length=200)]
    kind: ItemKind
    path_type: Annotated[str, Field(min_length=1, max_length=200)]
    params: dict[str, JsonValue] = Field(default_factory=dict)
    is_default: bool
    live_fetch_supported: bool


class SourceDetail(ContractModel):
    site: Annotated[str, Field(min_length=1, max_length=120)]
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: str | None = None
    kinds: set[ItemKind]
    dimensions: list[SourceDimension]
    boards: list[BoardDescriptor]

    @field_serializer("kinds")
    def serialize_kinds(self, kinds: set[ItemKind]) -> list[str]:
        return sorted(kind.value for kind in kinds)
