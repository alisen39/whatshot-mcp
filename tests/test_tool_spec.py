from __future__ import annotations

from whatshot_mcp.contracts.v1 import CurrentData, CurrentRequest
from whatshot_mcp.tools import ToolAvailability, ToolSpec


def test_tool_spec_has_only_stable_availability_values() -> None:
    assert {value.value for value in ToolAvailability} == {"universal", "cloud"}


def test_tool_spec_records_read_only_and_scopes() -> None:
    spec = ToolSpec(
        name="fetch_current",
        availability=ToolAvailability.UNIVERSAL,
        required_capability="current",
        required_scopes=frozenset({"data:read"}),
        read_only=True,
        input_model=CurrentRequest,
        output_model=CurrentData,
    )

    assert spec.read_only is True
    assert spec.required_scopes == {"data:read"}
