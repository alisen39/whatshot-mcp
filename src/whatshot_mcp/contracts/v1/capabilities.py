"""Backend capability negotiation for Contract v1."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_serializer, model_validator

from whatshot_mcp.contracts.v1.common import ContractModel, ItemKind


class CapabilityProfile(StrEnum):
    CORE_READ = "core-read"
    HISTORY_READ = "history-read"


class BackendInfo(ContractModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    version: Annotated[str, Field(min_length=1, max_length=80)]


class CapabilityFeatures(ContractModel):
    sources: bool = False
    source_schema: bool = False
    current: bool = False
    live_fetch: bool = False
    batch_current: bool = False
    history: bool = False
    history_search: bool = False
    trend_series: bool = False
    coverage: bool = False
    navigation: bool = False
    semantic_search: bool = False
    kinds: set[ItemKind] = Field(default_factory=set)

    @field_serializer("kinds")
    def serialize_kinds(self, kinds: set[ItemKind]) -> list[str]:
        return sorted(kind.value for kind in kinds)


class CapabilityLimits(ContractModel):
    max_result_items: Annotated[int, Field(ge=1, le=200)] = 200
    max_batch_targets: Annotated[int, Field(ge=1, le=100)] = 12
    default_history_days: Annotated[int, Field(ge=1, le=3650)] = 7
    max_history_days: Annotated[int, Field(ge=1, le=3650)] = 365

    @model_validator(mode="after")
    def validate_history_window(self) -> CapabilityLimits:
        if self.default_history_days > self.max_history_days:
            raise ValueError("default_history_days must not exceed max_history_days")
        return self


_PROFILE_REQUIREMENTS: dict[CapabilityProfile, tuple[str, ...]] = {
    CapabilityProfile.CORE_READ: ("sources", "source_schema", "current"),
    CapabilityProfile.HISTORY_READ: (
        "history",
        "history_search",
        "trend_series",
        "coverage",
    ),
}


class BackendCapabilities(ContractModel):
    backend: BackendInfo
    board_key_version: Literal[1]
    profiles: set[CapabilityProfile] = Field(
        default_factory=lambda: {CapabilityProfile.CORE_READ}
    )
    features: CapabilityFeatures
    limits: CapabilityLimits = Field(default_factory=CapabilityLimits)

    @field_serializer("profiles")
    def serialize_profiles(
        self,
        profiles: set[CapabilityProfile],
    ) -> list[str]:
        return sorted(profile.value for profile in profiles)

    @model_validator(mode="after")
    def validate_profiles(self) -> BackendCapabilities:
        if CapabilityProfile.CORE_READ not in self.profiles:
            raise ValueError("Contract v1 requires the core-read capability profile")
        for profile in self.profiles:
            missing = [
                feature
                for feature in _PROFILE_REQUIREMENTS[profile]
                if not getattr(self.features, feature)
            ]
            if missing:
                raise ValueError(
                    f"profile {profile.value!r} is missing required features: "
                    + ", ".join(missing)
                )
        if not self.features.kinds:
            raise ValueError("at least one supported item kind is required")
        return self
