from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from whatshot_mcp.contracts.v1 import (
    BackendCapabilities,
    CapabilityFeatures,
    CapabilityProfile,
    ItemKind,
    SuccessEnvelope,
)

FIXTURES = Path(__file__).parents[1] / "contracts" / "fixtures" / "v1"


def _core_read_features(**overrides: bool) -> CapabilityFeatures:
    values = {
        "sources": True,
        "source_schema": True,
        "current": True,
        "kinds": {ItemKind.HOTLIST},
        **overrides,
    }
    return CapabilityFeatures(**values)


def test_core_read_profile_allows_history_to_be_disabled() -> None:
    capabilities = BackendCapabilities(
        backend={"name": "local", "version": "0.1.0"},
        board_key_version=1,
        profiles={CapabilityProfile.CORE_READ},
        features=_core_read_features(),
    )

    assert capabilities.profiles == {CapabilityProfile.CORE_READ}
    assert capabilities.board_key_version == 1
    assert capabilities.features.history is False


def test_history_profile_requires_every_history_feature() -> None:
    with pytest.raises(ValidationError, match="trend_series"):
        BackendCapabilities(
            backend={"name": "local", "version": "0.1.0"},
            board_key_version=1,
            profiles={
                CapabilityProfile.CORE_READ,
                CapabilityProfile.HISTORY_READ,
            },
            features=_core_read_features(
                history=True,
                history_search=True,
                coverage=True,
            ),
        )


def test_capabilities_fixture_validates_as_success_envelope() -> None:
    payload = json.loads((FIXTURES / "capabilities-current.json").read_text())

    parsed = SuccessEnvelope[BackendCapabilities].model_validate(payload)

    assert parsed.data.backend.name == "whatshot-local"
    assert parsed.data.board_key_version == 1
    assert parsed.data.profiles == {CapabilityProfile.CORE_READ}
    assert parsed.model_dump(mode="json")["data"]["profiles"] == ["core-read"]
    assert "authorization" not in parsed.model_dump(mode="json")["data"]
