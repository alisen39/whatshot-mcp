"""Single-source metadata for the future open Tool Catalog."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel

_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_CAPABILITY_RE = re.compile(r"^[a-z][A-Za-z0-9]{0,79}$")


class ToolAvailability(StrEnum):
    UNIVERSAL = "universal"
    CLOUD = "cloud"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    availability: ToolAvailability
    required_capability: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    read_only: bool = True
    required_scopes: frozenset[str] = field(default_factory=frozenset)
    description: str = ""

    def __post_init__(self) -> None:
        if not _TOOL_NAME_RE.fullmatch(self.name):
            raise ValueError(f"invalid tool name: {self.name!r}")
        if not _CAPABILITY_RE.fullmatch(self.required_capability):
            raise ValueError(
                f"invalid required capability: {self.required_capability!r}"
            )
        if any(not scope.strip() or " " in scope for scope in self.required_scopes):
            raise ValueError("required scopes must be non-empty tokens")
