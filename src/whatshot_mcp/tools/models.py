"""MCP-only tool input models not represented as Backend request bodies."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from whatshot_mcp.contracts.v1 import ContractModel


class EmptyInput(ContractModel):
    pass


class SourceSchemaInput(ContractModel):
    site: Annotated[str, Field(min_length=1, max_length=120)]
