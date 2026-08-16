"""Common values and response envelopes for Backend Contract v1."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue
from pydantic.alias_generators import to_camel

CONTRACT_MAJOR: Literal["1"] = "1"


class ContractModel(BaseModel):
    """Strict model that accepts Python names and emits Contract JSON names."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
        use_enum_values=False,
    )


class ItemKind(StrEnum):
    HOTLIST = "hotlist"
    NEWSFLASH = "newsflash"
    GOLD = "gold"


class SourceMode(StrEnum):
    MEMORY_CACHE = "memory_cache"
    REDIS_CACHE = "redis_cache"
    DATABASE = "database"
    LIVE = "live"


class BackendErrorCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    INVALID_CURSOR = "INVALID_CURSOR"
    CURSOR_EXPIRED = "CURSOR_EXPIRED"
    UNKNOWN_SOURCE = "UNKNOWN_SOURCE"
    UNKNOWN_BOARD = "UNKNOWN_BOARD"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    HISTORY_DISABLED = "HISTORY_DISABLED"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    INSUFFICIENT_SCOPE = "INSUFFICIENT_SCOPE"
    RATE_LIMITED = "RATE_LIMITED"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ResponseMeta(ContractModel):
    request_id: Annotated[str, Field(min_length=1, max_length=128)]
    contract_version: Literal["1"] = CONTRACT_MAJOR
    generated_at: AwareDatetime | None = None


DataT = TypeVar("DataT")


class SuccessEnvelope(ContractModel, Generic[DataT]):
    data: DataT
    meta: ResponseMeta


class ErrorDetail(ContractModel):
    code: BackendErrorCode
    message: Annotated[str, Field(min_length=1, max_length=500)]
    retryable: bool = False
    details: dict[str, JsonValue] | None = None


class ErrorEnvelope(ContractModel):
    error: ErrorDetail
    meta: ResponseMeta


class Coverage(ContractModel):
    history_enabled: bool
    earliest_available_at: AwareDatetime | None = None
    latest_available_at: AwareDatetime | None = None
    configured_sites: list[str] | None = None
    complete: bool
    limitations: list[str] = Field(default_factory=list)


def utc_now() -> datetime:
    """Return an aware timestamp for callers constructing response metadata."""

    return datetime.now(UTC)
