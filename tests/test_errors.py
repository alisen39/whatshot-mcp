from __future__ import annotations

import json
from pathlib import Path

from whats_hot_mcp.contracts.v1 import BackendErrorCode, ErrorEnvelope

FIXTURES = Path(__file__).parents[1] / "contracts" / "fixtures" / "v1"


def test_error_fixture_has_stable_envelope_and_camel_case() -> None:
    payload = json.loads((FIXTURES / "error-unknown-source.json").read_text())

    error = ErrorEnvelope.model_validate(payload)
    dumped = error.model_dump(mode="json")

    assert error.error.code is BackendErrorCode.UNKNOWN_SOURCE
    assert dumped["meta"]["requestId"] == "fixture-error-unknown-source"
    assert dumped["meta"]["contractVersion"] == "1"
    assert "data" not in dumped
